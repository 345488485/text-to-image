from dataclasses import dataclass
from pathlib import Path
import os

@dataclass
class Settings:
    root: Path = Path(__file__).resolve().parents[2]
    data_dir: Path | None = None
    engine_url: str = 'http://127.0.0.1:8188'
    worker_enabled: bool = True
    engine_autostart: bool = False
    bootstrap_default_admin: bool = False
    task_timeout: int = 1800
    session_seconds: int = 43200
    secure_cookie: bool = False
    allowed_origins: tuple = ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000')

    def __post_init__(self):
        self.root = Path(self.root).resolve()
        self.data_dir = Path(self.data_dir or os.getenv('MOSS_DATA_DIR') or self.root / 'platform/data').resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / 'images').mkdir(exist_ok=True)
        self.db_path = self.data_dir / 'moss.sqlite3'
