import itertools

import discord
from discord.ext import commands, tasks

from core.config import config


class Presence(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cycle = itertools.cycle(("latency", "prefix", "service"))

    async def cog_load(self):
        self.rotate.start()

    async def cog_unload(self):
        self.rotate.cancel()

    def _text(self, key: str) -> str:
        if key == "latency":
            return f"{round(self.bot.latency * 1000)}ms latency"
        if key == "prefix":
            return f"Prefix: {config.prefix}"
        return "Automated service bot"

    @tasks.loop(minutes=1)
    async def rotate(self):
        activity = discord.Streaming(name=self._text(next(self.cycle)), url=config.stream_url)
        await self.bot.change_presence(activity=activity)

    @rotate.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Presence(bot))
