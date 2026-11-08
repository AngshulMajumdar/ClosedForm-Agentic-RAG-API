"""Check that the server files remain byte-identical to the tested Space release."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
manifest=json.loads((HERE/"reports/source_compatibility.json").read_text())
fail=[]
for filename, sha in manifest["original_space_files_sha256"].items():
    expected=HERE/("docs/HF_SPACE_README.md" if filename=="README.md" else filename)
    if not expected.is_file():
        fail.append(f"MISSING: {filename}")
    elif hashlib.sha256(expected.read_bytes()).hexdigest()!=sha:
        fail.append(f"CHANGED: {filename}")
if fail:
    raise SystemExit("Source compatibility check failed:\n"+"\n".join(fail))
print(f"PASS: {len(manifest['original_space_files_sha256'])} original Space files identical")
