import contextlib
import logging
import time

import discord
from discord.ext import commands, tasks

from core.config import config
from core.embeds import WARNING, make_embed

log = logging.getLogger("qubot.honeypot")

SWEEP_HISTORY_LIMIT = 1000
RECENT_SECONDS = 60
KICK_REASON = "Honeypot channel / ハニーポットチャンネル"


def warning_embed() -> discord.Embed:
    return make_embed(
        "Your account appears to be compromised. You have been removed from the server for sending a message in a "
        "restricted channel. Please check your computer for malicious applications, scan it for malware and change "
        "your passwords before rejoining.",
        "あなたのアカウントは乗っ取られている可能性があります。制限されたチャンネルにメッセージを送信したため、"
        "サーバーから退出させられました。再参加する前に、パソコンに悪意のあるアプリケーションがないか確認し、"
        "マルウェアのスキャンを行い、パスワードを変更してください。",
        title=("Account Compromised", "アカウントが乗っ取られています"),
        color=WARNING,
    )


class Honeypot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active: set[int] = set()
        self.recent: dict[int, float] = {}

    async def cog_load(self):
        if config.honeypot_channel:
            self.sweep.start()

    async def cog_unload(self):
        self.sweep.cancel()

    def _recently_handled(self, user_id: int) -> bool:
        now = time.monotonic()
        self.recent = {u: t for u, t in self.recent.items() if now - t < RECENT_SECONDS}
        return user_id in self.recent

    @staticmethod
    def _kickable(guild: discord.Guild, member: discord.Member) -> bool:
        me = guild.me
        return (
            me.guild_permissions.kick_members
            and member.id != guild.owner_id
            and member.id != me.id
            and member.top_role < me.top_role
        )

    @staticmethod
    async def _delete(messages: list[discord.Message]):
        for message in messages:
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                log.warning("Could not delete a honeypot message (check Manage Messages in the channel)")

    async def _trap(self, guild: discord.Guild, user_id: int, messages: list[discord.Message]):
        await self._delete(messages)
        if user_id in self.active or self._recently_handled(user_id):
            return

        self.active.add(user_id)
        try:
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    return

            if not self._kickable(guild, member):
                log.warning("Could not act on honeypot user %s (permissions or role hierarchy)", user_id)
                return

            with contextlib.suppress(discord.HTTPException):
                await member.send(embed=warning_embed())

            try:
                await member.kick(reason=KICK_REASON)
                log.info("Kicked %s for messaging the honeypot channel", user_id)
            except discord.HTTPException:
                log.warning("Could not kick honeypot user %s", user_id)
        except Exception:
            log.exception("Unexpected error handling a honeypot message")
        finally:
            self.active.discard(user_id)
            self.recent[user_id] = time.monotonic()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not config.honeypot_channel or message.channel.id != config.honeypot_channel:
            return
        if message.guild is None or message.author.bot or message.webhook_id is not None:
            return
        await self._trap(message.guild, message.author.id, [message])

    @tasks.loop(hours=1)
    async def sweep(self):
        try:
            channel = self.bot.get_channel(config.honeypot_channel) or await self.bot.fetch_channel(config.honeypot_channel)
            by_author: dict[int, list[discord.Message]] = {}
            async for message in channel.history(limit=SWEEP_HISTORY_LIMIT):
                if message.author.bot or message.webhook_id is not None:
                    continue
                by_author.setdefault(message.author.id, []).append(message)
            for user_id, messages in by_author.items():
                await self._trap(channel.guild, user_id, messages)
        except discord.HTTPException as exc:
            log.error("Honeypot sweep failed: HTTP %s", exc.status)
        except Exception:
            log.exception("Honeypot sweep failed")

    @sweep.before_loop
    async def before_sweep(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Honeypot(bot))
