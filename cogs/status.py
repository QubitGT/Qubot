from discord.ext import commands

from core import runtime
from core.embeds import make_embed


class Status(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        try:
            runtime.commit = await runtime.git("rev-parse", "--short", "HEAD")
        except Exception:
            runtime.commit = "unknown"

    @commands.hybrid_command(name="status", description="Show the commit and uptime. / コミットと稼働時間を表示します。")
    async def status(self, ctx: commands.Context):
        seconds = runtime.uptime_seconds()
        await ctx.reply(
            embed=make_embed(
                f"Commit: `{runtime.commit}`\nUptime: **{seconds}** seconds",
                f"コミット：`{runtime.commit}`\n稼働時間：**{seconds}**秒",
                title=("Status", "ステータス"),
            ),
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Status(bot))
