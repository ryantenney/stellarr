from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from contextlib import asynccontextmanager
import secrets

from config import get_settings
from database import init_db, add_request, remove_request, get_all_requests, is_requested
from tmdb import tmdb_client
from rss import generate_movie_rss, generate_tv_rss, generate_combined_rss


settings = get_settings()
security = HTTPBasic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Overseer Lite",
    description="A lightweight media request system with RSS feeds for Sonarr/Radarr",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth ---

def verify_password(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify the preshared password."""
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"),
        settings.preshared_password.encode("utf8")
    )
    if not correct_password:
        raise HTTPException(
            status_code=401,
            detail="Invalid password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


class PasswordCheck(BaseModel):
    password: str


@app.post("/api/auth/verify")
async def verify_auth(data: PasswordCheck):
    """Verify the preshared password."""
    if secrets.compare_digest(data.password, settings.preshared_password):
        return {"valid": True}
    raise HTTPException(status_code=401, detail="Invalid password")


# --- Search ---

class SearchQuery(BaseModel):
    query: str
    media_type: str | None = None  # "movie", "tv", or None for multi
    page: int = 1


@app.post("/api/search")
async def search(data: SearchQuery):
    """Search TMDB for movies and TV shows."""
    try:
        if data.media_type == "movie":
            results = await tmdb_client.search_movie(data.query, data.page)
        elif data.media_type == "tv":
            results = await tmdb_client.search_tv(data.query, data.page)
        else:
            results = await tmdb_client.search_multi(data.query, data.page)

        # Filter out person results and add requested status
        filtered_results = []
        for item in results.get("results", []):
            if item.get("media_type") == "person":
                continue

            media_type = item.get("media_type", data.media_type or "movie")
            tmdb_id = item.get("id")

            # Determine title and year
            if media_type == "tv":
                title = item.get("name", "Unknown")
                year = item.get("first_air_date", "")[:4] if item.get("first_air_date") else None
            else:
                title = item.get("title", "Unknown")
                year = item.get("release_date", "")[:4] if item.get("release_date") else None

            requested = await is_requested(tmdb_id, media_type)

            filtered_results.append({
                "id": tmdb_id,
                "title": title,
                "year": int(year) if year else None,
                "overview": item.get("overview"),
                "poster_path": item.get("poster_path"),
                "media_type": media_type,
                "vote_average": item.get("vote_average"),
                "requested": requested
            })

        return {
            "results": filtered_results,
            "page": results.get("page", 1),
            "total_pages": results.get("total_pages", 1),
            "total_results": results.get("total_results", 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Requests ---

class MediaRequest(BaseModel):
    tmdb_id: int
    media_type: str  # "movie" or "tv"


@app.post("/api/request")
async def create_request(data: MediaRequest):
    """Add a media item to the request list."""
    try:
        # Get full details from TMDB
        if data.media_type == "movie":
            details = await tmdb_client.get_movie(data.tmdb_id)
            title = details.get("title", "Unknown")
            year = details.get("release_date", "")[:4] if details.get("release_date") else None
            imdb_id = details.get("external_ids", {}).get("imdb_id")
            tvdb_id = None
        else:
            details = await tmdb_client.get_tv(data.tmdb_id)
            title = details.get("name", "Unknown")
            year = details.get("first_air_date", "")[:4] if details.get("first_air_date") else None
            imdb_id = details.get("external_ids", {}).get("imdb_id")
            tvdb_id = details.get("external_ids", {}).get("tvdb_id")

        success = await add_request(
            tmdb_id=data.tmdb_id,
            media_type=data.media_type,
            title=title,
            year=int(year) if year else None,
            overview=details.get("overview"),
            poster_path=details.get("poster_path"),
            imdb_id=imdb_id,
            tvdb_id=tvdb_id
        )

        if success:
            return {"success": True, "message": f"Added {title} to requests"}
        else:
            return {"success": False, "message": "Item may already be requested"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/request/{media_type}/{tmdb_id}")
async def delete_request(media_type: str, tmdb_id: int):
    """Remove a media item from the request list."""
    success = await remove_request(tmdb_id, media_type)
    if success:
        return {"success": True, "message": "Request removed"}
    raise HTTPException(status_code=404, detail="Request not found")


@app.get("/api/requests")
async def list_requests(media_type: str | None = None):
    """Get all requests, optionally filtered by media type."""
    requests = await get_all_requests(media_type)
    return {"requests": requests}


# --- Trending/Popular ---

@app.get("/api/trending")
async def get_trending(media_type: str = "all"):
    """Get trending movies/TV shows."""
    try:
        results = await tmdb_client.get_trending(media_type)

        items = []
        for item in results.get("results", []):
            item_type = item.get("media_type", media_type if media_type != "all" else "movie")
            tmdb_id = item.get("id")

            if item_type == "tv":
                title = item.get("name", "Unknown")
                year = item.get("first_air_date", "")[:4] if item.get("first_air_date") else None
            else:
                title = item.get("title", "Unknown")
                year = item.get("release_date", "")[:4] if item.get("release_date") else None

            requested = await is_requested(tmdb_id, item_type)

            items.append({
                "id": tmdb_id,
                "title": title,
                "year": int(year) if year else None,
                "overview": item.get("overview"),
                "poster_path": item.get("poster_path"),
                "media_type": item_type,
                "vote_average": item.get("vote_average"),
                "requested": requested
            })

        return {"results": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- RSS Feeds ---

@app.get("/rss/movies")
async def rss_movies(request: Request):
    """RSS feed for movie requests (Radarr compatible)."""
    base_url = str(request.base_url).rstrip("/")
    xml = await generate_movie_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/rss/tv")
async def rss_tv(request: Request):
    """RSS feed for TV show requests (Sonarr compatible)."""
    base_url = str(request.base_url).rstrip("/")
    xml = await generate_tv_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/rss/all")
async def rss_all(request: Request):
    """Combined RSS feed for all requests."""
    base_url = str(request.base_url).rstrip("/")
    xml = await generate_combined_rss(base_url)
    return Response(content=xml, media_type="application/rss+xml")


# --- Health Check ---

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "overseer-lite"}
