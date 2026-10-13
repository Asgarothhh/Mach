#!/usr/bin/env python3
"""Download pinned speech model artifacts and print hashes for the lock file.

Usage:
    python scripts/fetch_models.py --list
    python scripts/fetch_models.py silero-tts-v5_5_ru --output-dir models/tts
    python scripts/fetch_models.py silero-tts-v5_cis_base_nostress --output-dir models/tts

The script is deliberately dependency-free (stdlib only) so it can run before
the venv is ready. After the download it prints a YAML snippet with SHA-256;
paste the hash into ``config/models.lock.yaml``.

Note (SSOT §4.2): ``silero-tts-v5_5_ru`` is CC BY-NC-SA 4.0 — demo/evaluation
only until a commercial license decision is recorded in LICENSES.md.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS: dict[str, dict[str, str]] = {
    "silero-tts-v5_5_ru": {
        "url": "https://models.silero.ai/models/tts/ru/v5_5_ru.pt",
        "filename": "v5_5_ru.pt",
        "license": "CC BY-NC-SA 4.0 (demo-only until commercial approval)",
    },
    "silero-tts-v5_cis_base_nostress": {
        "url": "https://models.silero.ai/models/tts/ru/v5_cis_base_nostress.pt",
        "filename": "v5_cis_base_nostress.pt",
        "license": "MIT",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    print(f"downloading {url}")
    with urllib.request.urlopen(url) as response, tmp.open("wb") as fh:  # noqa: S310
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            fh.write(block)
    tmp.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", nargs="?", help="model id (see --list)")
    parser.add_argument("--list", action="store_true", help="list known model ids")
    parser.add_argument("--output-dir", default="models", help="target directory")
    parser.add_argument("--force", action="store_true", help="re-download if exists")
    args = parser.parse_args()

    if args.list or not args.model:
        for model_id, meta in MODELS.items():
            print(f"{model_id:38s} {meta['license']:55s} {meta['url']}")
        return 0

    meta = MODELS.get(args.model)
    if meta is None:
        print(f"unknown model id: {args.model!r}; use --list", file=sys.stderr)
        return 2

    destination = Path(args.output_dir) / meta["filename"]
    if destination.is_file() and not args.force:
        print(f"already present: {destination}")
    else:
        download(meta["url"], destination)

    digest = sha256(destination)
    print()
    print(f"file:   {destination}")
    print(f"sha256: {digest}")
    print("lock snippet (paste into config/models.lock.yaml):")
    print(f"  - id: {args.model}")
    print(f"    sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
