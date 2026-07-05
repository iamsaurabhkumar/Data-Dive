import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import async_session_factory
from sqlalchemy import text

async def main():
    async with async_session_factory() as db:
        res = await db.execute(text("SELECT id, creator_id, platform, title FROM content_posts"))
        rows = res.fetchall()
        print(f"Total posts in DB: {len(rows)}")
        for r in rows:
            print(f"- {r[2]}: {r[3]}")

if __name__ == "__main__":
    asyncio.run(main())
