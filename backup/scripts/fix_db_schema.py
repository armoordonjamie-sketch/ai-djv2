import sqlite3

conn = sqlite3.connect('data/ai_dj.db')
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables:", tables)

if 'llm_trace' in tables:
    print("llm_trace exists, adding column...")
    try:
        conn.execute('ALTER TABLE llm_trace ADD COLUMN correlation_id TEXT')
        conn.commit()
        print("Column added!")
    except Exception as e:
        print(f"Error: {e}")
else:
    print("llm_trace table does NOT exist, creating all tables...")
    from backend_v2.db.base import Base
    from backend_v2.db.session import engine
    from backend_v2.models import existing  # noqa: F401 - ensure models are loaded
    from backend_v2.models import user  # noqa: F401
    from backend_v2.models import mood  # noqa: F401
    from backend_v2.models import status_event_log  # noqa: F401
    
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine
    
    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("All tables created!")
    
    asyncio.run(create_tables())

conn.close()
