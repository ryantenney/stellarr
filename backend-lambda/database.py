import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from config import get_settings

settings = get_settings()

# Connection pool for better Lambda performance
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row}
        )
    return _pool


@contextmanager
def get_connection():
    """Get a database connection from the pool."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def init_db():
    """Initialize the database with required tables."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
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
        conn.commit()


def add_request(
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
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO requests
                (tmdb_id, media_type, title, year, overview, poster_path, imdb_id, tvdb_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tmdb_id, media_type) DO NOTHING
                """,
                (tmdb_id, media_type, title, year, overview, poster_path, imdb_id, tvdb_id)
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"Error adding request: {e}")
        return False


def remove_request(tmdb_id: int, media_type: str) -> bool:
    """Remove a media request from the database."""
    try:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM requests WHERE tmdb_id = %s AND media_type = %s",
                (tmdb_id, media_type)
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"Error removing request: {e}")
        return False


def get_all_requests(media_type: str | None = None) -> list[dict]:
    """Get all media requests, optionally filtered by type."""
    with get_connection() as conn:
        if media_type:
            cursor = conn.execute(
                "SELECT * FROM requests WHERE media_type = %s ORDER BY created_at DESC",
                (media_type,)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM requests ORDER BY created_at DESC"
            )
        return cursor.fetchall()


def is_requested(tmdb_id: int, media_type: str) -> bool:
    """Check if a media item has already been requested."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM requests WHERE tmdb_id = %s AND media_type = %s",
            (tmdb_id, media_type)
        )
        return cursor.fetchone() is not None
