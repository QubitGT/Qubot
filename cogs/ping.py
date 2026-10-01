from discord.ext import commands

from core.embeds import make_embed


class Ping(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Check if the bot is alive. / ボットが動いているか確認します。")
    async def ping(self, ctx: commands.Context):
        ms = round(self.bot.latency * 1000)
        await ctx.reply(
            embed=make_embed(
                f"Pong! Latency: **{ms}ms**",
                f"ポン！レイテンシ：**{ms}ms**",
                title=("Ping", "ピング"),
            ),
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Ping(bot))
