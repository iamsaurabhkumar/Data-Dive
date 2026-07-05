import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.redis import init_redis_pool, enqueue_task, close_redis_pool
from app.config import get_settings

async def main():
    settings = get_settings()
    # Initialize the ARQ Redis connection pool
    await init_redis_pool(settings.redis_url)
    
    print("Enqueueing mock task...")
    # Mock creator ID (a valid UUID)
    mock_creator_id = "123e4567-e89b-12d3-a456-426614174000"
    
    # We enqueue the fetch_and_analyze_trends task with ARQ native formatting
    job_id = await enqueue_task(
        "fetch_and_analyze_trends", 
        mock_creator_id, 
        "youtube"
    )
    
    if job_id:
        print(f"Task successfully enqueued with Job ID: {job_id}")
    else:
        print("Task was not enqueued (might be a duplicate).")
        
    await close_redis_pool()

if __name__ == "__main__":
    asyncio.run(main())
