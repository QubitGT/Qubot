import asyncio
import logging
import sys

from discord.ext import commands, tasks

from core import runtime
from core.config import config
from core.embeds import make_embed
from core.logs import send_log
from core.privacy import ROOT

log = logging.getLogger("qubot.updater")


class Updater(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_error = ""

    async def cog_load(self):
        self.check.start()

    async def cog_unload(self):
        self.check.cancel()

    async def _install_requirements(self) -> bool:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt",
            cwd=ROOT, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        return await proc.wait() == 0

    @tasks.loop(seconds=60)
    async def check(self):
        if not config.auto_update:
            return
        try:
            await runtime.git("fetch", "--quiet")
            if int(await runtime.git("rev-list", "--count", "HEAD..@{u}")) == 0:
                self.last_error = ""
                return
            changed = (await runtime.git("diff", "--name-only", "HEAD", "@{u}")).splitlines()
            await runtime.git("pull", "--ff-only", "--quiet")
            new_commit = await runtime.git("rev-parse", "--short", "HEAD")
        except Exception as exc:
            if str(exc) != self.last_error:
                self.last_error = str(exc)
                log.error("Update check failed: %s", exc)
            return

        log.info("Pulled update %s", new_commit)
        if "requirements.txt" in changed and not await self._install_requirements():
            log.error("Installing requirements failed; not restarting")
            return

        await send_log(
            self.bot,
            make_embed(
                f"Updated to `{new_commit}`. Restarting...",
                f"`{new_commit}` に更新しました。再起動しています...",
                title=("Update", "アップデート"),
            ),
        )
        self.bot.restart_requested = True
        await self.bot.close()

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Updater(bot))
