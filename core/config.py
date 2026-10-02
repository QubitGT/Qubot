import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _hex_color(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip().lstrip("#")
    try:
        return int(raw, 16) if len(raw) == 6 else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    token: str = os.getenv("DISCORD_TOKEN", "")
    prefix: str = os.getenv("PREFIX", "q!")
    dev_guild_id: int | None = int(os.getenv("DEV_GUILD_ID") or 0) or None
    api_url: str = (os.getenv("MASUTA_API") or "").rstrip("/")
    api_key: str = os.getenv("HIMITSU_KAGI", "")
    console_log_channel: int | None = int(os.getenv("CONSOLE_LOG_CHANNEL") or 0) or None
    bot_administration: frozenset[int] = frozenset(
        int(p) for p in os.getenv("BOT_ADMINISTRATION", "").replace(" ", "").split(",") if p.isdigit()
    )
    embed_regular: int = _hex_color("EMBED_REGULAR", 0xAA64FF)
    embed_success: int = _hex_color("EMBED_SUCCESS", 0x57F287)
    embed_warning: int = _hex_color("EMBED_WARNING", 0xFEE75C)
    embed_error: int = _hex_color("EMBED_ERROR", 0xED4245)
    auto_update: bool = (os.getenv("AUTO_UPDATE") or "true").strip().lower() not in ("0", "false", "no", "off")
    verify_channel: int | None = int(os.getenv("VERIFY_CHANNEL") or 0) or None
    verify_role: int | None = int(os.getenv("VERIFY_ROLE") or 0) or None
    honeypot_channel: int | None = int(os.getenv("HONEYPOT_CHANNEL_ID") or 0) or None
    stream_url: str = os.getenv("STREAM_URL") or "https://www.twitch.tv/discord"


config = Config()
