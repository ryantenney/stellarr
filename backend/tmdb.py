import httpx
from config import get_settings

settings = get_settings()


class TMDBClient:
    def __init__(self):
        self.base_url = settings.tmdb_base_url
        self.api_key = settings.tmdb_api_key

    async def _request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a request to the TMDB API."""
        if params is None:
            params = {}
        params["api_key"] = self.api_key

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{endpoint}",
                params=params,
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

    async def search_multi(self, query: str, page: int = 1) -> dict:
        """Search for movies and TV shows."""
        return await self._request("/search/multi", {
            "query": query,
            "page": page,
            "include_adult": "false"
        })

    async def search_movie(self, query: str, page: int = 1, year: int | None = None) -> dict:
        """Search for movies."""
        params = {"query": query, "page": page}
        if year:
            params["year"] = year
        return await self._request("/search/movie", params)

    async def search_tv(self, query: str, page: int = 1, year: int | None = None) -> dict:
        """Search for TV shows."""
        params = {"query": query, "page": page}
        if year:
            params["first_air_date_year"] = year
        return await self._request("/search/tv", params)

    async def get_movie(self, movie_id: int) -> dict:
        """Get movie details including external IDs."""
        return await self._request(f"/movie/{movie_id}", {
            "append_to_response": "external_ids"
        })

    async def get_tv(self, tv_id: int) -> dict:
        """Get TV show details including external IDs."""
        return await self._request(f"/tv/{tv_id}", {
            "append_to_response": "external_ids"
        })

    async def get_trending(self, media_type: str = "all", time_window: str = "week") -> dict:
        """Get trending movies/TV shows."""
        return await self._request(f"/trending/{media_type}/{time_window}")

    async def get_popular_movies(self, page: int = 1) -> dict:
        """Get popular movies."""
        return await self._request("/movie/popular", {"page": page})

    async def get_popular_tv(self, page: int = 1) -> dict:
        """Get popular TV shows."""
        return await self._request("/tv/popular", {"page": page})

tmdb_client = TMDBClient()
