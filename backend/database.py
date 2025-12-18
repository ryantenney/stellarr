import aiosqlite
from config import get_settings
from pathlib import Path

settings = get_settings()


async def init_db():
    """Initialize the database with required tables."""
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                year INTEGER,
                overview TEXT,
                poster_path TEXT,
                imdb_id TEXT,
                tvdb_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tmdb_id, media_type)
            )
        """)
        await db.commit()


async def get_db():
    """Get database connection."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def add_request(
    tmdb_id: int,
    media_type: str,
    title: str,
    year: int | None,
    overview: str | None,
    poster_path: str | None,
    imdb_id: str | None = None,
    tvdb_id: int | None = None
) -> bool:
    """Add a media request to the database."""
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                """
                INSERT OR IGNORE INTO requests
                (tmdb_id, media_type, title, year, overview, poster_path, imdb_id, tvdb_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tmdb_id, media_type, title, year, overview, poster_path, imdb_id, tvdb_id)
            )
            await db.commit()
            return True
        except Exception as e:
            print(f"Error adding request: {e}")
            return False


async def remove_request(tmdb_id: int, media_type: str) -> bool:
    """Remove a media request from the database."""
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                "DELETE FROM requests WHERE tmdb_id = ? AND media_type = ?",
                (tmdb_id, media_type)
            )
            await db.commit()
            return True
        except Exception as e:
            print(f"Error removing request: {e}")
            return False


async def get_all_requests(media_type: str | None = None) -> list[dict]:
    """Get all media requests, optionally filtered by type."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        if media_type:
            cursor = await db.execute(
                "SELECT * FROM requests WHERE media_type = ? ORDER BY created_at DESC",
                (media_type,)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM requests ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def is_requested(tmdb_id: int, media_type: str) -> bool:
    """Check if a media item has already been requested."""
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM requests WHERE tmdb_id = ? AND media_type = ?",
            (tmdb_id, media_type)
        )
        row = await cursor.fetchone()
        return row is not None
