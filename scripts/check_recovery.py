"""Local fault-injection test; temporarily stops this project's Kafka broker."""
import json
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nexus.platform.config import load_local_env,database_url,artifact_dir
from nexus.platform.simulator import simulate
from nexus.platform.verify import eventually
from nexus.store import Store,now

load_local_env()
store=Store(database_url())
compose=["docker","compose","--env-file",str(ROOT/".env.platform"),"-f",str(ROOT/"docker-compose.platform.yml")]
def run(*args):
    subprocess.run([*compose,*args],cwd=ROOT,check=True)

try:
    run("stop","kafka")
    queued=simulate(1,99,store)
    def pending_after_failure():
        with store.transaction() as con:
            rows=con.execute("SELECT status,attempts FROM outbox WHERE id=?",(queued["event_ids"][0],)).fetchone()
            return rows["status"]=="PENDING" and rows["attempts"]>0
    eventually(pending_after_failure,60)
finally:
    run("up","-d","--wait","kafka")

def all_consumed():
    with store.transaction() as con:
        return all(con.execute("SELECT id FROM inbox WHERE id=?",(i,)).fetchone() for i in queued["event_ids"])
eventually(all_consumed)
run("restart","worker")
queued=simulate(1,100,store)
eventually(all_consumed)
report=dict(verified_at=now(),kafka_outage="pending events retained and retried",broker_recovery="all queued events consumed",worker_restart="existing topics reused; processing resumed",events_per_recovery=len(queued["event_ids"]))
(artifact_dir()/"recovery_verification.json").write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
