import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from config import get_settings
import logging
import socket
import time

print("DEBUG: database.py loading...", flush=True)
settings = get_settings()
print("DEBUG: Settings loaded in database module", flush=True)


def test_socket_connectivity(host: str, port: int, timeout: float = 5.0) -> tuple[bool, str]:
    """Test basic TCP connectivity to the database host."""
    try:
        print(f"DEBUG: Testing socket connectivity to {host}:{port}...", flush=True)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start = time.time()
        result = sock.connect_ex((host, port))
        elapsed = time.time() - start
        sock.close()
        if result == 0:
            print(f"DEBUG: Socket connection successful in {elapsed:.2f}s", flush=True)
            return True, f"Connected in {elapsed:.2f}s"
        else:
            print(f"DEBUG: Socket connection failed: error code {result}", flush=True)
            return False, f"Connection refused (error {result})"
    except socket.gaierror as e:
        print(f"DEBUG: DNS resolution failed for {host}: {e}", flush=True)
        return False, f"DNS resolution failed: {e}"
    except socket.timeout:
        print(f"DEBUG: Socket connection timed out after {timeout}s", flush=True)
        return False, f"Connection timed out after {timeout}s"
    except Exception as e:
        print(f"DEBUG: Socket test error: {e}", flush=True)
        return False, str(e)

# Connection pool for better Lambda performance
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        print(f"DEBUG: Creating connection pool to {settings.db_host}:{settings.db_port}/{settings.db_name}", flush=True)

        # Test basic socket connectivity first
        if settings.db_host:
            can_connect, msg = test_socket_connectivity(settings.db_host, settings.db_port, timeout=5.0)
            if not can_connect:
                print(f"DEBUG: Cannot reach database server: {msg}", flush=True)
                raise ConnectionError(f"Database unreachable: {msg}")
        else:
            print("DEBUG: db_host is empty - secrets may not have loaded correctly", flush=True)
            raise ValueError("Database host not configured")

        try:
            print("DEBUG: Socket test passed, creating connection pool...", flush=True)
            start = time.time()
            _pool = ConnectionPool(
                settings.database_url,
                min_size=1,
                max_size=5,
                open=True,  # Open connections immediately
                timeout=10,  # Connection timeout
                kwargs={"row_factory": dict_row}
            )
            print(f"DEBUG: Connection pool created successfully in {time.time() - start:.2f}s", flush=True)
        except Exception as e:
            print(f"DEBUG: Failed to create connection pool: {type(e).__name__}: {e}", flush=True)
            raise
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
