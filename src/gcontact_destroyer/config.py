from pathlib import Path

APP_NAME = "gcontact-destroyer"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
DATA_DIR = Path.home() / ".local" / "share" / APP_NAME
DB_PATH = DATA_DIR / "contacts.db"
TOKEN_PATH = DATA_DIR / "token.json"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"

SCOPES = ["https://www.googleapis.com/auth/contacts"]

KEEP_LABEL = "Keep"

SYNC_PAGE_SIZE = 1000
BATCH_DELETE_SIZE = 500


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
