"""
Core business logic tasks for the ARQ worker.
Handles external API ingestion, OpenAI vector generation, and structured RAG output.
"""
import logging
from datetime import datetime, timezone
from typing import Any
import uuid
import json

import httpx
import openai
from pydantic import BaseModel, Field
from sqlalchemy import text
from arq import Retry

from db import get_session
from config import get_worker_settings

logger = logging.getLogger("datadive.worker.tasks")
_settings = get_worker_settings()


class LLMSuggestion(BaseModel):
    """
    Pydantic schema for OpenAI Structured Outputs.
    Forces the LLM to return exactly this JSON structure.
    """
    title: str = Field(description="The proposed title for the new video/post.")
    description: str = Field(description="Detailed strategy and narrative approach for the content.")
    reasoning: str = Field(description="Why this trend fits the creator's persona and audience.")
    confidence_score: float = Field(description="A score between 0.0 and 1.0 indicating relevance.")


async def fetch_youtube_trends(http_client: httpx.AsyncClient, category_id: str = "27") -> list[dict]:
    """
    Fetches trending videos from YouTube Data API.
    Strips raw payload to heavily optimize token usage before passing to LLM.
    """
    api_key = _settings.youtube_api_key
    if not api_key:
        logger.error("YOUTUBE_API_KEY is not set.")
        return []

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet",
        "chart": "mostPopular",
        "videoCategoryId": category_id,
        "maxResults": 3,  # Top 3 to save context window and vector costs
        "key": api_key,
    }

    try:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.error(f"YouTube API HTTP error: {exc}")
        raise  # Bubble up to trigger ARQ backoff

    trends = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        # Token Optimization: strictly map only necessary fields
        trends.append({
            "id": item.get("id"),
            "title": snippet.get("title", ""),
            "tags": snippet.get("tags", [])[:5],  # Limit tags
        })
        
    return trends


async def load_creator_context(creator_id: str, limit: int = 40) -> dict:
    """
    Pull the creator's recent titles (best performers first) so the LLM persona is
    derived from *their* content rather than a hard-coded channel.
    """
    sql = text("""
        SELECT p.platform, p.content_type, p.title, COALESCE(m.views, 0) AS views
        FROM content_posts p
        LEFT JOIN LATERAL (
            SELECT views FROM metric_snapshots s WHERE s.post_id = p.id
            ORDER BY captured_at DESC LIMIT 1
        ) m ON TRUE
        WHERE p.creator_id = :creator_id
        ORDER BY COALESCE(m.views, 0) DESC
        LIMIT :limit
    """)
    async with get_session() as session:
        rows = (await session.execute(sql, {"creator_id": creator_id, "limit": limit})).all()
    return {
        "titles": [r.title for r in rows],
        "platforms": sorted({r.platform for r in rows}),
        "top": [f"{r.title} ({r.platform} {r.content_type}, {r.views:,} views)" for r in rows[:8]],
    }


def get_rag_system_prompt(context: dict | None = None) -> str:
    """
    System instruction for the LLM reasoner, grounded in the creator's own catalogue.
    Falls back to a generic creator persona when the creator has no synced content yet.
    """
    base = (
        "You are an elite creative director for an independent content creator. "
        "Review the trending topic provided and pivot it into ONE specific, narrative-driven video concept "
        "this creator could realistically make next week. Do NOT generate generic listicles; weave the "
        "creator's existing themes and personal experience into the trend."
    )
    if context and context.get("top"):
        base += (
            "\n\nThe creator publishes on: " + ", ".join(context["platforms"]) + ".\n"
            "Their best-performing recent content (use this to infer voice, niche and audience):\n- "
            + "\n- ".join(context["top"])
        )
    return base


