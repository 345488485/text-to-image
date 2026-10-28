"""Submit the local 512px/20-step workflow and verify its real PNG output."""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:8188"


def request(path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(HOST + path, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    graph = json.loads((ROOT / "workflow-api.json").read_text(encoding="utf-8"))
    result = request("/prompt", {"prompt": graph})
    prompt_id = result["prompt_id"]
    print(f"QUEUED {prompt_id}", flush=True)
    started = time.monotonic()
    while time.monotonic() - started < 1800:
        history = request(f"/history/{prompt_id}")
        if prompt_id not in history:
            time.sleep(5)
            continue
        entry = history[prompt_id]
        (ROOT / ".runtime" / "smoke-history.json").write_text(
            json.dumps(entry, indent=2), encoding="utf-8")
        if entry["status"]["status_str"] != "success":
            raise RuntimeError(json.dumps(entry["status"], ensure_ascii=False))
        image = entry["outputs"]["10"]["images"][0]
        output_root = (ROOT / "output").resolve()
        path = (output_root / image["subfolder"] / image["filename"]).resolve()
        if not path.is_relative_to(output_root):
            raise RuntimeError("Unexpected output path")
        with Image.open(path) as png:
            assert png.size == (512, 512), png.size
            png.verify()
        report = dict(status="success", image=str(path),
                      seconds=round(time.monotonic() - started, 2),
                      sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      width=512, height=512, steps=20, seed=42)
        (ROOT / ".runtime" / "smoke-result.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        return
    raise TimeoutError("No completed generation within 30 minutes; inspect server logs")


if __name__ == "__main__":
    main()
