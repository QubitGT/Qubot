from __future__ import annotations

from collections.abc import Iterable

import discord
from discord.ext import commands


class MissingRole(commands.CheckFailure):
    def __init__(self, roles: Iterable[str | int]):
        self.roles = list(roles)
        super().__init__("Missing a required role")


class UserNotAllowed(commands.CheckFailure):
    pass


def _has_role(member: discord.Member, role: str | int) -> bool:
    if isinstance(role, int):
        return any(r.id == role for r in member.roles)
    return any(r.name.lower() == role.lower() for r in member.roles)


def requires(*, users: Iterable[int] = (), roles: Iterable[str | int] = (), **permissions: bool):
    allowed_users = frozenset(users)
    required_roles = list(roles)

    async def predicate(ctx: commands.Context) -> bool:
        if allowed_users:
            if ctx.author.id in allowed_users:
                return True
            raise UserNotAllowed()

        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            raise commands.NoPrivateMessage()

        if ctx.author.id == ctx.guild.owner_id:
            return True

        held = ctx.channel.permissions_for(ctx.author)
        missing = [name for name, value in permissions.items() if getattr(held, name) != value]
        if missing:
            raise commands.MissingPermissions(missing)

        if required_roles and not any(_has_role(ctx.author, r) for r in required_roles):
            raise MissingRole(required_roles)

        return True

    return commands.check(predicate)
