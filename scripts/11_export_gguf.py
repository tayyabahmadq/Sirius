#!/usr/bin/env python3
"""Lean GGUF export: llama.cpp convert + quantize, no llama-cpp-python wheel.
The wheel build OOM-killed a Colab runtime; this path only compiles the small
llama-quantize utility with make.
"""
import argparse, os, shutil, subprocess, sys

def sh(cmd, cwd=None):
    print(f"\n$ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"FAILED ({r.returncode}): {cmd}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", required=True)
    ap.add_argument("--base-name", default="sirius_final")
    args = ap.parse_args()

    root = os.path.abspath(".")
    llama = os.path.join(root, "llama.cpp")
    if not os.path.isdir(llama):
        sh("git clone --depth 1 https://github.com/ggerganov/llama.cpp.git llama.cpp",
           cwd=root)

    convert = os.path.join(llama, "convert_hf_to_gguf.py")
    if not os.path.isfile(convert):
        convert = os.path.join(llama, "convert.py")

    f16 = os.path.join(root, args.base_name + ".f16.gguf")
    if not os.path.isfile(f16):
        sh(f'python "{convert}" "{args.merged}" --outfile "{f16}" --outtype f16', cwd=root)
    else:
        print(f"Reusing existing {f16}", flush=True)

    # llama.cpp replaced Make with CMake; build only the quantize tool.
    quant_bin = os.path.join(llama, "build", "bin", "llama-quantize")
    if not os.path.isfile(quant_bin):
        sh('cmake -B build -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF', cwd=llama)
        sh('cmake --build build --target llama-quantize -j4', cwd=llama)
    if not os.path.isfile(quant_bin):
        alt = os.path.join(llama, "llama-quantize")
        if os.path.isfile(alt):
            quant_bin = alt

    outs = []
    for q in ("Q6_K", "Q5_K_M"):
        out = os.path.join(root, f"{args.base_name}_{q}.gguf")
        sh(f'"{quant_bin}" "{f16}" "{out}" {q}', cwd=root)
        mb = os.path.getsize(out) / 1e6
        print(f" -> {out} ({mb:.1f} MB)", flush=True)
        outs.append(out)

    mf = """FROM ./{q6}

PARAMETER temperature 0.2
PARAMETER num_predict 240
SYSTEM You are a security auditor assistant. Answer concisely, technically, and name the exact issue.
""".format(q6=args.base_name + "_Q6_K.gguf")
    with open(os.path.join(root, "Modelfile.sirius"), "w") as f:
        f.write(mf)
    print("Wrote Modelfile.sirius")
    print("DONE", outs)

if __name__ == "__main__":
    main()
