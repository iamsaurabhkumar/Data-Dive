/**
 * Runtime proxy for the FastAPI backend.
 *
 * `next.config.ts` rewrites resolve INTERNAL_API_URL at *build* time, which
 * silently ignored the value injected by docker-compose at run time. This
 * handler reads the env on every request instead, and forwards the bearer
 * token unchanged so the API keeps doing its own JWT verification.
 */
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const HOP_BY_HOP = new Set(["connection", "keep-alive", "transfer-encoding", "host", "content-length"]);

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const base = (process.env.INTERNAL_API_URL || "http://api:8000").replace(/\/$/, "");
  const url = `${base}/api/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => { if (!HOP_BY_HOP.has(k.toLowerCase())) headers.set(k, v); });

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  try {
    const upstream = await fetch(url, init);
    const out = new Headers();
    upstream.headers.forEach((v, k) => { if (!HOP_BY_HOP.has(k.toLowerCase())) out.set(k, v); });
    return new Response(upstream.status === 204 ? null : upstream.body, { status: upstream.status, headers: out });
  } catch (err) {
    return Response.json(
      { detail: `API unreachable at ${base}: ${err instanceof Error ? err.message : String(err)}` },
      { status: 502 },
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
