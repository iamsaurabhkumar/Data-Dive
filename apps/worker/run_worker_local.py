import asyncio
import sys
import os
import httpx
import openai
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from sqlalchemy import text
from db import get_session
from tasks import fetch_and_analyze_trends

async def main():
    async with get_session() as db:
        res = await db.execute(text("SELECT id FROM creator_profiles LIMIT 1"))
        creator_id = res.scalar()
    
    if not creator_id:
        print("No creator profile found. Please sync first.")
        return

    print(f"Running manual worker for creator: {creator_id}")
    
    from config import get_worker_settings
    _settings = get_worker_settings()
    
    async with httpx.AsyncClient() as http_client:
        openai_client = openai.AsyncClient(api_key=_settings.openai_api_key)
        ctx = {
            "http": http_client,
            "openai": openai_client,
            "job_try": 1
        }
        
        try:
            result = await fetch_and_analyze_trends(ctx, str(creator_id), "youtube")
            print("Task result:", result)
        except Exception as e:
            print("Worker failed:", e)

if __name__ == "__main__":
    asyncio.run(main())
