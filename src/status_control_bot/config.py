import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env из корня проекта (на 2 уровня выше текущего файла)
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

# Базовые пути
BASE_DIR = _env_path.parent.resolve()  # resolve() -> абсолютный путь
DATA_DIR = BASE_DIR / "data"
PARSING_DIR = DATA_DIR / "parsing"

# Читаем токен
API_BOT_TOKEN = os.getenv("API_BOT_TOKEN", None)

# Допустимый максимум в различии имен (строковых выражений)
DIFF_SYMBOLS = 1