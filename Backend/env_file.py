"""
env_file.py — reads the local `.env` into the process environment
Project: NetVerify — Tunisie Telecom

The backend takes its configuration from environment variables (database URL,
signing key, service token, Gemini key). On a workstation that means retyping a
`set GEMINI_API_KEY=...` in every new terminal, and forgetting it once is enough
for the assistant to answer "GEMINI_API_KEY is not set on the backend server".
Storing them in a file next to the code removes that failure mode.

No dependency: the format is one `NAME=value` per line, which is what
`docker compose` already reads from the project root, so the same file serves
both ways of starting the stack.

A variable already present in the real environment always wins — a value
exported on purpose (in production, in the container) must never be silently
overridden by a development file left behind on disk.
"""

import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# The backend directory first (the usual working directory when uvicorn is
# started by hand), then the project root (the file docker compose reads).
CANDIDATES = (_HERE / ".env", _HERE.parent / ".env")


def _parse(line: str):
    """Returns (name, value) for a usable line, None for anything else."""
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None

    # `export NAME=value` is tolerated so a file written for a Unix shell can be
    # reused as is.
    if line.startswith("export "):
        line = line[len("export "):].lstrip()

    name, _, value = line.partition("=")
    name = name.strip()
    if not name:
        return None

    value = value.strip()
    # Quotes delimit the value, they are not part of it: a key pasted between
    # quotes must not reach the API with the quotes attached.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return name, value


def load_env_files(paths=CANDIDATES) -> list[str]:
    """Loads the first existing files and returns the names actually set.

    Must be called before importing the modules that capture their
    configuration at import time — afterwards it would be too late.
    """
    loaded = []
    for path in paths:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for line in content.splitlines():
            parsed = _parse(line)
            if parsed is None:
                continue
            name, value = parsed
            if os.environ.get(name):
                continue
            os.environ[name] = value
            loaded.append(name)
    return loaded