async def fetch_and_analyze_trends(ctx: dict[str, Any], creator_id: str, platform: str = "youtube") -> dict:
    """
    Core asynchronous task:
    1. Ingest YouTube trends.
    2. Generate vectors via OpenAI text-embedding-3-small.
    3. Run structured RAG inference via gpt-4o-mini.
    4. Save securely via a single SQLAlchemy transaction block.
    """
    attempt = ctx.get('job_try', 1)
    logger.info("Starting fetch_and_analyze_trends for creator=%s, platform=%s (Attempt %d)", 
                creator_id, platform, attempt)
    
    http_client: httpx.AsyncClient = ctx['http']
    openai_client: openai.AsyncClient = ctx['openai']

    if not _settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping trend analysis for creator=%s", creator_id)
        return {"status": "skipped", "reason": "no_openai_key"}

    try:
        # 0. Creator context for the persona prompt
        creator_context = await load_creator_context(creator_id)

        # 1. Fetch Truncated Trends
        trends = await fetch_youtube_trends(http_client)
        if not trends:
            logger.warning("No trends returned from YouTube.")
            return {"status": "no_trends"}

        # We will process the top trend for the suggestion to keep the transaction tight.
        top_trend = trends[0]
        trend_text = f"Title: {top_trend['title']}\nTags: {', '.join(top_trend['tags'])}"
        
        # 2. Vector Generation
        embedding_response = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=trend_text
        )
        embedding_vector = embedding_response.data[0].embedding

        # 3. LLM Reasoner (Structured Output)
        completion = await openai_client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_rag_system_prompt(creator_context)},
                {"role": "user", "content": f"Here is the top trending video data: {trend_text}. Generate a video suggestion based on this."},
            ],
            response_format=LLMSuggestion,
        )
        suggestion_output = completion.choices[0].message.parsed
        
        # 4. Transaction Safety
        async with get_session() as session:
            # Upsert PlatformTrend (Idempotent: ON CONFLICT DO NOTHING)
            # We use explicit SQL to avoid needing the full ORM mappings in the worker context
            trend_id = uuid.uuid4()
            upsert_trend_sql = text("""
                INSERT INTO platform_trends (
                    id, source, category, title, description, external_url, 
                    raw_metadata, embedding, fetched_at
                ) VALUES (
                    :id, :source, :category, :title, :description, :external_url,
                    :raw_metadata, :embedding, :fetched_at
                )
                ON CONFLICT (source, external_url, ((fetched_at AT TIME ZONE 'UTC')::date)) 
                WHERE external_url IS NOT NULL 
                DO NOTHING
                RETURNING id;
            """)
            
            result = await session.execute(upsert_trend_sql, {
                "id": trend_id,
                "source": platform,
                "category": "productivity", # Default category for this run
                "title": top_trend['title'],
                "description": "",
                "external_url": f"https://youtube.com/watch?v={top_trend['id']}",
                "raw_metadata": json.dumps({"tags": top_trend['tags']}),
                "embedding": f"[{','.join(map(str, embedding_vector))}]",
                "fetched_at": datetime.now(timezone.utc),
            })
            
            # If DO NOTHING triggered, it returns None. We need to query for the ID.
            returned_trend_id = result.scalar()
            if not returned_trend_id:
                fetch_existing_sql = text("""
                    SELECT id FROM platform_trends 
                    WHERE source = :source 
                    AND external_url = :external_url
                    AND ((fetched_at AT TIME ZONE 'UTC')::date) = (:fetched_at AT TIME ZONE 'UTC')::date
                """)
                existing_res = await session.execute(fetch_existing_sql, {
                    "source": platform,
                    "external_url": f"https://youtube.com/watch?v={top_trend['id']}",
                    "fetched_at": datetime.now(timezone.utc)
                })
                trend_id = existing_res.scalar() or trend_id # Fallback to generated ID
            else:
                trend_id = returned_trend_id

            # Insert ContentSuggestion
            insert_suggestion_sql = text("""
                INSERT INTO content_suggestions (
                    id, creator_id, trend_id, title, description, reasoning, confidence_score, status,
                    source, platform, content_type, topics
                ) VALUES (
                    :id, :creator_id, :trend_id, :title, :description, :reasoning, :confidence_score, 'pending',
                    'trend', 'YouTube', 'Long-form', :topics
                )
            """)
            await session.execute(insert_suggestion_sql, {
                "id": uuid.uuid4(),
                "creator_id": creator_id,
                "trend_id": trend_id,
                "title": suggestion_output.title,
                "description": suggestion_output.description,
                "reasoning": suggestion_output.reasoning,
                "confidence_score": max(0.0, min(1.0, suggestion_output.confidence_score)),
                "topics": json.dumps(top_trend['tags'][:3]),
            })
            
            # Transaction automatically commits on exit of context manager
            
        logger.info("Successfully completed fetch_and_analyze_trends for creator=%s", creator_id)
        return {"status": "success", "platform": platform, "creator_id": creator_id}
        
    except httpx.HTTPError as exc:
        logger.warning("HTTP Error during trend fetch (Attempt %d): %s", attempt, exc)
        # Exponential backoff: 10s -> 30s -> 90s
        delay = 10 * (3 ** (attempt - 1))
        raise Retry(defer=delay)
    except openai.APIError as exc:
        logger.warning("OpenAI API Error (Attempt %d): %s", attempt, exc)
        delay = 10 * (3 ** (attempt - 1))
        raise Retry(defer=delay)
    except Exception as exc:
        logger.exception("Unexpected error in fetch_and_analyze_trends")
        raise



