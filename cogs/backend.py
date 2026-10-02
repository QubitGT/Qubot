import json
import time
from pathlib import Path

import discord
from discord.ext import commands

from core.api import BackendError, backend, backend_error_embed
from core.config import config
from core.embeds import make_embed
from core.logs import send_log
from core.permissions import requires

MAX_SERVERDATA_BYTES = 200 * 1024
RESTART_MARKER = Path(__file__).resolve().parent.parent / ".restart.json"
RESTART_MARKER_MAX_AGE = 300


class Backend(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not RESTART_MARKER.exists():
            return
        try:
            marker = json.loads(RESTART_MARKER.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            marker = None
        RESTART_MARKER.unlink(missing_ok=True)
        if not marker:
            return

        elapsed = time.time() - marker["started"]
        if elapsed > RESTART_MARKER_MAX_AGE:
            return
        try:
            channel = self.bot.get_channel(marker["channel_id"]) or await self.bot.fetch_channel(marker["channel_id"])
            message = await channel.fetch_message(marker["message_id"])
            await message.edit(
                embed=make_embed(
                    f"Restarted in {elapsed:.1f}s.",
                    f"{elapsed:.1f}秒で再起動しました。",
                    title=("Restart", "再起動"),
                )
            )
        except discord.DiscordException:
            pass

    @staticmethod
    def _error(en: str, ja: str, title: tuple[str, str]) -> discord.Embed:
        return make_embed(en, ja, title=title)

    @commands.hybrid_group(
        name="backend",
        description="Manage the backend. / バックエンドを管理します。",
        invoke_without_command=True,
    )
    @requires(users=config.bot_administration)
    async def backend_group(self, ctx: commands.Context):
        p = ctx.clean_prefix
        await ctx.reply(
            embed=make_embed(
                f"`{p}backend serverdata <file>`\n`{p}backend restart`",
                f"`{p}backend serverdata <ファイル>`\n`{p}backend restart`",
                title=("Backend", "バックエンド"),
            ),
            mention_author=False,
        )

    @backend_group.command(
        name="serverdata",
        description="Upload a new serverdata.json. / 新しいserverdata.jsonをアップロードします。",
    )
    @requires(users=config.bot_administration)
    async def serverdata(self, ctx: commands.Context, file: discord.Attachment):
        await ctx.defer()

        if file.size > MAX_SERVERDATA_BYTES:
            return await ctx.reply(
                embed=self._error(
                    f"The file is too large (max {MAX_SERVERDATA_BYTES // 1024} KB).",
                    f"ファイルが大きすぎます（最大{MAX_SERVERDATA_BYTES // 1024}KB）。",
                    ("File Too Large", "ファイルが大きすぎます"),
                ),
                mention_author=False,
            )

        try:
            data = json.loads((await file.read()).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return await ctx.reply(
                embed=self._error(
                    "The file is not valid JSON.",
                    "ファイルが有効なJSONではありません。",
                    ("Invalid File", "無効なファイル"),
                ),
                mention_author=False,
            )
        except discord.DiscordException:
            return await ctx.reply(
                embed=self._error(
                    "Could not download the file.",
                    "ファイルをダウンロードできませんでした。",
                    ("Invalid File", "無効なファイル"),
                ),
                mention_author=False,
            )

        if not isinstance(data, dict):
            return await ctx.reply(
                embed=self._error(
                    "The JSON must be an object.",
                    "JSONはオブジェクトである必要があります。",
                    ("Invalid File", "無効なファイル"),
                ),
                mention_author=False,
            )

        try:
            ok = await backend.set_server_data(data)
        except BackendError as exc:
            return await ctx.reply(embed=backend_error_embed(exc), mention_author=False)

        if not ok:
            return await ctx.reply(
                embed=self._error(
                    "The backend refused the data.",
                    "バックエンドがデータを拒否しました。",
                    ("Failed", "失敗"),
                ),
                mention_author=False,
            )

        await send_log(
            self.bot,
            make_embed(
                f"{ctx.author} (`{ctx.author.id}`) uploaded new serverdata (`{file.filename}`).",
                f"{ctx.author} (`{ctx.author.id}`) が新しいserverdata（`{file.filename}`）をアップロードしました。",
                title=("Serverdata Updated", "Serverdata更新"),
            ),
        )
        await ctx.reply(
            embed=make_embed(
                f"Serverdata updated from `{file.filename}`.",
                f"`{file.filename}` からserverdataを更新しました。",
                title=("Serverdata Updated", "Serverdata更新"),
            ),
            mention_author=False,
        )

    @backend_group.command(name="restart", description="Restart the bot. / ボットを再起動します。")
    @requires(users=config.bot_administration)
    async def restart(self, ctx: commands.Context):
        await send_log(
            self.bot,
            make_embed(
                f"{ctx.author} (`{ctx.author.id}`) restarted the bot.",
                f"{ctx.author} (`{ctx.author.id}`) がボットを再起動しました。",
                title=("Bot Restart", "ボット再起動"),
            ),
        )
        message = await ctx.reply(
            embed=make_embed(
                "Restarting...",
                "再起動しています...",
                title=("Restart", "再起動"),
            ),
            mention_author=False,
        )
        RESTART_MARKER.write_text(
            json.dumps({"channel_id": message.channel.id, "message_id": message.id, "started": time.time()}),
            encoding="utf-8",
        )
        self.bot.restart_requested = True
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Backend(bot))
