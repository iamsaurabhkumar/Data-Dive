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


def get_rag_system_prompt() -> str:
    """
    Constructs the system instruction for the LLM Reasoner.
    Pivots raw trends into narrative-driven concepts for 'Keyboard on Clouds'.
    """
    return (
        "You are an elite creative director for a YouTube channel called 'Keyboard on Clouds'. "
        "The channel focuses on personal journeys, productivity, tech, and translating complex life lessons "
        "into modern, relatable, highly-aesthetic stories.\n\n"
        "Your task is to review the following trending YouTube topics and pivot them into a unique, "
        "narrative-driven video concept for 'Keyboard on Clouds'. Do NOT generate generic listicles. "
        "Instead, focus on how the creator can weave their personal experience into the trend."
    )


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
    
    try:
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
                {"role": "system", "content": get_rag_system_prompt()},
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
                    id, creator_id, trend_id, title, description, reasoning, confidence_score, status
                ) VALUES (
                    :id, :creator_id, :trend_id, :title, :description, :reasoning, :confidence_score, 'pending'
                )
            """)
            await session.execute(insert_suggestion_sql, {
                "id": uuid.uuid4(),
                "creator_id": creator_id,
                "trend_id": trend_id,
                "title": suggestion_output.title,
                "description": suggestion_output.description,
                "reasoning": suggestion_output.reasoning,
                "confidence_score": suggestion_output.confidence_score,
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
