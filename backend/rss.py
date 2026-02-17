from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from database import get_all_requests


def create_feed_generator(title: str, description: str, link: str) -> FeedGenerator:
    """Create a base feed generator."""
    fg = FeedGenerator()
    fg.title(title)
    fg.description(description)
    fg.link(href=link, rel="self")
    fg.language("en")
    fg.lastBuildDate(datetime.now(timezone.utc))
    return fg


def _get_pub_date(created_at: str | None) -> datetime:
    """Parse publication date from created_at timestamp."""
    if created_at:
        try:
            return datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    return datetime.now(timezone.utc)


async def generate_movie_rss(base_url: str) -> str:
    """
    Generate RSS feed for movie requests (Radarr compatible).

    Radarr RSS format expects:
    - Title with year: "Movie Name (2023)"
    - GUID with IMDB ID for accurate matching
    """
    requests = await get_all_requests(media_type="movie")

    fg = create_feed_generator(
        title="Stellarr - Movie Requests",
        description="Movie requests from Stellarr for Radarr",
        link=f"{base_url}/rss/movies"
    )

    for req in requests:
        fe = fg.add_entry()

        # Title format: "Movie Name (Year)" - this is what Radarr parses
        title = f"{req['title']} ({req['year']})" if req['year'] else req['title']
        fe.title(title)
        fe.id(f"movie-{req['tmdb_id']}")
        fe.description(req['overview'] or "No description available")

        # GUID: IMDB ID is preferred for Radarr matching
        # Radarr looks for IMDB IDs (tt1234567 format)
        if req['imdb_id']:
            fe.guid(req['imdb_id'], permalink=False)
        else:
            # Fallback to title format which Radarr can also parse
            fe.guid(title, permalink=False)

        fe.link(href=f"https://www.themoviedb.org/movie/{req['tmdb_id']}")
        fe.pubDate(_get_pub_date(req['created_at']))

    return fg.rss_str(pretty=True).decode('utf-8')


async def generate_tv_rss(base_url: str) -> str:
    """
    Generate RSS feed for TV show requests.

    For Sonarr, use /list/sonarr JSON endpoint instead (Custom Lists).
    This RSS feed is provided for other tools that may consume it.
    """
    requests = await get_all_requests(media_type="tv")

    fg = create_feed_generator(
        title="Stellarr - TV Show Requests",
        description="TV show requests from Stellarr",
        link=f"{base_url}/rss/tv"
    )

    for req in requests:
        fe = fg.add_entry()

        title = f"{req['title']} ({req['year']})" if req['year'] else req['title']
        fe.title(title)
        fe.id(f"tv-{req['tmdb_id']}")
        fe.description(req['overview'] or "No description available")

        # TVDB ID for potential Sonarr compatibility
        if req['tvdb_id']:
            fe.guid(f"tvdb-{req['tvdb_id']}", permalink=False)
        else:
            fe.guid(title, permalink=False)

        fe.link(href=f"https://www.themoviedb.org/tv/{req['tmdb_id']}")
        fe.pubDate(_get_pub_date(req['created_at']))

    return fg.rss_str(pretty=True).decode('utf-8')


async def generate_combined_rss(base_url: str) -> str:
    """Generate combined RSS feed for all requests."""
    requests = await get_all_requests()

    fg = create_feed_generator(
        title="Stellarr - All Requests",
        description="All media requests from Stellarr",
        link=f"{base_url}/rss/all"
    )

    for req in requests:
        fe = fg.add_entry()
        fe.id(f"{req['media_type']}-{req['tmdb_id']}")

        type_label = "Movie" if req['media_type'] == "movie" else "TV"
        title = f"{req['title']} ({req['year']})" if req['year'] else req['title']
        fe.title(f"[{type_label}] {title}")
        fe.description(req['overview'] or "No description available")

        # Use appropriate ID for GUID
        if req['media_type'] == "movie" and req['imdb_id']:
            fe.guid(req['imdb_id'], permalink=False)
        elif req['media_type'] == "tv" and req['tvdb_id']:
            fe.guid(f"tvdb-{req['tvdb_id']}", permalink=False)
        else:
            fe.guid(title, permalink=False)

        fe.link(href=f"https://www.themoviedb.org/{req['media_type']}/{req['tmdb_id']}")
        fe.pubDate(_get_pub_date(req['created_at']))

    return fg.rss_str(pretty=True).decode('utf-8')


async def generate_radarr_json() -> list[dict]:
    """
    Generate Radarr StevenLu Custom list format (JSON).

    This is the RECOMMENDED format for Radarr as it uses IMDB IDs
    for accurate matching without requiring text search.

    Format: [{"title": "Movie", "imdb_id": "tt1234567", "poster_url": "..."}]
    """
    requests = await get_all_requests(media_type="movie")

    items = []
    for req in requests:
        item = {
            "title": f"{req['title']} ({req['year']})" if req['year'] else req['title'],
        }

        # IMDB ID is preferred for accurate matching
        if req['imdb_id']:
            item["imdb_id"] = req['imdb_id']

        # Include poster URL if available
        if req['poster_path']:
            item["poster_url"] = f"https://image.tmdb.org/t/p/w300{req['poster_path']}"

        items.append(item)

    return items


async def generate_sonarr_json() -> list[dict]:
    """
    Generate Sonarr Custom List format (JSON).

    Sonarr supports custom lists with tvdbId field.
    See: https://github.com/Sonarr/Sonarr/pull/5160

    Format: [{"tvdbId": "75837"}, {"tvdbId": "77847"}]

    In Sonarr: Settings -> Import Lists -> Add -> Custom Lists
    """
    requests = await get_all_requests(media_type="tv")

    items = []
    for req in requests:
        # Sonarr requires tvdbId as a string
        if req['tvdb_id']:
            items.append({"tvdbId": str(req['tvdb_id'])})

    return items
