import os
from sqlalchemy import create_engine, text
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Drop old bool columns and add new ones
    try:
        conn.execute(text("ALTER TABLE messages DROP COLUMN is_seen;"))
        conn.execute(text("ALTER TABLE messages DROP COLUMN seen_at;"))
    except Exception as e:
        print("Column is_seen or seen_at already dropped or not exist.", e)
        
    try:
        conn.execute(text("""
            ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'sent',
            ADD COLUMN IF NOT EXISTS quote_content TEXT,
            ADD COLUMN IF NOT EXISTS quote_sender VARCHAR;
        """))
    except Exception as e:
        print("Error adding new columns:", e)
        
    conn.commit()
    print("✅ Schema updated!")
