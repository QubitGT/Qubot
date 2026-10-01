import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    token: str = os.getenv("DISCORD_TOKEN", "")
    prefix: str = os.getenv("PREFIX", "q!")
    dev_guild_id: int | None = int(os.getenv("DEV_GUILD_ID") or 0) or None
    stream_url: str = os.getenv("STREAM_URL") or "https://www.twitch.tv/discord"


config = Config()
