import asyncio
import contextlib
import logging
import re
from collections import defaultdict
from typing import Callable, Literal

import discord
from discord import app_commands
from discord.ext import commands

from core.embeds import ERROR, SUCCESS, WARNING, make_embed
from core.permissions import requires
from core.rrstore import Entry, Store

log = logging.getLogger("qubot.reactionrole")

TYPE_TEXT = {
    "normal": ("react to get, unreact to lose", "リアクションで付与、解除で剥奪"),
    "unique": ("only one role from this message", "このメッセージからは1つのみ"),
    "verify": ("react to get, kept after unreacting", "リアクションで付与、解除しても保持"),
    "drop": ("react to lose the role", "リアクションで剥奪"),
}

LINK_RE = re.compile(r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")
CUSTOM_EMOJI_RE = re.compile(r"<a?:([A-Za-z0-9_]{2,32}):(\d+)>")
BYPASS_SLOWMODE = 1 << 52

SPECIAL_PERMISSIONS = {
    "administrator": ("Administrator", "管理者"),
    "manage_guild": ("Manage Server", "サーバー管理"),
    "manage_roles": ("Manage Roles", "ロールの管理"),
    "manage_channels": ("Manage Channels", "チャンネルの管理"),
    "manage_messages": ("Manage Messages", "メッセージの管理"),
    "manage_threads": ("Manage Threads", "スレッドの管理"),
    "manage_webhooks": ("Manage Webhooks", "ウェブフックの管理"),
    "manage_nicknames": ("Manage Nicknames", "ニックネームの管理"),
    "manage_expressions": ("Manage Expressions", "表現の管理"),
    "manage_events": ("Manage Events", "イベントの管理"),
    "kick_members": ("Kick Members", "メンバーをキック"),
    "ban_members": ("Ban Members", "メンバーをBAN"),
    "moderate_members": ("Timeout Members", "メンバーをタイムアウト"),
    "mention_everyone": ("Mention Everyone", "全員にメンション"),
    "view_audit_log": ("View Audit Log", "監査ログを表示"),
}


def emoji_key(emoji: discord.PartialEmoji) -> str:
    return str(emoji.id) if emoji.id else (emoji.name or "").replace("️", "")


def parse_emoji(raw: str) -> tuple[str, str] | None:
    raw = raw.strip()
    match = CUSTOM_EMOJI_RE.fullmatch(raw)
    if match:
        return match[2], f"{match[1]}:{match[2]}"
    if raw and len(raw) <= 20 and not raw.isascii():
        return raw.replace("️", ""), raw
    return None


def special_permissions(role: discord.Role) -> list[tuple[str, str]]:
    found = [names for flag, names in SPECIAL_PERMISSIONS.items() if getattr(role.permissions, flag, False)]
    if role.permissions.value & BYPASS_SLOWMODE:
        found.append(("Bypass Slowmode", "低速モードの影響を受けない"))
    return found


def message_link_of(entry: Entry) -> str:
    return f"https://discord.com/channels/{entry.guild_id}/{entry.channel_id}/{entry.message_id}"


class Confirm(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.value: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            embed=make_embed(
                "Only the person who ran the command can use these buttons.",
                "これらのボタンはコマンドを実行した本人のみ使用できます。",
                color=ERROR,
            ),
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Confirm / 確認", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel / キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.defer()
        self.stop()


class ReactionRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = Store()
        self.entries: dict[tuple[int, str], Entry] = {}
        self.by_message: dict[int, list[Entry]] = defaultdict(list)
        self._locks: dict[int, list] = {}
        self._warned: set[int] = set()

    async def cog_load(self):
        for entry in await asyncio.to_thread(self.store.all):
            self._index(entry)
        log.info("Loaded %d reaction roles", len(self.entries))

    async def cog_unload(self):
        await asyncio.to_thread(self.store.close)

    def _index(self, entry: Entry):
        self.entries[(entry.message_id, entry.emoji_key)] = entry
        self.by_message[entry.message_id].append(entry)

    def _unindex(self, entry: Entry):
        self.entries.pop((entry.message_id, entry.emoji_key), None)
        siblings = [e for e in self.by_message.get(entry.message_id, []) if e.id != entry.id]
        if siblings:
            self.by_message[entry.message_id] = siblings
        else:
            self.by_message.pop(entry.message_id, None)

    async def _purge(self, matches: Callable[[Entry], bool]):
        doomed = [e for e in list(self.entries.values()) if matches(e)]
        if not doomed:
            return
        for entry in doomed:
            self._unindex(entry)
        await asyncio.to_thread(self.store.delete, [e.id for e in doomed])
        log.info("Removed %d reaction roles whose target no longer exists", len(doomed))

    @contextlib.asynccontextmanager
    async def _user_lock(self, user_id: int):
        slot = self._locks.get(user_id)
        if slot is None:
            slot = self._locks[user_id] = [asyncio.Lock(), 0]
        slot[1] += 1
        try:
            async with slot[0]:
                yield
        finally:
            slot[1] -= 1
            if slot[1] == 0:
                self._locks.pop(user_id, None)

    async def _http_failed(self, entry: Entry, exc: discord.HTTPException):
        if isinstance(exc, discord.NotFound):
            if exc.code == 10011:
                await self._purge(lambda e: e.role_id == entry.role_id)
            elif exc.code in (10003, 10008):
                await self._purge(lambda e: e.message_id == entry.message_id)
            return
        if isinstance(exc, discord.Forbidden):
            if entry.id not in self._warned:
                self._warned.add(entry.id)
                log.warning("Missing permission for reaction role #%d (role hierarchy or permissions changed)", entry.id)
            return
        log.error("Reaction role #%d failed: HTTP %s", entry.id, exc.status)

    async def _give(self, entry: Entry, user_id: int):
        try:
            await self.bot.http.add_role(entry.guild_id, user_id, entry.role_id, reason="Reaction role")
        except discord.HTTPException as exc:
            await self._http_failed(entry, exc)

    async def _take(self, entry: Entry, user_id: int):
        try:
            await self.bot.http.remove_role(entry.guild_id, user_id, entry.role_id, reason="Reaction role")
        except discord.HTTPException as exc:
            await self._http_failed(entry, exc)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        entry = self.entries.get((payload.message_id, emoji_key(payload.emoji)))
        if entry is None or payload.user_id == self.bot.user.id:
            return
        member = payload.member
        if member is not None and member.bot:
            return

        async with self._user_lock(payload.user_id):
            try:
                if entry.type == "drop":
                    await self._take(entry, payload.user_id)
                    return

                if member is None or all(r.id != entry.role_id for r in member.roles):
                    await self._give(entry, payload.user_id)

                if entry.type == "unique":
                    for other in self.by_message.get(entry.message_id, ()):
                        if other.id == entry.id or other.type != "unique":
                            continue
                        if member is None or any(r.id == other.role_id for r in member.roles):
                            await self._take(other, payload.user_id)
                        with contextlib.suppress(discord.HTTPException):
                            await self.bot.http.remove_reaction(
                                other.channel_id, other.message_id, other.emoji_api, payload.user_id
                            )
            except Exception:
                log.exception("Unexpected error handling reaction add")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        entry = self.entries.get((payload.message_id, emoji_key(payload.emoji)))
        if entry is None or entry.type not in ("normal", "unique") or payload.user_id == self.bot.user.id:
            return

        async with self._user_lock(payload.user_id):
            try:
                await self._take(entry, payload.user_id)
            except Exception:
                log.exception("Unexpected error handling reaction remove")

    async def _restore_reactions(self, entries):
        for entry in entries:
            try:
                await self.bot.http.add_reaction(entry.channel_id, entry.message_id, entry.emoji_api)
            except discord.HTTPException as exc:
                await self._http_failed(entry, exc)

    @commands.Cog.listener()
    async def on_raw_reaction_clear(self, payload: discord.RawReactionClearEvent):
        entries = self.by_message.get(payload.message_id)
        if entries:
            await self._restore_reactions(list(entries))

    @commands.Cog.listener()
    async def on_raw_reaction_clear_emoji(self, payload: discord.RawReactionClearEmojiEvent):
        entry = self.entries.get((payload.message_id, emoji_key(payload.emoji)))
        if entry:
            await self._restore_reactions([entry])

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.message_id in self.by_message:
            await self._purge(lambda e: e.message_id == payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        gone = payload.message_ids & self.by_message.keys()
        if gone:
            await self._purge(lambda e: e.message_id in gone)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._purge(lambda e: e.channel_id == channel.id)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        await self._purge(lambda e: e.channel_id == thread.id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._purge(lambda e: e.role_id == role.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self._purge(lambda e: e.guild_id == guild.id)

    @staticmethod
    def _fail(en: str, ja: str, title: tuple[str, str] = ("Error", "エラー")) -> discord.Embed:
        return make_embed(en, ja, title=title, color=ERROR)

    @commands.hybrid_group(
        name="reactionrole",
        description="Manage reaction roles. / リアクションロールを管理します。",
        invoke_without_command=True,
    )
    @commands.guild_only()
    @requires(manage_messages=True, manage_roles=True)
    async def reactionrole(self, ctx: commands.Context):
        p = ctx.clean_prefix
        types = ", ".join(TYPE_TEXT)
        await ctx.reply(
            embed=make_embed(
                f"`{p}reactionrole add <emoji> <role> <type> <message-link>`\n"
                f"`{p}reactionrole remove <reaction-id>`\n`{p}reactionrole list`\n"
                f"Types: {types}",
                f"`{p}reactionrole add <絵文字> <ロール> <タイプ> <メッセージリンク>`\n"
                f"`{p}reactionrole remove <リアクションID>`\n`{p}reactionrole list`\n"
                f"タイプ：{types}",
                title=("Reaction Roles", "リアクションロール"),
            ),
            mention_author=False,
        )

    @reactionrole.command(name="add", description="Add a reaction role. / リアクションロールを追加します。")
    @commands.guild_only()
    @requires(manage_messages=True, manage_roles=True)
    @app_commands.describe(
        emoji="The emoji to react with / リアクションの絵文字",
        role="The role to give / 付与するロール",
        type="How the reaction role behaves / 動作タイプ",
        message_link="Link to the message / メッセージのリンク",
    )
    @app_commands.rename(message_link="message-link")
    async def add(
        self,
        ctx: commands.Context,
        emoji: str,
        role: discord.Role,
        type: Literal["normal", "unique", "verify", "drop"],
        message_link: str,
    ):
        await ctx.defer()
        guild = ctx.guild
        reply_message: discord.Message | None = None

        async def respond(embed: discord.Embed, view: discord.ui.View | None = None):
            nonlocal reply_message
            if reply_message is None:
                if view is None:
                    reply_message = await ctx.reply(embed=embed, mention_author=False)
                else:
                    reply_message = await ctx.reply(embed=embed, view=view, mention_author=False)
            else:
                await reply_message.edit(embed=embed, view=view)

        parsed = parse_emoji(emoji)
        if parsed is None:
            return await respond(
                self._fail(
                    "That is not a valid emoji. Use a Unicode emoji or a custom emoji.",
                    "有効な絵文字ではありません。Unicode絵文字またはカスタム絵文字を使用してください。",
                    ("Invalid Emoji", "無効な絵文字"),
                )
            )
        key, api = parsed

        link = LINK_RE.search(message_link.strip("<> \n"))
        if link is None or int(link[1]) != guild.id:
            return await respond(
                self._fail(
                    "That is not a valid link to a message in this server.",
                    "このサーバー内のメッセージへの有効なリンクではありません。",
                    ("Invalid Link", "無効なリンク"),
                )
            )
        channel_id, message_id = int(link[2]), int(link[3])

        if role.is_default() or role.managed:
            return await respond(
                self._fail(
                    "That role cannot be assigned manually.",
                    "そのロールは手動で付与できません。",
                    ("Invalid Role", "無効なロール"),
                )
            )
        if ctx.author.id != guild.owner_id and role >= ctx.author.top_role:
            return await respond(
                self._fail(
                    "You can only use roles below your highest role.",
                    "あなたの最上位ロールより下のロールのみ使用できます。",
                    ("Role Too High", "ロールが高すぎます"),
                )
            )
        me = guild.me
        if not me.guild_permissions.manage_roles or role >= me.top_role:
            return await respond(
                self._fail(
                    "I can't assign that role. Move my highest role above it and make sure I have Manage Roles.",
                    "そのロールを付与できません。私の最上位ロールをそのロールより上に移動し、ロールの管理権限を付与してください。",
                    ("Role Too High", "ロールが高すぎます"),
                )
            )

        channel = guild.get_channel_or_thread(channel_id)
        if channel is None:
            return await respond(
                self._fail(
                    "I can't see the channel of that message.",
                    "そのメッセージのチャンネルが見えません。",
                    ("Channel Not Found", "チャンネルが見つかりません"),
                )
            )
        needed = channel.permissions_for(me)
        if not (needed.view_channel and needed.read_message_history and needed.add_reactions):
            return await respond(
                self._fail(
                    "I need View Channel, Read Message History and Add Reactions in that channel.",
                    "そのチャンネルで、チャンネルを見る・メッセージ履歴を読む・リアクションの追加の権限が必要です。",
                    ("Missing Permissions", "権限が不足しています"),
                )
            )
        if type == "unique" and not needed.manage_messages:
            return await respond(
                self._fail(
                    "The unique type needs me to have Manage Messages in that channel.",
                    "uniqueタイプには、そのチャンネルでのメッセージの管理権限が必要です。",
                    ("Missing Permissions", "権限が不足しています"),
                )
            )
        try:
            await channel.fetch_message(message_id)
        except discord.HTTPException:
            return await respond(
                self._fail(
                    "I can't find or read that message.",
                    "そのメッセージが見つからないか、読み取れません。",
                    ("Message Not Found", "メッセージが見つかりません"),
                )
            )

        if (message_id, key) in self.entries:
            return await respond(
                self._fail(
                    "That emoji already has a reaction role on this message.",
                    "このメッセージのその絵文字には既にリアクションロールがあります。",
                    ("Already Exists", "既に存在します"),
                )
            )

        dangerous = special_permissions(role)
        if dangerous:
            en = ", ".join(names[0] for names in dangerous)
            ja = "、".join(names[1] for names in dangerous)
            view = Confirm(ctx.author.id)
            await respond(
                make_embed(
                    f"{role.mention} has special permissions: **{en}**\n"
                    "Everyone who reacts will receive them. Do you want to continue?",
                    f"{role.mention} には特別な権限があります：**{ja}**\n"
                    "リアクションした全員に付与されます。続行しますか？",
                    title=("Confirmation Required", "確認が必要です"),
                    color=WARNING,
                ),
                view,
            )
            await view.wait()
            if not view.value:
                return await respond(
                    make_embed(
                        "Cancelled.",
                        "キャンセルしました。",
                        title=("Cancelled", "キャンセル"),
                    )
                )

        try:
            await self.bot.http.add_reaction(channel_id, message_id, api)
        except discord.HTTPException:
            return await respond(
                self._fail(
                    "I couldn't add that reaction. The emoji may be unavailable to me, or the message has too many reactions.",
                    "そのリアクションを追加できませんでした。絵文字が使用できないか、リアクションが多すぎる可能性があります。",
                    ("Reaction Failed", "リアクション失敗"),
                )
            )

        entry = await asyncio.to_thread(
            self.store.add, guild.id, channel_id, message_id, key, api, role.id, type, ctx.author.id
        )
        if entry is None:
            return await respond(
                self._fail(
                    "That emoji already has a reaction role on this message.",
                    "このメッセージのその絵文字には既にリアクションロールがあります。",
                    ("Already Exists", "既に存在します"),
                )
            )
        self._index(entry)

        await respond(
            make_embed(
                f"Reaction role **#{entry.id}** created: {emoji} gives {role.mention} "
                f"([message]({message_link_of(entry)})). Type: **{type}** ({TYPE_TEXT[type][0]}).",
                f"リアクションロール **#{entry.id}** を作成しました：{emoji} で {role.mention} "
                f"（[メッセージ]({message_link_of(entry)})）。タイプ：**{type}**（{TYPE_TEXT[type][1]}）。",
                title=("Reaction Role Added", "リアクションロールを追加しました"),
                color=SUCCESS,
            )
        )

    @reactionrole.command(name="remove", description="Remove a reaction role. / リアクションロールを削除します。")
    @commands.guild_only()
    @requires(manage_messages=True, manage_roles=True)
    @app_commands.describe(reaction_id="The reaction role ID / リアクションロールのID")
    @app_commands.rename(reaction_id="reaction-id")
    async def remove(self, ctx: commands.Context, reaction_id: int):
        await ctx.defer()
        entry = await asyncio.to_thread(self.store.get, reaction_id, ctx.guild.id)
        if entry is None:
            return await ctx.reply(
                embed=self._fail(
                    f"No reaction role with ID **#{reaction_id}** was found.",
                    f"ID **#{reaction_id}** のリアクションロールは見つかりませんでした。",
                    ("Not Found", "見つかりません"),
                ),
                mention_author=False,
            )

        self._unindex(entry)
        await asyncio.to_thread(self.store.delete, [entry.id])
        with contextlib.suppress(discord.HTTPException):
            await self.bot.http.remove_own_reaction(entry.channel_id, entry.message_id, entry.emoji_api)

        await ctx.reply(
            embed=make_embed(
                f"Reaction role **#{entry.id}** removed.",
                f"リアクションロール **#{entry.id}** を削除しました。",
                title=("Reaction Role Removed", "リアクションロールを削除しました"),
                color=SUCCESS,
            ),
            mention_author=False,
        )

    @reactionrole.command(name="list", description="List reaction roles. / リアクションロールの一覧を表示します。")
    @commands.guild_only()
    @requires(manage_messages=True, manage_roles=True)
    async def list_(self, ctx: commands.Context):
        entries = sorted((e for e in self.entries.values() if e.guild_id == ctx.guild.id), key=lambda e: e.id)
        if not entries:
            return await ctx.reply(
                embed=make_embed(
                    "There are no reaction roles in this server.",
                    "このサーバーにはリアクションロールがありません。",
                    title=("Reaction Roles", "リアクションロール"),
                ),
                mention_author=False,
            )

        shown = entries[:20]
        en = [f"**#{e.id}** <@&{e.role_id}> `{e.type}` [message]({message_link_of(e)})" for e in shown]
        ja = [line.replace("[message]", "[メッセージ]") for line in en]
        more = len(entries) - len(shown)
        await ctx.reply(
            embed=make_embed(
                "\n".join(en) + (f"\n+{more} more" if more else ""),
                "\n".join(ja) + (f"\n他{more}件" if more else ""),
                title=("Reaction Roles", "リアクションロール"),
            ),
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRole(bot))
