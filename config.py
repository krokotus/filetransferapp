from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"

PORT = 8000

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MiB
MAX_FILES_TOTAL = 50
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB

PIN_TTL_SECONDS = 300
SESSION_TTL_SECONDS = 3600
MAX_PIN_ATTEMPTS = 5

COOKIE_NAME = "fs_session"
# Локальный режим работает по HTTP. Для HTTPS в production установите True
# и настройте TLS перед приложением.
COOKIE_SECURE = False
