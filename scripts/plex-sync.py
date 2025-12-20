#!/usr/bin/env python3
"""
Sync Plex library to Overseer Lite.

This script reads your Plex library and syncs the TMDB/TVDB IDs to Overseer,
enabling "In Library" badges on search results and marking existing requests as added.

Run on the Plex server or any machine with network access to Plex.

Requirements:
    pip install plexapi requests

Usage:
    python plex-sync.py --plex-url http://localhost:32400 --plex-token YOUR_PLEX_TOKEN \
        --overseer-url https://overseer.example.com --sync-token YOUR_SYNC_TOKEN

Or via environment variables:
    export PLEX_URL=http://localhost:32400
    export PLEX_TOKEN=your_plex_token
    export OVERSEER_URL=https://overseer.example.com
    export OVERSEER_SYNC_TOKEN=your_plex_webhook_token
    python plex-sync.py

To find your Plex token:
    1. Open Plex Web App, navigate to any media item
    2. Click the three dots (...) and select "Get Info"
    3. Click "View XML" at the bottom
    4. Look for "X-Plex-Token=" in the URL
"""
import argparse
import os
import sys

try:
    import requests
except ImportError:
    print("Error: 'requests' package not found. Install with: pip install requests")
    sys.exit(1)

try:
    from plexapi.server import PlexServer
except ImportError:
    print("Error: 'plexapi' package not found. Install with: pip install plexapi")
    sys.exit(1)


def get_library_items(plex: PlexServer, library_type: str, verbose: bool = False) -> list[dict]:
    """
    Extract TMDB/TVDB IDs from Plex library.

    Args:
        plex: PlexServer instance
        library_type: "movie" or "tv"
        verbose: Print progress information

    Returns:
        List of dicts with tmdb_id, tvdb_id, and title
    """
    items = []
    section_type = "movie" if library_type == "movie" else "show"

    for section in plex.library.sections():
        if section.type != section_type:
            continue

        if verbose:
            print(f"  Processing library section: {section.title}")

        for item in section.all():
            tmdb_id = None
            tvdb_id = None

            # Extract IDs from guids
            for guid in item.guids:
                if guid.id.startswith("tmdb://"):
                    try:
                        tmdb_id = int(guid.id[7:])
                    except ValueError:
                        pass
                elif guid.id.startswith("tvdb://"):
                    try:
                        tvdb_id = int(guid.id[7:])
                    except ValueError:
                        pass

            # Only include items with TMDB ID (required for matching)
            if tmdb_id:
                items.append({
                    "tmdb_id": tmdb_id,
                    "tvdb_id": tvdb_id,
                    "title": item.title
                })
            elif verbose:
                print(f"    Skipping '{item.title}' - no TMDB ID found")

    return items


