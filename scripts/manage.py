"""Single entrypoint for the full reproducible data and intelligence pipeline."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nexus.platform.config import load_local_env


def main():
    load_local_env()
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["m5","public","train","worker","simulate","bootstrap","verify"])
    parser.add_argument("--days",type=int,default=365,help="M5 product-level history window; 0 imports all days")
    parser.add_argument("--ticks",type=int,default=10)
    parser.add_argument("--refresh",action="store_true")
    args=parser.parse_args()
    if args.command in {"m5","bootstrap"}:
        from nexus.platform.data import ingest_m5
        print(json.dumps(ingest_m5(days=args.days),indent=2),flush=True)
    if args.command in {"public","bootstrap"}:
        from nexus.platform.data import ingest_public
        print(json.dumps(ingest_public(refresh=args.refresh),indent=2),flush=True)
    if args.command in {"train","bootstrap"}:
        from nexus.platform.models import train_all
        print(json.dumps(train_all(),indent=2),flush=True)
    if args.command=="worker":
        from nexus.platform.streaming import worker
        worker()
    if args.command=="simulate":
        from nexus.platform.simulator import simulate
        print(json.dumps(simulate(args.ticks),indent=2))
    if args.command=="verify":
        from nexus.platform.verify import verify
        print(json.dumps(verify(),indent=2))


if __name__=="__main__":
    main()
