import logging
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.embeds import make_embed
from core.permissions import MissingRole

log = logging.getLogger("qubot")


class Qubot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # q!プレフィックスに必要（開発者ポータルで有効化すること）
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.prefix),
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self):
        for path in sorted(Path(__file__).parent.joinpath("cogs").glob("*.py")):
            if path.stem.startswith("_"):
                continue
            try:
                await self.load_extension(f"cogs.{path.stem}")
                log.info("Loaded cog: %s", path.stem)
            except Exception:
                log.exception("Failed to load cog: %s", path.stem)

        if config.dev_guild_id:
            guild = discord.Object(config.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    @staticmethod
    def _error_embed(error: Exception) -> discord.Embed | None:
        if isinstance(error, commands.MissingPermissions):
            names = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
            return make_embed(
                f"You need the following permissions: **{names}**",
                f"次の権限が必要です：**{names}**",
                title=("Permission Denied", "権限がありません"),
            )
        if isinstance(error, MissingRole):
            names = ", ".join(str(r) for r in error.roles)
            return make_embed(
                f"You need one of these roles: **{names}**",
                f"次のいずれかのロールが必要です：**{names}**",
                title=("Permission Denied", "権限がありません"),
            )
        if isinstance(error, commands.NoPrivateMessage):
            return make_embed(
                "This command can only be used in a server.",
                "このコマンドはサーバー内でのみ使用できます。",
                title=("Server Only", "サーバー専用"),
            )
        if isinstance(error, commands.CommandNotFound):
            return None
        if isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
            return make_embed(
                f"Slow down! Try again in {error.retry_after:.1f}s.",
                f"少し待ってください！{error.retry_after:.1f}秒後にもう一度お試しください。",
                title=("Cooldown", "クールダウン"),
            )
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            return make_embed(
                "Invalid or missing arguments.",
                "引数が無効、または不足しています。",
                title=("Invalid Input", "入力エラー"),
            )
        if isinstance(error, (commands.CheckFailure, app_commands.CheckFailure)):
            return make_embed(
                "You can't use this command here.",
                "ここではこのコマンドを使用できません。",
                title=("Not Allowed", "許可されていません"),
            )
        log.error("Unhandled command error", exc_info=error)
        return make_embed(
            "Something went wrong.",
            "問題が発生しました。",
            title=("Error", "エラー"),
        )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandInvokeError):
            error = error.original
        embed = self._error_embed(error)
        if embed:
            await ctx.reply(embed=embed, mention_author=False, ephemeral=True)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = self._error_embed(error)
        if not embed:
            return
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.token:
        sys.exit("DISCORD_TOKEN is missing. Copy .env.example to .env and fill it in.")
    Qubot().run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
