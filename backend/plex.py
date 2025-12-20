"""
Plex webhook payload parsing and ID extraction.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class PlexMedia:
    """Parsed media information from Plex webhook."""
    media_type: str          # "movie" or "tv" (normalized)
    plex_type: str           # Original Plex type (movie, show, season, episode)
    title: str
    year: Optional[int]
    tmdb_id: Optional[int]
    tvdb_id: Optional[int]
    imdb_id: Optional[str]
    plex_guid: Optional[str]  # Show-level Plex GUID for caching
    episode_tvdb_id: Optional[int]  # For episodes: the episode's TVDB ID (for reverse lookup)


def parse_guid_list(guids: list[dict]) -> dict:
    """
    Parse Plex Guid array to extract external IDs.

    Example input:
    [
        {"id": "tmdb://12345"},
        {"id": "tvdb://67890"},
        {"id": "imdb://tt1234567"}
    ]
    """
    result = {
        'tmdb_id': None,
        'tvdb_id': None,
        'imdb_id': None
    }

    for guid in guids:
        guid_str = guid.get('id', '')

        if guid_str.startswith('tmdb://'):
            try:
                result['tmdb_id'] = int(guid_str[7:])
            except ValueError:
                pass
        elif guid_str.startswith('tvdb://'):
            try:
                result['tvdb_id'] = int(guid_str[7:])
            except ValueError:
                pass
        elif guid_str.startswith('imdb://'):
            result['imdb_id'] = guid_str[7:]

    return result


def parse_plex_payload(payload: dict) -> Optional[PlexMedia]:
    """
    Parse a Plex webhook payload and extract media information.

    Returns None if the payload cannot be parsed or is not relevant.

    Handles:
    - movie: Direct match, uses guid
    - show: Direct match, uses guid
    - season: Uses parentGuid for show-level Plex GUID
    - episode: Uses grandparentGuid for show-level Plex GUID
    """
    metadata = payload.get('Metadata', {})
    plex_type = metadata.get('type', '')

    # Extract the show-level Plex GUID for caching
    plex_guid = None

    # Track if this is an episode (for TVDB reverse lookup)
    episode_tvdb_id = None

    # Map Plex types to our media types
    if plex_type == 'movie':
        media_type = 'movie'
        title = metadata.get('title', 'Unknown')
        year = metadata.get('year')
        # For movies, the guid is the movie's own GUID
        plex_guid = metadata.get('guid')

    elif plex_type == 'show':
        media_type = 'tv'
        title = metadata.get('title', 'Unknown')
        year = metadata.get('year')
        # For shows, the guid is the show's own GUID
        plex_guid = metadata.get('guid')

    elif plex_type == 'season':
        # For seasons, get the show info from parent
        media_type = 'tv'
        title = metadata.get('parentTitle', 'Unknown')
        year = metadata.get('parentYear')
        # parentGuid is the show's Plex GUID
        plex_guid = metadata.get('parentGuid')

    elif plex_type == 'episode':
        # For episodes, get the show (grandparent) info
        media_type = 'tv'
        title = metadata.get('grandparentTitle', 'Unknown')
        year = metadata.get('grandparentYear')
        # grandparentGuid is the show's Plex GUID
        plex_guid = metadata.get('grandparentGuid')

    else:
        # Unsupported type (music, photo, etc.)
        return None

    # Extract GUIDs from the Guid array (these are item-level, not show-level)
    guids = metadata.get('Guid', [])
    ids = parse_guid_list(guids)

    # For episodes, save the episode's TVDB ID for reverse lookup
    if plex_type == 'episode' and ids['tvdb_id']:
        episode_tvdb_id = ids['tvdb_id']
        # Clear tvdb_id since it's episode-level, not show-level
        ids['tvdb_id'] = None

    # For seasons, clear the IDs since they're season-level, not show-level
    if plex_type == 'season':
        ids['tmdb_id'] = None
        ids['tvdb_id'] = None

    return PlexMedia(
        media_type=media_type,
        plex_type=plex_type,
        title=title,
        year=year,
        tmdb_id=ids['tmdb_id'],
        tvdb_id=ids['tvdb_id'],
        imdb_id=ids['imdb_id'],
        plex_guid=plex_guid,
        episode_tvdb_id=episode_tvdb_id
    )
