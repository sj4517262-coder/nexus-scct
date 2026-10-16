"""NEXUS application entrypoint. See main_research.py for the original prototype."""
from nexus.platform.config import load_local_env
load_local_env()
from nexus.api import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
