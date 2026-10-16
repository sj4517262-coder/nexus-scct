"""Start both local services and stop both cleanly on Ctrl+C."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Start the NEXUS local workspace")
    parser.add_argument("--production", action="store_true", help="Serve a previously built frontend")
    args = parser.parse_args()
    node = shutil.which("node")
    if not node or not (ROOT/"node_modules/next/dist/bin/next").exists():
        sys.exit("Install Node.js 20+ and run npm ci in the project folder first.")
    for port in (3000, 8000):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                sys.exit(f"Port {port} is already in use. Stop the existing service before starting NEXUS.")
    if args.production and not (ROOT/".next/BUILD_ID").exists():
        sys.exit("Run npm run build before starting in production mode.")
    env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1", "PYTHONUNBUFFERED": "1"}
    processes = []
    try:
        processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, env=env))
        processes.append(subprocess.Popen([node, str(ROOT/"node_modules/next/dist/bin/next"), "start" if args.production else "dev", "--hostname", "127.0.0.1", "--port", "3000"], cwd=ROOT, env=env))
        print("\nNEXUS: http://localhost:3000 | API: http://127.0.0.1:8000/docs\nPress Ctrl+C to stop both services.\n", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(.5)
        failed = next((p.returncode for p in processes if p.poll() is not None), 1)
        if failed:
            raise SystemExit(failed)
    except KeyboardInterrupt:
        print("\nStopping NEXUS...")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
