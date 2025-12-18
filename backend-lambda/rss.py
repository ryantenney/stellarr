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


def _get_pub_date(created_at) -> datetime:
    """Parse publication date from created_at timestamp."""
    if created_at:
        if isinstance(created_at, datetime):
            return created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
        try:
            return datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    return datetime.now(timezone.utc)


def generate_movie_rss(base_url: str) -> str:
    """Generate RSS feed for movie requests (Radarr compatible)."""
    requests = get_all_requests(media_type="movie")

    fg = create_feed_generator(
        title="Overseer Lite - Movie Requests",
        description="Movie requests from Overseer Lite for Radarr",
        link=f"{base_url}/rss/movies"
    )

    for req in requests:
        fe = fg.add_entry()
        title = f"{req['title']} ({req['year']})" if req['year'] else req['title']
        fe.title(title)
        fe.id(f"movie-{req['tmdb_id']}")
        fe.description(req['overview'] or "No description available")

        if req['imdb_id']:
            fe.guid(req['imdb_id'], permalink=False)
        else:
            fe.guid(title, permalink=False)

        fe.link(href=f"https://www.themoviedb.org/movie/{req['tmdb_id']}")
        fe.pubDate(_get_pub_date(req['created_at']))

    return fg.rss_str(pretty=True).decode('utf-8')


def generate_tv_rss(base_url: str) -> str:
    """Generate RSS feed for TV show requests."""
    requests = get_all_requests(media_type="tv")

    fg = create_feed_generator(
        title="Overseer Lite - TV Show Requests",
        description="TV show requests from Overseer Lite",
        link=f"{base_url}/rss/tv"
    )

    for req in requests:
        fe = fg.add_entry()
        title = f"{req['title']} ({req['year']})" if req['year'] else req['title']
        fe.title(title)
        fe.id(f"tv-{req['tmdb_id']}")
        fe.description(req['overview'] or "No description available")

        if req['tvdb_id']:
            fe.guid(f"tvdb-{req['tvdb_id']}", permalink=False)
        else:
            fe.guid(title, permalink=False)

        fe.link(href=f"https://www.themoviedb.org/tv/{req['tmdb_id']}")
        fe.pubDate(_get_pub_date(req['created_at']))

    return fg.rss_str(pretty=True).decode('utf-8')


def generate_combined_rss(base_url: str) -> str:
    """Generate combined RSS feed for all requests."""
    requests = get_all_requests()

    fg = create_feed_generator(
        title="Overseer Lite - All Requests",
        description="All media requests from Overseer Lite",
        link=f"{base_url}/rss/all"
    )

    for req in requests:
        fe = fg.add_entry()
        fe.id(f"{req['media_type']}-{req['tmdb_id']}")

        type_label = "Movie" if req['media_type'] == "movie" else "TV"
        title = f"{req['title']} ({req['year']})" if req['year'] else req['title']
        fe.title(f"[{type_label}] {title}")
        fe.description(req['overview'] or "No description available")

        if req['media_type'] == "movie" and req['imdb_id']:
            fe.guid(req['imdb_id'], permalink=False)
        elif req['media_type'] == "tv" and req['tvdb_id']:
            fe.guid(f"tvdb-{req['tvdb_id']}", permalink=False)
        else:
            fe.guid(title, permalink=False)

        fe.link(href=f"https://www.themoviedb.org/{req['media_type']}/{req['tmdb_id']}")
        fe.pubDate(_get_pub_date(req['created_at']))

    return fg.rss_str(pretty=True).decode('utf-8')


def generate_radarr_json() -> list[dict]:
    """Generate Radarr StevenLu Custom list format (JSON)."""
    requests = get_all_requests(media_type="movie")

    items = []
    for req in requests:
        item = {
            "title": f"{req['title']} ({req['year']})" if req['year'] else req['title'],
        }
        if req['imdb_id']:
            item["imdb_id"] = req['imdb_id']
        if req['poster_path']:
            item["poster_url"] = f"https://image.tmdb.org/t/p/w300{req['poster_path']}"
        items.append(item)

    return items


def generate_sonarr_json() -> list[dict]:
    """Generate Sonarr Custom List format (JSON)."""
    requests = get_all_requests(media_type="tv")

    items = []
    for req in requests:
        if req['tvdb_id']:
            items.append({"tvdbId": str(req['tvdb_id'])})

    return items
