"""Download only three pinned Comfy-Org files, without a second model cache."""
import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVISION = "530a4c94f92c35ef6818b1b035a983fe9dcf5f54"
FILES = (
    "diffusion_models/moss_image_sft_int8_convrot.safetensors",
    "text_encoders/qwen3.5_9b_w4a8_gptq.safetensors",
    "vae/flux2-vae_small.safetensors",
)
RESERVE = 5 * 1024**3


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="https://huggingface.co")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    url = f"{args.endpoint}/api/models/Comfy-Org/MOSS-Image/revision/{REVISION}?blobs=true"
    with urllib.request.urlopen(url, timeout=30) as response:
        metadata = json.load(response)
    assert metadata["sha"] == REVISION, "Unexpected model revision"
    siblings = {item["rfilename"]: item for item in metadata["siblings"]}
    plan = []
    for name in FILES:
        lfs = siblings[name]["lfs"]
        target = ROOT / "models" / name
        part = target.with_suffix(target.suffix + ".part")
        digest = lfs["sha256"]
        size = lfs["size"]
        assert len(digest) == 64 and size > 0
        if target.exists():
            if target.stat().st_size != size or sha256(target) != digest:
                raise RuntimeError(f"Existing file does not match; preserved: {target}")
            remaining = 0
        else:
            offset = part.stat().st_size if part.exists() else 0
            assert offset <= size, f"Oversized partial preserved: {part}"
            remaining = size - offset
        plan.append(dict(name=name, size=size, sha256=digest, remaining=remaining))
    free = shutil.disk_usage(ROOT).free
    required = sum(item["remaining"] for item in plan)
    manifest = dict(repo="Comfy-Org/MOSS-Image", revision=REVISION,
                    endpoint=args.endpoint, free_bytes=free,
                    remaining_bytes=required, reserve_bytes=RESERVE, files=plan)
    (runtime / "model-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    if free < required + RESERVE:
        raise RuntimeError("Insufficient space with 5GiB reserve; no files deleted")
    if args.preflight_only:
        return
    for item in plan:
        target = ROOT / "models" / item["name"]
        if target.exists():
            print(f"VERIFIED {target}", flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(target.suffix + ".part")
        subprocess.run([
            "curl.exe", "--location", "--fail", "--continue-at", "-",
            "--connect-timeout", "15", "--max-time", "3600", "--retry", "0",
            "--speed-time", "120", "--speed-limit", "1024",
            "--output", str(part),
            f"{args.endpoint}/Comfy-Org/MOSS-Image/resolve/{REVISION}/{item['name']}",
        ], check=True)
        if part.stat().st_size != item["size"] or sha256(part) != item["sha256"]:
            raise RuntimeError(f"Download failed verification; partial preserved: {part}")
        part.rename(target)
        print(f"VERIFIED {target} SHA256={item['sha256']}", flush=True)


if __name__ == "__main__":
    main()
