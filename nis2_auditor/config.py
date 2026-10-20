from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_data_dir

PACKAGE_ROOT = Path(__file__).resolve().parent
load_dotenv(Path.cwd() / ".env")
DATA = Path(os.getenv("NIS2_DATA_DIR") or user_data_dir("nis2-auditor", "NIS2 Auditor")).expanduser().resolve()
FILES = DATA / "files"
PAGES = DATA / "pages"
DB = DATA / "auditor.sqlite3"
for directory in (DATA, FILES, PAGES):
    directory.mkdir(parents=True, exist_ok=True)

AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_TEXT_MODEL = os.getenv("AI_TEXT_MODEL", "").strip()
AI_VISION_MODEL = os.getenv("AI_VISION_MODEL", "").strip()
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024

