import discord

from .config import config
from .privacy import scrub_text

REGULAR = discord.Color(config.embed_regular)
SUCCESS = discord.Color(config.embed_success)
WARNING = discord.Color(config.embed_warning)
ERROR = discord.Color(config.embed_error)


def bilingual(en: str, ja: str) -> str:
    return f"{en}\n{ja}"


def make_embed(
    en: str,
    ja: str,
    title: tuple[str, str] | None = None,
    color: discord.Color = REGULAR,
) -> discord.Embed:
    embed = discord.Embed(description=scrub_text(bilingual(en, ja)), color=color)
    if title:
        embed.title = scrub_text(f"{title[0]} / {title[1]}")
    return embed
