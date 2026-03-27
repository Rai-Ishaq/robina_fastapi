# ── Run this once on your database to add media columns ──────
# Render pe GitBash se run karo:
# python add_media_columns.py

import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Render gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Add media columns to messages table if not exist
    conn.execute(text("""
        ALTER TABLE messages
        ADD COLUMN IF NOT EXISTS media_url VARCHAR,
        ADD COLUMN IF NOT EXISTS media_type VARCHAR,
        ADD COLUMN IF NOT EXISTS media_thumbnail VARCHAR;
    """))
    conn.commit()
    print("✅ Media columns added to messages table!")