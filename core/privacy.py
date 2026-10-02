import getpass
import os
import platform
import re
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _safe(fn) -> str:
    try:
        return fn() or ""
    except Exception:
        return ""


def _path_variants(path: str) -> set[str]:
    return {path, path.replace("\\", "/"), path.replace("\\", "\\\\")}


def _build():
    paths = {str(ROOT), os.getcwd(), str(Path.home()), sys.prefix, sys.base_prefix, sys.exec_prefix}
    paths.add(_safe(lambda: os.path.dirname(sys.executable)))
    variants = {v for p in paths if len(p) > 1 for v in _path_variants(p.rstrip("\\/"))}
    variants = {v for v in variants if len(v) > 1}
    flags = re.IGNORECASE if os.name == "nt" else 0
    path_re = re.compile(
        "(?:" + "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True)) + r")(?:[\\/][^\s'\"<>|]*)?",
        flags,
    )

    hosts = {_safe(socket.gethostname), _safe(platform.node), os.getenv("COMPUTERNAME", ""), os.getenv("HOSTNAME", "")}
    hosts = {h for h in hosts if len(h) > 1}
    host_re = re.compile("|".join(re.escape(h) for h in sorted(hosts, key=len, reverse=True)), re.IGNORECASE) if hosts else None

    users = {_safe(getpass.getuser), os.getenv("USERNAME", ""), os.getenv("USER", "")}
    users = {u for u in users if len(u) > 1 and u.lower() != "root"}
    user_re = (
        re.compile(
            r"(?<![A-Za-z0-9_-])(?:" + "|".join(re.escape(u) for u in sorted(users, key=len, reverse=True)) + r")(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        )
        if users
        else None
    )
    return path_re if variants else None, host_re, user_re


_PATH_RE, _HOST_RE, _USER_RE = _build()


def scrub_text(text: str) -> str:
    if _PATH_RE:
        text = _PATH_RE.sub("[path]", text)
    if _HOST_RE:
        text = _HOST_RE.sub("[host]", text)
    return text


def scrub_stream_text(text: str) -> str:
    text = scrub_text(text)
    if _USER_RE:
        text = _USER_RE.sub("[user]", text)
    return text


class _ScrubStream:
    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        return self._stream.write(scrub_stream_text(text) if isinstance(text, str) else text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install():
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is not None and not isinstance(stream, _ScrubStream):
            setattr(sys, name, _ScrubStream(stream))
