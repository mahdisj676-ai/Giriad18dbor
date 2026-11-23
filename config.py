"""Environment-backed configuration for GuardBot."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("BOT_TOKEN", "").strip()
_raw_owners = os.getenv("OWNER_IDS", "")
OWNERS: set[int] = set()
for _part in _raw_owners.replace(";", ",").split(","):
    _part = _part.strip()
    if _part:
        try:
            OWNERS.add(int(_part))
        except ValueError:
            raise RuntimeError(f"OWNER_IDS contains a non-numeric value: {_part!r}")

_db_path = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "guardbot.sqlite3"))).expanduser()
if not _db_path.is_absolute():
    _db_path = BASE_DIR / _db_path
_db_path = _db_path.resolve()
DB_PATH = str(_db_path)
_db_dir = _db_path.parent
_db_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
try:
    os.chmod(_db_dir, 0o700)
except OSError:
    pass

DEFAULT_ENGINE = os.getenv("DEFAULT_ENGINE", "smart").strip().lower()
if DEFAULT_ENGINE not in {"local", "cloud", "brain", "hybrid", "smart"}:
    DEFAULT_ENGINE = "smart"

DEFAULT_LEVEL = os.getenv("DEFAULT_LEVEL", "mid").strip().lower()
if DEFAULT_LEVEL not in {"low", "mid", "high"}:
    DEFAULT_LEVEL = "mid"

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()
GOOGLE_VISION_KEY = os.getenv("GOOGLE_VISION_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
GOOGLE_DAILY_CAP = max(0, int(os.getenv("GOOGLE_DAILY_CAP", "100")))
ANTHROPIC_DAILY_CAP = max(0, int(os.getenv("ANTHROPIC_DAILY_CAP", "250")))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