def sync_to_overseer(
    items: list[dict],
    media_type: str,
    overseer_url: str,
    sync_token: str,
    batch_size: int = 100,
    verbose: bool = False
) -> dict:
    """
    POST library items to Overseer sync endpoint in batches.

    Args:
        items: List of library items
        media_type: "movie" or "tv"
        overseer_url: Base URL of Overseer instance
        sync_token: Plex webhook token for authentication
        batch_size: Number of items per request
        verbose: Print progress information

    Returns:
        Aggregated response with total counts
    """
    url = f"{overseer_url.rstrip('/')}/sync/library"
    params = {
        "media_type": media_type,
        "token": sync_token
    }

    total_synced = 0
    total_marked = 0

    # Split into batches
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(items) + batch_size - 1) // batch_size
        is_first_batch = (i == 0)

        if verbose:
            print(f"    Sending batch {batch_num}/{total_batches} ({len(batch)} items)...")

        # Clear existing items only on first batch
        batch_params = params.copy()
        if is_first_batch:
            batch_params["clear"] = "true"

        response = requests.post(
            url,
            params=batch_params,
            json=batch,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        total_synced += result.get('synced', 0)
        total_marked += result.get('marked_as_added', 0)

    return {
        "synced": total_synced,
        "marked_as_added": total_marked,
        "media_type": media_type
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sync Plex library to Overseer Lite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--plex-url",
        default=os.environ.get("PLEX_URL", "http://localhost:32400"),
        help="Plex server URL (default: http://localhost:32400 or PLEX_URL env var)"
    )
    parser.add_argument(
        "--plex-token",
        default=os.environ.get("PLEX_TOKEN"),
        help="Plex authentication token (or PLEX_TOKEN env var)"
    )
    parser.add_argument(
        "--overseer-url",
        default=os.environ.get("OVERSEER_URL"),
        help="Overseer Lite base URL (or OVERSEER_URL env var)"
    )
    parser.add_argument(
        "--sync-token",
        default=os.environ.get("OVERSEER_SYNC_TOKEN"),
        help="Overseer sync token - same as PLEX_WEBHOOK_TOKEN (or OVERSEER_SYNC_TOKEN env var)"
    )
    parser.add_argument(
        "--movies-only",
        action="store_true",
        help="Only sync movies, skip TV shows"
    )
    parser.add_argument(
        "--tv-only",
        action="store_true",
        help="Only sync TV shows, skip movies"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print detailed progress information"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of items per batch request (default: 100)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without actually syncing"
    )

    args = parser.parse_args()

    # Validate required arguments
    if not args.plex_token:
        print("Error: Plex token is required. Use --plex-token or set PLEX_TOKEN env var.")
        sys.exit(1)

    if not args.overseer_url:
        print("Error: Overseer URL is required. Use --overseer-url or set OVERSEER_URL env var.")
        sys.exit(1)

    if not args.sync_token:
        print("Error: Sync token is required. Use --sync-token or set OVERSEER_SYNC_TOKEN env var.")
        sys.exit(1)

    if args.movies_only and args.tv_only:
        print("Error: Cannot specify both --movies-only and --tv-only")
        sys.exit(1)

    # Connect to Plex
    print(f"Connecting to Plex at {args.plex_url}...")
    try:
        plex = PlexServer(args.plex_url, args.plex_token)
        print(f"Connected to: {plex.friendlyName}")
    except Exception as e:
        print(f"Error connecting to Plex: {e}")
        sys.exit(1)

    # Sync movies
    if not args.tv_only:
        print("\nScanning movie libraries...")
        movies = get_library_items(plex, "movie", args.verbose)
        print(f"Found {len(movies)} movies with TMDB IDs")

        if args.dry_run:
            print("(Dry run - not syncing)")
            if args.verbose and movies:
                print("Sample items:")
                for item in movies[:5]:
                    print(f"  - {item['title']} (TMDB: {item['tmdb_id']})")
        else:
            print("Syncing movies to Overseer...")
            try:
                result = sync_to_overseer(
                    movies, "movie", args.overseer_url, args.sync_token,
                    batch_size=args.batch_size, verbose=args.verbose
                )
                print(f"Synced {result.get('synced', 0)} movies")
                if result.get('marked_as_added', 0) > 0:
                    print(f"Marked {result['marked_as_added']} requests as added")
            except requests.exceptions.RequestException as e:
                print(f"Error syncing movies: {e}")

    # Sync TV shows
    if not args.movies_only:
        print("\nScanning TV show libraries...")
        shows = get_library_items(plex, "tv", args.verbose)
        print(f"Found {len(shows)} TV shows with TMDB IDs")

        if args.dry_run:
            print("(Dry run - not syncing)")
            if args.verbose and shows:
                print("Sample items:")
                for item in shows[:5]:
                    print(f"  - {item['title']} (TMDB: {item['tmdb_id']}, TVDB: {item.get('tvdb_id', 'N/A')})")
        else:
            print("Syncing TV shows to Overseer...")
            try:
                result = sync_to_overseer(
                    shows, "tv", args.overseer_url, args.sync_token,
                    batch_size=args.batch_size, verbose=args.verbose
                )
                print(f"Synced {result.get('synced', 0)} TV shows")
                if result.get('marked_as_added', 0) > 0:
                    print(f"Marked {result['marked_as_added']} requests as added")
            except requests.exceptions.RequestException as e:
                print(f"Error syncing TV shows: {e}")

    print("\nSync complete!")


if __name__ == "__main__":
    main()
