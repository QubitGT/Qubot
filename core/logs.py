import logging

import discord
from discord.ext import commands

from .config import config

log = logging.getLogger("qubot")


async def send_log(bot: commands.Bot, embed: discord.Embed):
    if not config.console_log_channel:
        return
    try:
        channel = bot.get_channel(config.console_log_channel) or await bot.fetch_channel(config.console_log_channel)
        await channel.send(embed=embed)
    except discord.DiscordException:
        log.exception("Failed to send log message")
