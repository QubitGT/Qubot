import asyncio
import hmac
import io
import json
import logging
import time
from dataclasses import dataclass

import discord
from discord.ext import commands

from core import captcha
from core.config import config
from core.embeds import ERROR, REGULAR, make_embed
from core.privacy import ROOT

log = logging.getLogger("qubot.verification")

STATE_FILE = ROOT / "data" / "verification.json"

TITLE = "Welcome to Qubit!"
DESCRIPTION = (
    "This server requires authentication to prevent bot activity. To authenticate, please click the checkmark at "
    "the bottom of this message to gain full access to all server channels.\n"
    "このサーバーは、ボットによる不正アクセスを防ぐため、認証が必要です。認証するには、このメッセージの下部にある"
    "チェックマークをクリックして、すべてのサーバーチャンネルへのフルアクセス権を取得してください。"
)

CHALLENGE_SECONDS = 300
MAX_ATTEMPTS = 3
REQUEST_COOLDOWN = 3


@dataclass
class Challenge:
    code: str
    expires: float
    attempts: int = 0


def welcome_embed() -> discord.Embed:
    return discord.Embed(title=TITLE, description=DESCRIPTION, color=REGULAR)


def error_embed(en: str, ja: str) -> discord.Embed:
    return make_embed(en, ja, title=("Verification", "認証"), color=ERROR)


