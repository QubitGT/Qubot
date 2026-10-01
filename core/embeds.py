import discord

COLOR = discord.Color(0xAA64FF)


def bilingual(en: str, ja: str) -> str:
    return f"{en}\n{ja}"


def make_embed(
    en: str,
    ja: str,
    title: tuple[str, str] | None = None,
) -> discord.Embed:
    embed = discord.Embed(description=bilingual(en, ja), color=COLOR)
    if title:
        embed.title = f"{title[0]} / {title[1]}"
    return embed