# ──────────────────────────────────────────────────────────────────────────
# Phase 3 additions
# ──────────────────────────────────────────────────────────────────────────
class LLMEnrichment(BaseModel):
    """Hook + outline for an existing idea (structured output)."""
    title: str = Field(description="A sharper, specific title (max 70 chars).")
    hook: str = Field(description="The first spoken/on-screen line. One or two sentences, pattern-interrupt.")
    outline: list[str] = Field(description="4-7 production beats, in order, each one line.")


ENRICH_MAX_TRIES = 3


async def _set_enrichment_status(suggestion_id: str, status: str) -> None:
    async with get_session() as session:
        await session.execute(text(
            "UPDATE content_suggestions SET enrichment_status = :s, updated_at = now() WHERE id = :id"
        ), {"id": suggestion_id, "s": status})


async def enrich_idea(ctx: dict[str, Any], suggestion_id: str) -> dict:
    """
    Optional LLM pass over an idea produced by the analytics engine or "Generate Next Project":
    rewrites the title and fills hook/outline in the creator's voice, grounded in the trend
    that inspired it. The forecast/prediction is never touched so it stays reviewable.

    enrichment_status: queued → done | skipped (no key) | failed (after ENRICH_MAX_TRIES)
    """
    openai_client: openai.AsyncClient = ctx['openai']
    if not _settings.openai_api_key:
        await _set_enrichment_status(suggestion_id, "skipped")
        return {"status": "skipped", "reason": "no_openai_key"}

    async with get_session() as session:
        row = (await session.execute(text("""
            SELECT s.id, s.creator_id, s.title, s.hook, s.outline, s.platform, s.content_type, s.topics, s.reasoning,
                   t.title AS trend_title, t.source AS trend_source, t.raw_metadata AS trend_meta
            FROM content_suggestions s
            LEFT JOIN platform_trends t ON t.id = s.trend_id
            WHERE s.id = :id
        """), {"id": suggestion_id})).first()
    if row is None:
        return {"status": "not_found"}

    context = await load_creator_context(str(row.creator_id))
    trend_line = ""
    if row.trend_title:
        tags = (row.trend_meta or {}).get("tags", []) if isinstance(row.trend_meta, dict) else []
        trend_line = f"Trend it builds on: {row.trend_title} (on {row.trend_source}; tags: {', '.join(tags[:5])})\n"
    user_msg = (
        f"Idea: {row.title}\nPlatform/format: {row.platform} {row.content_type}\n{trend_line}"
        f"Topics: {', '.join(row.topics or [])}\nWhy it was suggested: {row.reasoning or ''}\n"
        f"Current hook: {row.hook or '(none)'}\nCurrent outline: {row.outline or '(none)'}\n\n"
        "Rewrite the title, write the hook and a production outline for this exact format. "
        "Keep the same angle and the same trend; do not invent statistics."
    )
    attempt = ctx.get('job_try', 1)
    try:
        completion = await openai_client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": get_rag_system_prompt(context)},
                      {"role": "user", "content": user_msg}],
            response_format=LLMEnrichment,
        )
    except openai.APIError as exc:
        logger.warning("OpenAI error enriching %s (attempt %d): %s", suggestion_id, attempt, exc)
        if attempt >= ENRICH_MAX_TRIES:
            await _set_enrichment_status(suggestion_id, "failed")
            return {"status": "failed", "suggestion_id": suggestion_id}
        raise Retry(defer=10 * (3 ** (attempt - 1)))

    out = completion.choices[0].message.parsed
    async with get_session() as session:
        await session.execute(text("""
            UPDATE content_suggestions
            SET title = :title, hook = :hook, outline = :outline, enrichment_status = 'done', updated_at = now()
            WHERE id = :id
        """), {"id": suggestion_id, "title": out.title[:200], "hook": out.hook, "outline": json.dumps(out.outline)})
    logger.info("Enriched suggestion %s", suggestion_id)
    return {"status": "success", "suggestion_id": suggestion_id}


async def fetch_trends_for_all_creators(ctx: dict[str, Any]) -> dict:
    """12-hour cron (per V2 spec): enqueue a trend analysis job for every creator profile."""
    from arq import ArqRedis  # local import: only needed inside the worker process
    redis: ArqRedis = ctx['redis']
    async with get_session() as session:
        ids = [str(r[0]) for r in (await session.execute(text("SELECT id FROM creator_profiles"))).all()]
    for cid in ids:
        await redis.enqueue_job("fetch_and_analyze_trends", cid, "youtube", _job_id=f"trends:{cid}:{datetime.now(timezone.utc):%Y%m%d%H}")
    logger.info("Scheduled trend analysis for %d creators", len(ids))
    return {"scheduled": len(ids)}
