#!/usr/bin/env python3
"""
SIRIUS Toolkit - Script 02: Download Raw GGUF Files from Hugging Face
=====================================================================
Ollama pulls models in its own cache. For weight-space *diagnosis* and later
fine-tuning we also want the raw .gguf files we can open ourselves.
This script downloads them from Hugging Face with resume support, so an
interrupted download continues where it stopped (just re-run it).

Default downloads (Qwen2.5-0.5B, the SIRIUS target base):
  1. official Instruct GGUF, Q4_K_M  (Qwen team)      ~491 MB
  2. base (pretrain) GGUF,  Q4_K_M  (QuantFactory)    ~398 MB

Usage
-----
    python 02_download_gguf.py               # download the two defaults
    python 02_download_gguf.py --check       # show sizes without downloading
    python 02_download_gguf.py --url <any gguf url>
    python 02_download_gguf.py --dir ./gguf  # choose target folder

Requires:  stdlib only. Python 3.9+.
"""

import argparse
import os
import sys
import time
import urllib.request

DEFAULT_FILES = [
    ("qwen2.5-0.5b-instruct-q4_k_m.gguf",
     "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"),
    ("qwen2.5-0.5b-base-q4_k_m.gguf",
     "https://huggingface.co/QuantFactory/Qwen2.5-0.5B-GGUF/resolve/main/Qwen2.5-0.5B.Q4_K_M.gguf"),
]


def remote_size(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers.get("Content-Length", 0))


def download(url, dest, chunk=1 << 20):
    tmp = dest + ".part"
    done = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    total = remote_size(url)
    if done >= total > 0:
        os.replace(tmp, dest)
        print(f"  already complete: {dest}")
        return
    headers = {"Range": f"bytes={done}-"} if done else {}
    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "ab") as f:
        while True:
            block = r.read(chunk)
            if not block:
                break
            f.write(block)
            done += len(block)
            if total:
                pct = done / total * 100
                speed = done / max(time.time() - t0, 0.1) / 1024
                print(f"\r  {done / 1e6:8.1f} / {total / 1e6:.1f} MB  "
                      f"({pct:5.1f}%)  {speed:7.0f} KB/s", end="")
    print()
    os.replace(tmp, dest)
    print(f"  saved: {dest}")


def main():
    ap = argparse.ArgumentParser(description="Download raw GGUF files from Hugging Face (resumable)")
    ap.add_argument("--url", default=None, help="download a single GGUF URL instead of the defaults")
    ap.add_argument("--dir", default="gguf", help="target directory (default ./gguf)")
    ap.add_argument("--check", action="store_true", help="only show remote sizes")
    args = ap.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    jobs = [(os.path.basename(args.url).split("?")[0], args.url)] if args.url else DEFAULT_FILES

    for name, url in jobs:
        dest = os.path.join(args.dir, name)
        try:
            size = remote_size(url)
            print(f"{name}  ->  {size / 1e6:.1f} MB")
        except Exception as e:
            print(f"WARNING: cannot HEAD {url} ({e})")
            size = 0
        if args.check:
            continue
        if os.path.exists(dest) and size and os.path.getsize(dest) == size:
            print("  already downloaded, skipping")
            continue
        try:
            download(url, dest)
        except KeyboardInterrupt:
            sys.exit("\nInterrupted - run this script again to resume.")
        except Exception as e:
            sys.exit(f"ERROR downloading {url}: {e}\n"
                     "Re-run the script - downloads resume from where they stopped.")

    print("\nNext step: diagnose the file(s) with script 03, e.g.")
    print(f"  python 03_diagnose_gguf.py {os.path.join(args.dir, jobs[0][0])}")


if __name__ == "__main__":
    main()
