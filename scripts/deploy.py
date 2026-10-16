"""Portable Docker launcher; generates local secrets without printing them."""
import argparse
import json
import secrets
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["up","bootstrap","down","status","verify","backup"],default="up",nargs="?")
    args=parser.parse_args()
    env=ROOT/".env.platform"
    if not env.exists():
        password=secrets.token_urlsafe(32)
        env.write_text(f"NEXUS_POSTGRES_PASSWORD={password}\nNEXUS_DATABASE_URL=postgresql://nexus:{password}@127.0.0.1:5433/nexus\nNEXUS_KAFKA_BOOTSTRAP=localhost:19092\nNEXUS_MLFLOW_URI=http://127.0.0.1:5001\n",encoding="utf-8")
    command=["docker","compose","--env-file",str(env),"-f",str(ROOT/"docker-compose.platform.yml")]
    def run(*parts):
        subprocess.run([*command,*parts],cwd=ROOT,check=True)
    if args.command in {"up","bootstrap"}:
        (ROOT/"runtime/artifacts").mkdir(parents=True,exist_ok=True)
        run("up","-d","--build","postgres","kafka","mlflow")
        deadline=time.monotonic()+180
        while True:
            try:
                urllib.request.urlopen("http://127.0.0.1:5001/health",timeout=3).close()
                break
            except Exception:
                if time.monotonic()>deadline:
                    raise RuntimeError("MLflow failed readiness; inspect compose logs")
                time.sleep(2)
        if args.command=="bootstrap":
            run("--profile","jobs","run","--rm","bootstrap")
        run("up","-d","--build","api","worker","web")
        print("NEXUS: http://localhost:3000 | API: http://localhost:8000/docs | MLflow: http://localhost:5001")
        if not (ROOT/"runtime/artifacts/demand_model.json").exists():
            print("Import and train with: python scripts/deploy.py bootstrap (M5 input files required; see README).")
    elif args.command=="down":
        run("down")
    elif args.command=="status":
        run("ps")
    elif args.command=="verify":
        run("exec","-T","api","python","scripts/manage.py","verify")
    elif args.command=="backup":
        path=ROOT/"runtime/backups"/time.strftime("nexus-%Y%m%d-%H%M%S.dump")
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("wb") as output:
            subprocess.run([*command,"exec","-T","postgres","pg_dump","-U","nexus","-d","nexus","-Fc"],cwd=ROOT,stdout=output,check=True)
        print(f"Database backup saved to {path}. Also preserve runtime/artifacts and the MLflow volume.")


if __name__=="__main__":
    main()
