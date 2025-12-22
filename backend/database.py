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
                added_at TIMESTAMP,
                plex_guid TEXT,
                UNIQUE(tmdb_id, media_type)
            )
        """)

        # Library table for tracking items in Plex
        await db.execute("""
            CREATE TABLE IF NOT EXISTS library (
                tmdb_id INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                tvdb_id INTEGER,
                title TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tmdb_id, media_type)
            )
        """)

        # Plex GUID cache table for caching show-level IDs from episode webhooks
        await db.execute("""
            CREATE TABLE IF NOT EXISTS plex_guid_cache (
                plex_guid TEXT PRIMARY KEY,
                show_tmdb_id INTEGER,
                show_tvdb_id INTEGER,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add new columns if missing (for existing databases)
        cursor = await db.execute("PRAGMA table_info(requests)")
        columns = [row[1] for row in await cursor.fetchall()]
        if 'added_at' not in columns:
            await db.execute("ALTER TABLE requests ADD COLUMN added_at TIMESTAMP")
        if 'plex_guid' not in columns:
            await db.execute("ALTER TABLE requests ADD COLUMN plex_guid TEXT")

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


async def mark_as_added(tmdb_id: int, media_type: str) -> bool:
    """Mark a request as added to Plex library."""
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            cursor = await db.execute(
                """
                UPDATE requests
                SET added_at = CURRENT_TIMESTAMP
                WHERE tmdb_id = ? AND media_type = ? AND added_at IS NULL
                """,
                (tmdb_id, media_type)
            )
            await db.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error marking request as added: {e}")
            return False


async def find_by_tvdb_id(tvdb_id: int, media_type: str) -> dict | None:
    """Find a request by TVDB ID."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM requests WHERE tvdb_id = ? AND media_type = ?",
            (tvdb_id, media_type)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def find_by_plex_guid(plex_guid: str) -> dict | None:
    """Find a request by Plex GUID."""
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM requests WHERE plex_guid = ?",
            (plex_guid,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_plex_guid(tmdb_id: int, media_type: str, plex_guid: str) -> bool:
    """Cache a Plex GUID on a request for future matching."""
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                """
                UPDATE requests
                SET plex_guid = ?
                WHERE tmdb_id = ? AND media_type = ?
                """,
                (plex_guid, tmdb_id, media_type)
            )
            await db.commit()
            return True
        except Exception as e:
            print(f"Error updating plex_guid: {e}")
            return False


# --- Library Functions ---

async def sync_library(items: list[dict], media_type: str, clear_first: bool = False) -> int:
    """
    Sync library items for a media type.
    Upserts items (additive by default).
    Set clear_first=True to delete all existing items before inserting.
    Returns count of items synced.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            # Optionally clear existing items first
            if clear_first:
                await db.execute(
                    "DELETE FROM library WHERE media_type = ?",
                    (media_type,)
                )

            # Insert/update items
            for item in items:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO library (tmdb_id, media_type, tvdb_id, title)
                    VALUES (?, ?, ?, ?)
                    """,
                    (item['tmdb_id'], media_type, item.get('tvdb_id'), item.get('title'))
                )

            await db.commit()
            return len(items)
        except Exception as e:
            print(f"Error syncing library: {e}")
            return 0


async def is_in_library(tmdb_id: int, media_type: str) -> bool:
    """Check if an item exists in the Plex library."""
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM library WHERE tmdb_id = ? AND media_type = ?",
            (tmdb_id, media_type)
        )
        row = await cursor.fetchone()
        return row is not None


async def get_library_ids(media_type: str | None = None) -> set[tuple[int, str]]:
    """Get all (tmdb_id, media_type) pairs in library for batch checking."""
    async with aiosqlite.connect(settings.database_path) as db:
        if media_type:
            cursor = await db.execute(
                "SELECT tmdb_id, media_type FROM library WHERE media_type = ?",
                (media_type,)
            )
        else:
            cursor = await db.execute("SELECT tmdb_id, media_type FROM library")
        rows = await cursor.fetchall()
        return {(row[0], row[1]) for row in rows}


# --- Plex GUID Cache ---
# Caches plex_guid -> {tmdb_id, tvdb_id} for shows
# This prevents repeated TVDB reverse lookups for episodes of the same show

async def get_plex_guid_cache(plex_guid: str) -> dict | None:
    """
    Look up cached show-level IDs for a Plex GUID.
    Returns dict with tmdb_id, tvdb_id if found, None otherwise.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT show_tmdb_id, show_tvdb_id FROM plex_guid_cache WHERE plex_guid = ?",
            (plex_guid,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                'tmdb_id': row['show_tmdb_id'],
                'tvdb_id': row['show_tvdb_id']
            }
        return None


async def set_plex_guid_cache(plex_guid: str, tmdb_id: int | None, tvdb_id: int | None) -> bool:
    """
    Cache show-level IDs for a Plex GUID.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                """
                INSERT OR REPLACE INTO plex_guid_cache (plex_guid, show_tmdb_id, show_tvdb_id)
                VALUES (?, ?, ?)
                """,
                (plex_guid, tmdb_id, tvdb_id)
            )
            await db.commit()
            return True
        except Exception as e:
            print(f"Error setting plex_guid cache: {e}")
            return False
