import asyncio
import time

from .privacy import ROOT

started = time.monotonic()
commit = "unknown"


async def git(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode:
        lines = err.decode(errors="replace").strip().splitlines()
        raise RuntimeError(f"git {args[0]} failed: {lines[-1] if lines else proc.returncode}")
    return out.decode(errors="replace").strip()


def uptime_seconds() -> int:
    return int(time.monotonic() - started)
