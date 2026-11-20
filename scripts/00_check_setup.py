#!/usr/bin/env python3
"""
SIRIUS Toolkit - Script 00: Setup Check
=======================================
Checks that your laptop is ready for the SIRIUS Phase 1 workflow:
  - Python version
  - RAM and free disk space
  - Ollama installed + reachable
  - the 'gguf' Python package (needed by script 03)
  - internet connectivity to Hugging Face / Ollama

Run it first. Everything it reports as PASS/WARN/FAIL comes with a fix hint.

Usage
-----
    python 00_check_setup.py          (or:  python3 00_check_setup.py)
"""

import os
import shutil
import subprocess
import sys
import urllib.request

OK, WARN, FAIL = "PASS ", "WARN ", "FAIL "


def check(name, ok, hint, level="fail"):
    """level: 'fail' = blocker, 'warn' = only a warning."""
    if ok:
        print(f"  [{OK}] {name}")
        return True
    tag = FAIL if level == "fail" else WARN
    print(f"  [{tag}] {name}")
    print(f"         hint: {hint}")
    return False if level == "fail" else True


def ram_gb():
    # Linux
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    # macOS
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                             capture_output=True, text=True)
        return int(out.stdout.strip()) / 1024 ** 3
    except Exception:
        pass
    # Windows
    try:
        out = subprocess.run(["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
                             capture_output=True, text=True)
        for line in out.stdout.split():
            if line.isdigit():
                return int(line) / 1024 ** 3
    except Exception:
        pass
    return None


def main():
    print("SIRIUS Phase 1 - Setup Check")
    print("=" * 60)
    problems = 0

    # --- python ---
    v = sys.version_info
    check(f"Python {'.'.join(map(str, v[:3]))}", v >= (3, 9),
          "SIRIUS scripts need Python 3.9+. Install from python.org.")
    problems += 0 if v >= (3, 9) else 1

    # --- RAM ---
    ram = ram_gb()
    if ram:
        ok = ram >= 7.0
        check(f"RAM {ram:.1f} GB", ok,
              "8 GB is enough for 0.5B models; close heavy apps while running.",
              level="warn")
    else:
        print(f"  [{WARN}] RAM unknown (auto-detect failed) - if you have 8 GB you are fine.")

    # --- disk ---
    target = os.path.expanduser("~")
    free = shutil.disk_usage(target).free
    check(f"Free disk {free / 1024 ** 3:.0f} GB (home)", free > 8 * 1024 ** 3,
          "Models need ~8 GB total. Free up space or use another disk.",
          level="warn")

    # --- gguf package ---
    try:
        import gguf  # noqa: F401
        check("Python package 'gguf' installed", True, "")
    except ImportError:
        check("Python package 'gguf' installed", False,
              "run:  pip install gguf   (needed by script 03)")

    # --- ollama ---
    ollama_found = False
    try:
        out = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        ollama_found = out.returncode == 0
        ver = (out.stdout or out.stderr).strip()
    except FileNotFoundError:
        ver = ""
    check(f"Ollama installed {('- ' + ver) if ver else ''}", ollama_found,
          "install from https://ollama.com/download, then open a new terminal.")

    if ollama_found:
        try:
            with urllib.request.urlopen("http://localhost:11434/api/version", timeout=5):
                check("Ollama server reachable (localhost:11434)", True, "")
        except Exception:
            check("Ollama server reachable (localhost:11434)", False,
                  "start it:  'ollama serve'  in one terminal, or open the Ollama app.",
                  level="warn")

    # --- internet ---
    net = False
    for url in ("https://ollama.com", "https://huggingface.co"):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=8):
                net = True
                break
        except Exception:
            continue
    check("Internet reachable (ollama.com / huggingface.co)", net,
          "model downloads need internet; corporate proxies may block them.")

    print("=" * 60)
    if problems or not ollama_found:
        print("Fix the FAIL items above, then run this script again.")
        print("After everything passes, start with script 01_pull_models.py")
    else:
        print("You are ready. Order of runs:")
        print("  1. python 01_pull_models.py --core")
        print("  2. python 04_sirius_baseline.py --quick")
        print("  3. python 03_diagnose_gguf.py <your .gguf file>")
        print("  4. python 05_compare_models.py --quick")


if __name__ == "__main__":
    main()
