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


async def generate_movie_rss(base_url: str) -> str:
    """Generate RSS feed for movie requests (Radarr compatible)."""
    requests = await get_all_requests(media_type="movie")

    fg = create_feed_generator(
        title="Overseer Lite - Movie Requests",
        description="Movie requests from Overseer Lite",
        link=f"{base_url}/rss/movies"
    )

    for req in requests:
        fe = fg.add_entry()
        fe.id(f"movie-{req['tmdb_id']}")
        fe.title(f"{req['title']} ({req['year']})" if req['year'] else req['title'])
        fe.description(req['overview'] or "No description available")

        # Radarr uses GUID for matching - include TMDB ID
        guid = f"tmdb-{req['tmdb_id']}"
        if req['imdb_id']:
            guid = req['imdb_id']
        fe.guid(guid, permalink=False)

        # Add link to TMDB page
        fe.link(href=f"https://www.themoviedb.org/movie/{req['tmdb_id']}")

        # Publication date
        if req['created_at']:
            try:
                pub_date = datetime.fromisoformat(req['created_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pub_date = datetime.now(timezone.utc)
        else:
            pub_date = datetime.now(timezone.utc)
        fe.pubDate(pub_date)

    return fg.rss_str(pretty=True).decode('utf-8')


async def generate_tv_rss(base_url: str) -> str:
    """Generate RSS feed for TV show requests (Sonarr compatible)."""
    requests = await get_all_requests(media_type="tv")

    fg = create_feed_generator(
        title="Overseer Lite - TV Show Requests",
        description="TV show requests from Overseer Lite",
        link=f"{base_url}/rss/tv"
    )

    for req in requests:
        fe = fg.add_entry()
        fe.id(f"tv-{req['tmdb_id']}")
        fe.title(f"{req['title']} ({req['year']})" if req['year'] else req['title'])
        fe.description(req['overview'] or "No description available")

        # Sonarr prefers TVDB ID for matching
        guid = f"tvdb-{req['tvdb_id']}" if req['tvdb_id'] else f"tmdb-{req['tmdb_id']}"
        fe.guid(guid, permalink=False)

        # Add link to TMDB page
        fe.link(href=f"https://www.themoviedb.org/tv/{req['tmdb_id']}")

        # Publication date
        if req['created_at']:
            try:
                pub_date = datetime.fromisoformat(req['created_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pub_date = datetime.now(timezone.utc)
        else:
            pub_date = datetime.now(timezone.utc)
        fe.pubDate(pub_date)

    return fg.rss_str(pretty=True).decode('utf-8')


async def generate_combined_rss(base_url: str) -> str:
    """Generate combined RSS feed for all requests."""
    requests = await get_all_requests()

    fg = create_feed_generator(
        title="Overseer Lite - All Requests",
        description="All media requests from Overseer Lite",
        link=f"{base_url}/rss/all"
    )

    for req in requests:
        fe = fg.add_entry()
        fe.id(f"{req['media_type']}-{req['tmdb_id']}")

        type_label = "Movie" if req['media_type'] == "movie" else "TV"
        fe.title(f"[{type_label}] {req['title']} ({req['year']})" if req['year'] else f"[{type_label}] {req['title']}")
        fe.description(req['overview'] or "No description available")

        # Use appropriate ID for GUID
        if req['media_type'] == "movie" and req['imdb_id']:
            guid = req['imdb_id']
        elif req['media_type'] == "tv" and req['tvdb_id']:
            guid = f"tvdb-{req['tvdb_id']}"
        else:
            guid = f"tmdb-{req['tmdb_id']}"
        fe.guid(guid, permalink=False)

        # Add link to TMDB page
        fe.link(href=f"https://www.themoviedb.org/{req['media_type']}/{req['tmdb_id']}")

        # Publication date
        if req['created_at']:
            try:
                pub_date = datetime.fromisoformat(req['created_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pub_date = datetime.now(timezone.utc)
        else:
            pub_date = datetime.now(timezone.utc)
        fe.pubDate(pub_date)

    return fg.rss_str(pretty=True).decode('utf-8')
