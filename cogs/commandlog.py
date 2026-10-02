import logging

import discord
from discord.ext import commands

log = logging.getLogger("qubot.commands")

MAX_LENGTH = 200


def describe_interaction(data: dict) -> str:
    names = [data.get("name", "?")]
    options = data.get("options", [])
    while options and options[0].get("type") in (1, 2):
        names.append(options[0]["name"])
        options = options[0].get("options", [])
    args = " ".join(f"{o['name']}={o.get('value')}" for o in options)
    return f"/{' '.join(names)} {args}".strip()


def where(guild: discord.Guild | None, channel_id: int | None) -> str:
    return f"{guild.name} ({guild.id}) #{channel_id}" if guild else "DM"


class CommandLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if ctx.interaction is not None:
            return
        log.info(
            "%s (%s) ran: %s | %s",
            ctx.author,
            ctx.author.id,
            ctx.message.content[:MAX_LENGTH],
            where(ctx.guild, ctx.channel.id),
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.application_command:
            return
        log.info(
            "%s (%s) ran: %s | %s",
            interaction.user,
            interaction.user.id,
            describe_interaction(interaction.data or {})[:MAX_LENGTH],
            where(interaction.guild, interaction.channel_id),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandLog(bot))
