from sqlalchemy import create_engine, text
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

try:
    with engine.begin() as conn:
        print("Adding 'deleted_by' column to 'messages' table...")
        conn.execute(text("""
            ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS deleted_by VARCHAR DEFAULT '';
        """))
        print("✅ Schema updated successfully: Added 'deleted_by'!")
except Exception as e:
    print("Error updating schema:", e)
