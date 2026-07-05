import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_session

async def main():
    async with get_session() as db:
        res = await db.execute(text("SELECT id FROM creator_profiles LIMIT 1"))
        creator_id = res.scalar()
        
        if not creator_id:
            print("No creator profile found!")
            return

        trend_id = uuid.uuid4()
        
        # 1. Insert fake trend
        mock_embedding = "[" + ",".join(["0.0"] * 1536) + "]"
        await db.execute(text(f"""
            INSERT INTO platform_trends (
                id, source, category, title, description, external_url, 
                raw_metadata, embedding, fetched_at
            ) VALUES (
                :id, 'youtube', 'productivity', 'How I built a $10k/mo side hustle', '', 'https://youtube.com/watch?v=mock',
                '{{}}', '{mock_embedding}', :fetched_at
            )
        """), {
            "id": trend_id,
            "fetched_at": datetime.now(timezone.utc)
        })

        # 2. Insert suggestion
        suggestion_id = uuid.uuid4()
        await db.execute(text("""
            INSERT INTO content_suggestions (
                id, creator_id, trend_id, title, description, reasoning, confidence_score, status
            ) VALUES (
                :id, :creator_id, :trend_id, 
                'The "Anti-Hustle" Side Hustle',
                'A narrative-driven video breaking down how building systems instead of grinding hours leads to sustainable income.',
                'The audience resonates with productivity but is burned out. Framing a side hustle through an anti-hustle, systematic lens aligns perfectly with your "Keyboard on Clouds" persona.',
                0.92,
                'pending'
            )
        """), {
            "id": suggestion_id,
            "creator_id": creator_id,
            "trend_id": trend_id
        })
        
        await db.commit()
        print("Mock suggestion inserted successfully!")

if __name__ == "__main__":
    asyncio.run(main())
