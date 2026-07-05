"""
Redis connection pool and task dispatch for Data-Dive API using ARQ.

Design:
- Singleton ArqRedis initialized in FastAPI lifespan, closed on shutdown.
- enqueue_task() uses ARQ's native enqueue_job to push to the worker.
- Graceful degradation: Redis failures return HTTP-safe errors, never block the event loop.
"""
import logging
from typing import Any

from arq.connections import RedisSettings, ArqRedis, create_pool
from redis.exceptions import ConnectionError, TimeoutError, RedisError

logger = logging.getLogger("datadive.redis")

# Module-level reference
_pool: ArqRedis | None = None

class RedisUnavailableError(Exception):
    """Raised when Redis broker is unreachable. Maps to HTTP 503."""
    pass

def _parse_redis_settings(redis_url: str) -> RedisSettings:
    url = redis_url.replace("redis://", "")
    parts = url.split("/")
    host_port = parts[0]
    database = int(parts[1]) if len(parts) > 1 else 0

    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = 6379

    return RedisSettings(
        host=host, 
        port=port, 
        database=database,
        conn_timeout=2.0,
        conn_retries=2,
    )

async def init_redis_pool(redis_url: str) -> None:
    global _pool

    redis_settings = _parse_redis_settings(redis_url)
    
    try:
        _pool = await create_pool(redis_settings)
        # Verify connectivity
        await _pool.ping()
        logger.info("ARQ Redis connection pool initialized")
    except (ConnectionError, TimeoutError, Exception) as exc:
        logger.error("Redis startup connectivity check failed: %s", exc)
        raise

async def close_redis_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("ARQ Redis connection pool disconnected")

def get_redis_pool() -> ArqRedis:
    if _pool is None:
        raise RedisUnavailableError("ARQ Redis pool not initialized")
    return _pool

async def check_redis_health() -> bool:
    if _pool is None:
        return False
    try:
        return await _pool.ping()
    except (ConnectionError, TimeoutError, RedisError, Exception):
        return False

async def enqueue_task(
    task_name: str,
    *args: Any,
    **kwargs: Any,
) -> str | None:
    """
    Push a task to the ARQ worker queue.
    """
    pool = get_redis_pool()

    try:
        job = await pool.enqueue_job(task_name, *args, **kwargs)
        if job:
            logger.info("Task enqueued: task=%s job_id=%s", task_name, job.job_id)
            return job.job_id
        else:
            logger.warning("Task not enqueued (might be a duplicate): %s", task_name)
            return None
    except (ConnectionError, TimeoutError) as exc:
        logger.error("Failed to enqueue task=%s: Redis unreachable — %s", task_name, exc)
        raise RedisUnavailableError(f"Task queue temporarily unavailable: {exc}") from exc
