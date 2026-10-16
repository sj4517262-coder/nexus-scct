import os
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"


def load_local_env():
    # Dedicated configuration: never reinterpret or overwrite the legacy .env.
    path = ROOT / ".env.platform"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value.strip())


def database_url():
    load_local_env()
    return os.getenv("NEXUS_DATABASE_URL", "sqlite:///" + (RUNTIME / "platform.db").as_posix())


@lru_cache(maxsize=4)
def engine_for(url):
    from sqlalchemy import create_engine
    return create_engine(url, pool_pre_ping=True)


def engine():
    return engine_for(database_url())


def artifact_dir():
    path = Path(os.getenv("NEXUS_ARTIFACT_DIR", str(RUNTIME / "artifacts")))
    path.mkdir(parents=True, exist_ok=True)
    return path
