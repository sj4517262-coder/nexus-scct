"""Restore the latest backup into a disposable database, verify, then remove it."""
import json
import subprocess
import uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
backup=max((ROOT/"runtime/backups").glob("*.dump"),key=lambda p:p.stat().st_mtime)
compose=["docker","compose","--env-file",str(ROOT/".env.platform"),"-f",str(ROOT/"docker-compose.platform.yml"),"exec","-T","postgres"]
database="nexus_restore_"+uuid.uuid4().hex[:10]
subprocess.run([*compose,"createdb","-U","nexus",database],check=True)
try:
    with backup.open("rb") as source:
        subprocess.run([*compose,"pg_restore","-U","nexus","-d",database,"--exit-on-error","--no-owner"],stdin=source,check=True)
    result=subprocess.check_output([*compose,"psql","-U","nexus","-d",database,"-Atc","SELECT count(*) FROM m5_demand"],text=True).strip()
    expected=json.loads((ROOT/"runtime/artifacts/m5_validation.json").read_text())["persisted_demand_rows"]
    assert int(result)==expected
    report=dict(verified_at=datetime.now(timezone.utc).isoformat(),backup=backup.name,restored_demand_rows=int(result),status="PASSED",isolation="disposable database; live database unchanged")
    (ROOT/"runtime/artifacts/backup_verification.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
finally:
    subprocess.run([*compose,"dropdb","-U","nexus",database],check=True)
