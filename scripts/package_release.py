"""Package the active application, documentation and trained model artifacts."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
folders=["app","components","nexus","policies","docs","tests","scripts","docker",".github"]
files=["README.md","main.py","next.config.js","package.json","package-lock.json","requirements.txt","requirements-platform.txt","requirements.lock.txt","docker-compose.yml","docker-compose.platform.yml","playwright.config.js","pytest.ini",".eslintrc.json",".eslintignore",".dockerignore",".gitignore",".env.example","start.ps1"]
selected=[]
for name in folders:
    selected.extend(p for p in (ROOT/name).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc",".log"})
selected.extend(ROOT/name for name in files)
selected.extend((ROOT/"runtime/artifacts").glob("*.json"))
selected.extend((ROOT/"runtime/artifacts").glob("*.joblib"))
output=ROOT/"dist/NEXUS-4.0-final-project.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(selected)):
        if path.exists():
            archive.write(path,"nexus-scct/"+path.relative_to(ROOT).as_posix())
sha=hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix(".sha256").write_text(sha+"  "+output.name+"\n")
print(json.dumps(dict(path=str(output),bytes=output.stat().st_size,sha256=sha),indent=2))