class VerifyView(discord.ui.View):
    def __init__(self, cog: "Verification"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Verify / 認証",
        emoji="✅",
        style=discord.ButtonStyle.primary,
        custom_id="qubot:verify",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.start_challenge(interaction)


class CodeModal(discord.ui.Modal, title="Verification / 認証"):
    code = discord.ui.TextInput(
        label="Code / コード",
        placeholder="ABC123",
        min_length=captcha.LENGTH,
        max_length=captcha.LENGTH,
    )

    def __init__(self, cog: "Verification"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.submit(interaction, str(self.code.value))

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error("Verification modal failed: %s", type(error).__name__)


class ChallengeView(discord.ui.View):
    def __init__(self, cog: "Verification", user_id: int):
        super().__init__(timeout=CHALLENGE_SECONDS)
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Enter Code / コードを入力", style=discord.ButtonStyle.primary)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CodeModal(self.cog))

    @discord.ui.button(label="New Image / 新しい画像", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.refresh_challenge(interaction, self)


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.challenges: dict[int, Challenge] = {}
        self.last_request: dict[int, float] = {}
        self.render_slots = asyncio.Semaphore(4)
        self.ensure_lock = asyncio.Lock()
        self.message_id: int | None = None
        self.startup_task: asyncio.Task | None = None

    async def cog_load(self):
        self.bot.add_view(VerifyView(self))
        self.startup_task = asyncio.create_task(self._startup())

    async def cog_unload(self):
        if self.startup_task:
            self.startup_task.cancel()

    async def _startup(self):
        await self.bot.wait_until_ready()
        await self.ensure_message()

    @staticmethod
    def _load_state() -> dict:
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _save_state(channel_id: int, message_id: int):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"channel_id": channel_id, "message_id": message_id}), encoding="utf-8")

    async def ensure_message(self):
        if not config.verify_channel:
            log.warning("VERIFY_CHANNEL is not set; the verification message will not be posted")
            return
        async with self.ensure_lock:
            try:
                channel = self.bot.get_channel(config.verify_channel) or await self.bot.fetch_channel(config.verify_channel)
                message = await self._find_message(channel)
                embed = welcome_embed()

                if message is None:
                    message = await channel.send(embed=embed, view=VerifyView(self))
                    log.info("Posted the verification message")
                else:
                    current = message.embeds[0] if message.embeds else None
                    if current is None or current.title != embed.title or current.description != embed.description:
                        await message.edit(embed=embed, view=VerifyView(self))
                        log.info("Updated the verification message")

                self.message_id = message.id
                self._save_state(channel.id, message.id)
            except discord.HTTPException as exc:
                log.error("Could not post the verification message: HTTP %s", exc.status)
            except Exception:
                log.exception("Could not post the verification message")

    async def _find_message(self, channel: discord.abc.Messageable) -> discord.Message | None:
        state = self._load_state()
        if state.get("channel_id") == channel.id and state.get("message_id"):
            try:
                return await channel.fetch_message(state["message_id"])
            except discord.NotFound:
                pass
        async for message in channel.history(limit=50):
            if message.author.id == self.bot.user.id and message.embeds and message.embeds[0].title == TITLE:
                return message
        return None

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if self.message_id is not None and payload.message_id == self.message_id:
            self.message_id = None
            await self.ensure_message()

    async def _render(self, code: str) -> discord.File:
        async with self.render_slots:
            data = await asyncio.to_thread(captcha.render, code)
        return discord.File(io.BytesIO(data), filename="captcha.png")

    @staticmethod
    def _prompt_embed() -> discord.Embed:
        embed = make_embed(
            "Type the characters shown in the image, then press **Enter Code**. The code expires in 5 minutes.",
            "画像に表示されている文字を入力するには、**コードを入力**を押してください。コードは5分で期限切れになります。",
            title=("Verification", "認証"),
        )
        embed.set_image(url="attachment://captcha.png")
        return embed

    def _new_challenge(self, user_id: int) -> Challenge:
        challenge = Challenge(captcha.make_code(), time.monotonic() + CHALLENGE_SECONDS)
        self.challenges[user_id] = challenge
        return challenge

    def _throttled(self, user_id: int) -> bool:
        now = time.monotonic()
        if now - self.last_request.get(user_id, 0) < REQUEST_COOLDOWN:
            return True
        self.last_request[user_id] = now
        if len(self.last_request) > 5000:
            self.last_request = {u: t for u, t in self.last_request.items() if now - t < REQUEST_COOLDOWN}
        return False

    def _role(self, guild: discord.Guild | None) -> discord.Role | None:
        return guild.get_role(config.verify_role) if guild and config.verify_role else None

    async def start_challenge(self, interaction: discord.Interaction):
        member = interaction.user
        role = self._role(interaction.guild)
        if not isinstance(member, discord.Member) or role is None:
            return await interaction.response.send_message(
                embed=error_embed("Verification is not available right now.", "現在、認証は利用できません。"),
                ephemeral=True,
            )
        if self._throttled(member.id):
            return await interaction.response.send_message(
                embed=error_embed("Please wait a moment before trying again.", "少し待ってからもう一度お試しください。"),
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)
        challenge = self._new_challenge(member.id)
        await interaction.followup.send(
            embed=self._prompt_embed(),
            file=await self._render(challenge.code),
            view=ChallengeView(self, member.id),
            ephemeral=True,
        )

    async def refresh_challenge(self, interaction: discord.Interaction, view: ChallengeView):
        if self._throttled(interaction.user.id):
            return await interaction.response.send_message(
                embed=error_embed("Please wait a moment before trying again.", "少し待ってからもう一度お試しください。"),
                ephemeral=True,
            )
        await interaction.response.defer()
        challenge = self._new_challenge(interaction.user.id)
        await interaction.edit_original_response(
            embed=self._prompt_embed(), attachments=[await self._render(challenge.code)], view=view
        )

    async def submit(self, interaction: discord.Interaction, answer: str):
        member = interaction.user
        role = self._role(interaction.guild)
        challenge = self.challenges.get(member.id)

        if role is None or not isinstance(member, discord.Member):
            return await interaction.response.send_message(
                embed=error_embed("Verification is not available right now.", "現在、認証は利用できません。"),
                ephemeral=True,
            )
        if challenge is None or challenge.expires < time.monotonic():
            self.challenges.pop(member.id, None)
            return await interaction.response.send_message(
                embed=error_embed(
                    "That code has expired. Click the checkmark to get a new one.",
                    "コードの期限が切れました。チェックマークをクリックして新しいコードを取得してください。",
                ),
                ephemeral=True,
            )

        if not hmac.compare_digest(answer.strip().upper().encode(), challenge.code.encode()):
            challenge.attempts += 1
            if challenge.attempts >= MAX_ATTEMPTS:
                self.challenges.pop(member.id, None)
                return await interaction.response.send_message(
                    embed=error_embed(
                        "Too many incorrect attempts. Click the checkmark to get a new code.",
                        "間違いが多すぎます。チェックマークをクリックして新しいコードを取得してください。",
                    ),
                    ephemeral=True,
                )
            left = MAX_ATTEMPTS - challenge.attempts
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Incorrect code. {left} attempt(s) remaining.",
                    f"コードが違います。残り{left}回です。",
                ),
                ephemeral=True,
            )

        self.challenges.pop(member.id, None)
        try:
            if role not in member.roles:
                await member.add_roles(role, reason="Verification")
        except discord.HTTPException:
            log.error("Could not give the verified role (check the role hierarchy and permissions)")
            return await interaction.response.send_message(
                embed=error_embed(
                    "I couldn't give you the role. Please contact a staff member.",
                    "ロールを付与できませんでした。スタッフにお問い合わせください。",
                ),
                ephemeral=True,
            )

        embed = make_embed(
            "You have been verified. Have fun!",
            "認証が完了しました。楽しんでください！",
            title=("Verified", "認証完了"),
        )
        if interaction.message is not None:
            await interaction.response.edit_message(embed=embed, attachments=[], view=None)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
