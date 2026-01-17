#!/usr/bin/env python3
"""
Compare two Plex movie libraries to find items only in one.

Requirements:
    pip install plexapi

Usage:
    python compare-libraries.py --plex-url http://localhost:32400 --plex-token YOUR_TOKEN
"""
import argparse
import os
import sys

try:
    from plexapi.server import PlexServer
except ImportError:
    print("Error: 'plexapi' package not found. Install with: pip install plexapi")
    sys.exit(1)


def get_movies_from_library(section) -> dict[int, str]:
    """Get dict of tmdb_id -> title from a library section."""
    movies = {}
    for item in section.all():
        for guid in item.guids:
            if guid.id.startswith("tmdb://"):
                try:
                    tmdb_id = int(guid.id[7:])
                    movies[tmdb_id] = item.title
                except ValueError:
                    pass
                break
    return movies


def main():
    parser = argparse.ArgumentParser(description="Compare Plex movie libraries")
    parser.add_argument("--plex-url", default=os.environ.get("PLEX_URL", "http://localhost:32400"))
    parser.add_argument("--plex-token", default=os.environ.get("PLEX_TOKEN"))
    parser.add_argument("--lib1", default="4K Movies", help="First library name")
    parser.add_argument("--lib2", default="Movies", help="Second library name")
    args = parser.parse_args()

    if not args.plex_token:
        print("Error: Plex token required. Use --plex-token or set PLEX_TOKEN env var.")
        sys.exit(1)

    print(f"Connecting to Plex at {args.plex_url}...")
    plex = PlexServer(args.plex_url, args.plex_token)
    print(f"Connected to: {plex.friendlyName}\n")

    # Find the library sections
    lib1_section = None
    lib2_section = None

    for section in plex.library.sections():
        if section.title == args.lib1:
            lib1_section = section
        elif section.title == args.lib2:
            lib2_section = section

    if not lib1_section:
        print(f"Error: Library '{args.lib1}' not found")
        sys.exit(1)
    if not lib2_section:
        print(f"Error: Library '{args.lib2}' not found")
        sys.exit(1)

    print(f"Scanning '{args.lib1}'...")
    lib1_movies = get_movies_from_library(lib1_section)
    print(f"  Found {len(lib1_movies)} movies")

    print(f"Scanning '{args.lib2}'...")
    lib2_movies = get_movies_from_library(lib2_section)
    print(f"  Found {len(lib2_movies)} movies")

    # Find movies only in lib1
    only_in_lib1 = {tmdb_id: title for tmdb_id, title in lib1_movies.items() if tmdb_id not in lib2_movies}

    # Find movies only in lib2
    only_in_lib2 = {tmdb_id: title for tmdb_id, title in lib2_movies.items() if tmdb_id not in lib1_movies}

    print(f"\n{'='*60}")
    print(f"Movies ONLY in '{args.lib1}' ({len(only_in_lib1)}):")
    print(f"{'='*60}")
    for tmdb_id, title in sorted(only_in_lib1.items(), key=lambda x: x[1]):
        print(f"  {title} (TMDB: {tmdb_id})")

    print(f"\n{'='*60}")
    print(f"Movies ONLY in '{args.lib2}' ({len(only_in_lib2)}):")
    print(f"{'='*60}")
    for tmdb_id, title in sorted(only_in_lib2.items(), key=lambda x: x[1]):
        print(f"  {title} (TMDB: {tmdb_id})")

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  {args.lib1}: {len(lib1_movies)} total, {len(only_in_lib1)} unique")
    print(f"  {args.lib2}: {len(lib2_movies)} total, {len(only_in_lib2)} unique")
    print(f"  In both: {len(lib1_movies) - len(only_in_lib1)}")


if __name__ == "__main__":
    main()
