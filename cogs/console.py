import re

import discord
from discord.ext import commands

from core.api import BackendError, backend, backend_error_embed
from core.embeds import make_embed
from core.logs import send_log
from core.permissions import requires

MAX_IDS = 25
ALLOWED_USERS = (1547371283933700167,)


def clean_id(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", raw).upper()[:20]


class Console(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_unload(self):
        await backend.close()

    async def _log(self, embed: discord.Embed):
        await send_log(self.bot, embed)

    @commands.hybrid_group(
        name="console",
        description="Manage console admin IDs. / コンソール管理者IDを管理します。",
        invoke_without_command=True,
    )
    @requires(users=ALLOWED_USERS)
    async def console(self, ctx: commands.Context):
        p = ctx.clean_prefix
        await ctx.reply(
            embed=make_embed(
                f"`{p}console add <ID> [name]`\n`{p}console del <ID> [ID ...]`",
                f"`{p}console add <ID> [名前]`\n`{p}console del <ID> [ID ...]`",
                title=("Console", "コンソール"),
            ),
            mention_author=False,
        )

    @console.command(name="add", description="Add an ID to the backend. / バックエンドにIDを追加します。")
    @requires(users=ALLOWED_USERS)
    async def add(self, ctx: commands.Context, id: str, *, name: str | None = None):
        await ctx.defer()

        user_id = clean_id(id)
        if not user_id:
            return await ctx.reply(
                embed=make_embed(
                    "That is not a valid ID.",
                    "無効なIDです。",
                    title=("Invalid ID", "無効なID"),
                ),
                mention_author=False,
            )
        name = (name or "").strip()[:32] or ctx.author.display_name

        try:
            if user_id in await backend.admin_ids():
                return await ctx.reply(
                    embed=make_embed(
                        f"`{user_id}` is already registered.",
                        f"`{user_id}` は既に登録されています。",
                        title=("Already Added", "登録済み"),
                    ),
                    mention_author=False,
                )
            ok = await backend.add_admin(user_id, name)
        except BackendError as exc:
            return await ctx.reply(embed=backend_error_embed(exc), mention_author=False)

        if ok:
            await self._log(
                make_embed(
                    f"{ctx.author} (`{ctx.author.id}`) added `{user_id}` as **{name}**.",
                    f"{ctx.author} (`{ctx.author.id}`) が `{user_id}` を **{name}** として追加しました。",
                    title=("Console ID Added", "コンソールID追加"),
                )
            )
            embed = make_embed(
                f"Added `{user_id}` as **{name}**.",
                f"`{user_id}` を **{name}** として追加しました。",
                title=("ID Added", "IDを追加しました"),
            )
        else:
            embed = make_embed(
                f"Failed to add `{user_id}`.",
                f"`{user_id}` の追加に失敗しました。",
                title=("Failed", "失敗"),
            )
        await ctx.reply(embed=embed, mention_author=False)

    @console.command(
        name="del",
        aliases=["remove"],
        description="Remove IDs from the backend (space separated). / バックエンドからIDを削除します（スペース区切り）。",
    )
    @requires(users=ALLOWED_USERS)
    async def remove(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()

        wanted = list(dict.fromkeys(i for i in map(clean_id, ids.split()) if i))
        if not wanted:
            return await ctx.reply(
                embed=make_embed(
                    "That is not a valid ID.",
                    "無効なIDです。",
                    title=("Invalid ID", "無効なID"),
                ),
                mention_author=False,
            )
        if len(wanted) > MAX_IDS:
            return await ctx.reply(
                embed=make_embed(
                    f"You can remove up to {MAX_IDS} IDs at once.",
                    f"一度に削除できるIDは最大{MAX_IDS}件です。",
                    title=("Too Many IDs", "IDが多すぎます"),
                ),
                mention_author=False,
            )

        removed, missing = [], []
        try:
            for user_id in wanted:
                (removed if await backend.remove_admin(user_id) else missing).append(user_id)
        except BackendError as exc:
            return await ctx.reply(embed=backend_error_embed(exc), mention_author=False)

        def fmt(items: list[str]) -> str:
            return ", ".join(f"`{i}`" for i in items)

        en, ja = [], []
        if removed:
            en.append(f"Removed: {fmt(removed)}")
            ja.append(f"削除しました：{fmt(removed)}")
        if missing:
            en.append(f"Not found: {fmt(missing)}")
            ja.append(f"見つかりません：{fmt(missing)}")

        if removed:
            await self._log(
                make_embed(
                    f"{ctx.author} (`{ctx.author.id}`)\n" + "\n".join(en),
                    f"{ctx.author} (`{ctx.author.id}`)\n" + "\n".join(ja),
                    title=("Console ID Removed", "コンソールID削除"),
                )
            )

        await ctx.reply(
            embed=make_embed(
                "\n".join(en),
                "\n".join(ja),
                title=("ID Removal", "ID削除") if removed else ("Not Found", "見つかりません"),
            ),
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Console(bot))
