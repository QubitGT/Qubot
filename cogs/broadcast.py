import re

import discord
from discord.ext import commands

from cogs.console import ALLOWED_ROLES
from core.api import BackendError, backend, backend_error_embed
from core.config import config
from core.embeds import SUCCESS, make_embed
from core.logs import send_log
from core.permissions import requires

SERVER_PREFIX = "<color=grey>[</color><color=#a07afa>SERVER</color><color=grey>]</color> "
MAX_MESSAGE = 200


def clean_code(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", raw).upper()[:12]


class Broadcast(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="notification",
        description="Send a live notification to all connected players. / 接続中の全プレイヤーに通知を送信します。",
    )
    @requires(roles=ALLOWED_ROLES)
    async def notification(
        self, ctx: commands.Context, message: str, format: bool = False, seconds: commands.Range[int, 1, 60] = 5
    ):
        await ctx.defer()

        text = (SERVER_PREFIX if format else "") + message.strip()[:MAX_MESSAGE]
        try:
            ok = await backend.notify(text, seconds)
        except BackendError as exc:
            return await ctx.reply(embed=backend_error_embed(exc), mention_author=False)

        if not ok:
            return await ctx.reply(
                embed=make_embed("The backend refused the notification.", "バックエンドが通知を拒否しました。", title=("Failed", "失敗")),
                mention_author=False,
            )

        await send_log(
            self.bot,
            make_embed(
                f"{ctx.author} (`{ctx.author.id}`) sent a notification:\n```{text}```",
                f"{ctx.author} (`{ctx.author.id}`) が通知を送信しました：\n```{text}```",
                title=("Notification Sent", "通知送信"),
            ),
        )
        await ctx.reply(
            embed=make_embed(
                f"Notification sent:\n```{text}```",
                f"通知を送信しました：\n```{text}```",
                title=("Notification Sent", "通知送信"),
                color=SUCCESS,
            ),
            mention_author=False,
        )

    @commands.hybrid_command(
        name="users",
        description="Show how many players are connected. / 接続中のプレイヤー数を表示します。",
    )
    async def users(self, ctx: commands.Context):
        await ctx.defer()

        try:
            count = await backend.user_count()
        except BackendError as exc:
            return await ctx.reply(embed=backend_error_embed(exc), mention_author=False)

        if count is None:
            return await ctx.reply(
                embed=make_embed("The backend returned no user count.", "バックエンドがユーザー数を返しませんでした。", title=("Failed", "失敗")),
                mention_author=False,
            )

        await ctx.reply(
            embed=make_embed(
                f"**{count}** players connected.",
                f"現在 **{count}** 人が接続中です。",
                title=("Users", "ユーザー"),
            ),
            mention_author=False,
        )

    @commands.hybrid_command(
        name="invite",
        description="Invite connected players to a code. / 接続中のプレイヤーをコードに招待します。",
    )
    @requires(users=config.bot_administration)
    async def invite(self, ctx: commands.Context, code: str, count: commands.Range[int, 1, 1000] = None):
        await ctx.defer()

        code = clean_code(code)
        if not code:
            return await ctx.reply(
                embed=make_embed("That is not a valid code.", "無効なコードです。", title=("Invalid Code", "無効なコード")),
                mention_author=False,
            )

        try:
            ok = await backend.invite(code, count)
        except BackendError as exc:
            return await ctx.reply(embed=backend_error_embed(exc), mention_author=False)

        if not ok:
            return await ctx.reply(
                embed=make_embed("The backend refused the invite.", "バックエンドが招待を拒否しました。", title=("Failed", "失敗")),
                mention_author=False,
            )

        who_en = f"{count} random players" if count else "all players"
        who_ja = f"ランダムな{count}人" if count else "全プレイヤー"
        await send_log(
            self.bot,
            make_embed(
                f"{ctx.author} (`{ctx.author.id}`) invited {who_en} to `{code}`.",
                f"{ctx.author} (`{ctx.author.id}`) が{who_ja}を `{code}` に招待しました。",
                title=("Invite Sent", "招待送信"),
            ),
        )
        await ctx.reply(
            embed=make_embed(
                f"Invited {who_en} to `{code}`.",
                f"{who_ja}を `{code}` に招待しました。",
                title=("Invite Sent", "招待送信"),
                color=SUCCESS,
            ),
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Broadcast(bot))
