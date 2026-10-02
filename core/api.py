import aiohttp
import discord

from .config import config
from .embeds import make_embed


class BackendError(Exception):
    pass


class BackendNotConfigured(BackendError):
    pass


class BackendUnauthorized(BackendError):
    pass


class Backend:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def _request(
        self, method: str, path: str, payload: dict | None = None, auth: bool = True
    ) -> tuple[int, dict]:
        if not config.api_url or (auth and not config.api_key):
            raise BackendNotConfigured()

        body = {"key": config.api_key, **(payload or {})} if auth else None
        try:
            async with self._get_session().request(method, f"{config.api_url}{path}", json=body) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {}
                status = resp.status
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise BackendError(str(exc)) from exc

        if status == 401:
            raise BackendUnauthorized()
        if status >= 500 or status == 429:
            raise BackendError(f"HTTP {status}")
        return status, data if isinstance(data, dict) else {}

    async def add_admin(self, user_id: str, name: str) -> bool:
        status, _ = await self._request("POST", "/addadmin", {"id": user_id, "name": name})
        return status == 200

    async def remove_admin(self, user_id: str) -> bool:
        status, _ = await self._request("POST", "/removeadmin", {"id": user_id})
        return status == 200

    async def set_server_data(self, data: dict) -> bool:
        status, _ = await self._request("POST", "/setserverdata", {"data": data})
        return status == 200

    async def admin_ids(self) -> set[str]:
        status, data = await self._request("GET", "/serverdata", auth=False)
        admins = data.get("admins", []) if status == 200 else []
        return {a.get("user-id") for a in admins if isinstance(a, dict)}


backend = Backend()


def backend_error_embed(error: BackendError) -> discord.Embed:
    if isinstance(error, BackendNotConfigured):
        return make_embed(
            "The backend is not configured.",
            "バックエンドが設定されていません。",
            title=("Backend Error", "バックエンドエラー"),
        )
    if isinstance(error, BackendUnauthorized):
        return make_embed(
            "The backend rejected the API key.",
            "バックエンドがAPIキーを拒否しました。",
            title=("Backend Error", "バックエンドエラー"),
        )
    return make_embed(
        "Could not reach the backend. Please try again later.",
        "バックエンドに接続できませんでした。後でもう一度お試しください。",
        title=("Backend Error", "バックエンドエラー"),
    )
