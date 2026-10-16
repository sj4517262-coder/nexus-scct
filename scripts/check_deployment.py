"""Authenticated production browser smoke test with a temporary QA account."""
import os
import secrets
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nexus.platform.config import load_local_env,database_url
from nexus.store import Store,uid
from nexus.api import password_hash

load_local_env()
store=Store(database_url())
store.initialize()
identifier=uid("QA")
email=identifier.lower()+"@example.invalid"
password=secrets.token_urlsafe(24)
with store.transaction() as con:
    con.execute("INSERT INTO users VALUES(?,?,?,?)",(identifier,email,password_hash(password),"ADMIN"))
try:
    subprocess.run(["node","scripts/check_deployment.js"],cwd=ROOT,env={**os.environ,"NEXUS_QA_EMAIL":email,"NEXUS_QA_PASSWORD":password},check=True)
finally:
    with store.transaction() as con:
        con.execute("DELETE FROM sessions WHERE user_id=?",(identifier,))
        con.execute("DELETE FROM users WHERE id=?",(identifier,))
