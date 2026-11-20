#!/usr/bin/env python3
"""
SIRIUS Toolkit - Script 03: GGUF Model Diagnosis
=================================================
Open any GGUF model file and report its internals:
  - general metadata (architecture, context length, tokenizer, quant format)
  - full tensor inventory (every weight matrix inside the file)
  - parameter accounting per layer (attention vs MLP vs norms vs embeddings)
  - quantization mix (how many bytes each parameter group really uses)
  - the largest tensors ("where the parameters actually live")

This is the "X-ray" step of the SIRIUS project: before we edit a model's
weights (LoRA add / pruning remove), we must know exactly what is inside.

Usage
-----
    python 03_diagnose_gguf.py path/to/model.gguf
    python 03_diagnose_gguf.py model.gguf --json report.json --md report.md

Ollama stores its models as GGUF "blobs", so this script also works on them:
    Linux / macOS : ~/.ollama/models/blobs/sha256-...
    Windows       : %USERPROFILE%\\.ollama\\models\\blobs\\sha256-...

Requires:  pip install gguf   (pure Python, works on any laptop)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------- helpers

def human_size(n):
    """Format a byte count in a human friendly way."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0


def human_num(n):
    """Format a parameter count: 494032768 -> '494.03 M'."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f} B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f} M"
    if n >= 1_000:
        return f"{n / 1_000:.1f} K"
    return str(n)


# GGML quantization type ids -> readable names (stable across gguf versions)
QTYPE_NAMES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1",
    8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K_S", 12: "Q3_K_M",
    13: "Q3_K_L", 14: "Q4_K_S", 15: "Q4_K_M", 16: "Q5_K_S", 17: "Q5_K_M",
    18: "Q6_K", 19: "IQ2_XXS", 20: "IQ2_XS", 21: "Q2_K_S", 22: "IQ3_XS",
    23: "IQ3_XXS", 24: "IQ1_S", 25: "IQ4_NL", 26: "IQ3_S", 27: "IQ2_S",
    28: "IQ4_XS", 29: "I8", 30: "I1", 31: "TQ1_0", 32: "TQ2_0",
}

FILE_TYPE_NAMES = {
    0: "all F32", 1: "mostly F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0",
    8: "Q5_0", 9: "Q5_1", 10: "Q2_K", 11: "Q3_K_S", 12: "Q3_K_M",
    13: "Q3_K_L", 14: "Q4_K_S", 15: "Q4_K_M", 16: "Q5_K_S", 17: "Q5_K_M",
    18: "Q6_K", 19: "IQ2_XXS", 20: "IQ2_XS", 24: "IQ1_S",
}


def field_value(field):
    """Decode one GGUF metadata field into a Python value (version-proof)."""
    types = []
    for t in field.types:
        try:
            types.append(int(t))
        except (TypeError, ValueError):
            types.append(t)
    if not types:
        return None
    t0 = types[0]
    if t0 == 8:  # STRING
        return bytes(field.parts[-1]).decode("utf-8", "replace")
    if t0 == 9:  # ARRAY - summarize, never dump contents
        return "<array>"
    v = field.parts[-1]
    try:
        return v[0].item() if hasattr(v, "__len__") else v
    except Exception:
        return bytes(v).decode("utf-8", "replace")


# ------------------------------------------------------- tensor taxonomy

def classify(name):
    """Classify a tensor name into (layer_index_or_None, component_group)."""
    if name.startswith("blk."):
        rest = name.split(".", 2)[2] if name.count(".") >= 2 else name
        idx = int(name.split(".")[1])
        if "attn_norm" in rest or "post_attention_norm" in rest or "norm" in rest:
            return idx, "norms"
        if rest.startswith(("attn_q", "attn_k", "attn_v", "attn_o")):
            return idx, "attention"
        if rest.startswith(("ffn_gate", "ffn_up", "ffn_down")):
            return idx, "mlp"
        return idx, "other"
    if name.startswith("token_embd"):
        return None, "embedding"
    if name.startswith("output_norm"):
        return None, "output_norm"
    if name.startswith("output"):
        return None, "output_head"
    if name.startswith("rope") or name.startswith("pos_embd"):
        return None, "positional"
    return None, "other"


def qtype_name(tid):
    return QTYPE_NAMES.get(tid, f"type_{tid}")


# ------------------------------------------------------------------ main

def diagnose(path, top_n=12):
    from gguf import GGUFReader  # imported here so --help works without it

    reader = GGUFReader(path, mode="r")
    file_size = os.path.getsize(path)

    # ---- metadata (skip giant arrays) ----
    meta = {}
    for name, field in reader.fields.items():
        val = field_value(field)
        if isinstance(val, str) and val.startswith("<array"):
            meta[name] = val
        else:
            meta[name] = val

    # ---- tensor inventory ----
    tensors = []
    for t in reader.tensors:
        tensors.append({
            "name": t.name,
            "shape": [int(x) for x in t.shape],
            "qtype_id": int(t.tensor_type),
            "qtype": qtype_name(int(t.tensor_type)),
            "params": int(t.n_elements),
            "bytes": int(t.n_bytes),
        })

    total_params = sum(t["params"] for t in tensors)
    tensor_bytes = sum(t["bytes"] for t in tensors)

    # ---- group by component ----
    groups = {}
    blocks = {}
    for t in tensors:
        idx, comp = classify(t["name"])
        g = groups.setdefault(comp, {"tensors": 0, "params": 0, "bytes": 0, "qtypes": {}})
        g["tensors"] += 1
        g["params"] += t["params"]
        g["bytes"] += t["bytes"]
        g["qtypes"][t["qtype"]] = g["qtypes"].get(t["qtype"], 0) + t["params"]
        if idx is not None:
            b = blocks.setdefault(idx, {"params": 0, "bytes": 0,
                                        "attention": 0, "mlp": 0, "norms": 0})
            b["params"] += t["params"]
            b["bytes"] += t["bytes"]
            b[comp] += t["params"]

    # ---- per-component quant usage (bytes per parameter) ----
    for comp, g in groups.items():
        g["bytes_per_param"] = (g["bytes"] / g["params"]) if g["params"] else 0.0

    largest = sorted(tensors, key=lambda t: t["bytes"], reverse=True)[:top_n]

    arch = meta.get("general.architecture", "?")
    n_blocks = meta.get(f"{arch}.block_count", len(blocks) or None)

    result = {
        "file": os.path.abspath(path),
        "diagnosed_at": datetime.now(timezone.utc).isoformat(),
        "file_size_bytes": file_size,
        "tensor_bytes": tensor_bytes,
        "container_overhead_bytes": file_size - tensor_bytes,
        "metadata": meta,
        "total_params": total_params,
        "tensor_count": len(tensors),
        "block_count": n_blocks,
        "avg_bits_per_param": (tensor_bytes * 8.0 / total_params) if total_params else 0.0,
        "groups": groups,
        "blocks": {str(k): v for k, v in sorted(blocks.items())},
        "largest_tensors": largest,
        "tensors": tensors,
    }
    return result


def print_summary(r):
    m = r["metadata"]
    print("=" * 64)
    print("SIRIUS GGUF DIAGNOSIS")
    print("=" * 64)
    print(f"file            : {r['file']}")
    print(f"file size       : {human_size(r['file_size_bytes'])}")
    print(f"architecture    : {m.get('general.architecture', '?')}")
    print(f"model name      : {m.get('general.name', '?')}")
    print(f"quant format    : {FILE_TYPE_NAMES.get(m.get('general.file_type'), '?')}"
          f"  (file_type={m.get('general.file_type')})")
    arch = m.get("general.architecture", "qwen2")
    print(f"layers/blocks   : {m.get(arch + '.block_count', '?')}")
    print(f"hidden size     : {m.get(arch + '.embedding_length', '?')}")
    print(f"context length  : {m.get(arch + '.context_length', '?')}")
    print(f"attention heads : {m.get(arch + '.attention.head_count', '?')} "
          f"(KV heads: {m.get(arch + '.attention.head_count_kv', '?')})")
    print(f"tokenizer       : {m.get('tokenizer.ggml.model', '?')}")
    vocab = next((t for t in r["tensors"] if t["name"] == "token_embd.weight"), None)
    print(f"vocab size      : {vocab['shape'][1] if vocab else '?'}  (from token_embd shape)")
    print("-" * 64)
    print(f"TOTAL PARAMS    : {human_num(r['total_params'])}  ({r['total_params']:,})")
    print(f"avg bits/param  : {r['avg_bits_per_param']:.2f}")
    print(f"tensors         : {r['tensor_count']}")
    print("-" * 64)
    print(f"{'component':<14}{'params':>12}{'bytes':>12}{'B/param':>10}  qtypes")
    for comp in sorted(r["groups"], key=lambda c: -r["groups"][c]["params"]):
        g = r["groups"][comp]
        qt = ", ".join(f"{k}:{human_num(v)}" for k, v in
                       sorted(g["qtypes"].items(), key=lambda kv: -kv[1])[:3])
        print(f"{comp:<14}{human_num(g['params']):>12}{human_size(g['bytes']):>12}"
              f"{g['bytes_per_param']:>10.2f}  {qt}")
    print("-" * 64)
    print("largest tensors:")
    for t in r["largest_tensors"]:
        print(f"  {t['name']:<28}{t['qtype']:<8}{human_num(t['params']):>12}"
              f"  {human_size(t['bytes']):>10}  shape={t['shape']}")
    print("=" * 64)


def write_markdown(r, out_path):
    m = r["metadata"]
    L = []
    L.append("# SIRIUS GGUF Diagnosis Report")
    L.append("")
    L.append(f"- File: `{r['file']}`")
    L.append(f"- Diagnosed at: {r['diagnosed_at']}")
    L.append(f"- File size: {human_size(r['file_size_bytes'])} | "
             f"Total parameters: {human_num(r['total_params'])} "
             f"({r['total_params']:,}) | Avg {r['avg_bits_per_param']:.2f} bits/param")
    L.append(f"- Architecture: {m.get('general.architecture','?')} | "
             f"Name: {m.get('general.name','?')} | "
             f"Quant: {FILE_TYPE_NAMES.get(m.get('general.file_type'),'?')}")
    L.append("")
    L.append("## Parameter distribution by component")
    L.append("")
    L.append("| Component | Params | Bytes | Bytes/param | Main quant types |")
    L.append("|---|---:|---:|---:|---|")
    for comp in sorted(r["groups"], key=lambda c: -r["groups"][c]["params"]):
        g = r["groups"][comp]
        qt = ", ".join(sorted(g["qtypes"], key=g["qtypes"].get, reverse=True)[:3])
        L.append(f"| {comp} | {g['params']:,} | {human_size(g['bytes'])} | "
                 f"{g['bytes_per_param']:.2f} | {qt} |")
    L.append("")
    L.append("## Per-layer accounting (block index: attention / MLP / norms)")
    L.append("")
    L.append("| Block | Attention params | MLP params | Norm params | Total |")
    L.append("|---|---:|---:|---:|---:|")
    for k in sorted(r["blocks"], key=lambda x: int(x)):
        b = r["blocks"][k]
        L.append(f"| {k} | {b['attention']:,} | {b['mlp']:,} | {b['norms']:,} | {b['params']:,} |")
    L.append("")
    L.append("## Largest tensors")
    L.append("")
    L.append("| Tensor | Quant | Params | Bytes | Shape |")
    L.append("|---|---|---:|---:|---|")
    for t in r["largest_tensors"]:
        L.append(f"| {t['name']} | {t['qtype']} | {t['params']:,} | "
                 f"{human_size(t['bytes'])} | {t['shape']} |")
    L.append("")
    L.append("## Full metadata (arrays summarized)")
    L.append("")
    L.append("```")
    for k in sorted(r["metadata"]):
        L.append(f"{k} = {r['metadata'][k]}")
    L.append("```")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser(
        description="Diagnose the internals of a GGUF model file (SIRIUS toolkit)")
    ap.add_argument("gguf_path", help="path to a .gguf file (or an Ollama blob)")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="write full JSON report to this path")
    ap.add_argument("--md", dest="md_out", default=None,
                    help="write Markdown report to this path")
    ap.add_argument("--top", type=int, default=12,
                    help="how many largest tensors to list (default 12)")
    args = ap.parse_args()

    if not os.path.isfile(args.gguf_path):
        sys.exit(f"ERROR: file not found: {args.gguf_path}")

    try:
        result = diagnose(args.gguf_path, top_n=args.top)
    except ImportError:
        sys.exit("ERROR: the 'gguf' package is missing. Run:  pip install gguf")

    print_summary(result)

    base = os.path.splitext(os.path.basename(args.gguf_path))[0]
    json_out = args.json_out or f"diagnosis_{base}.json"
    md_out = args.md_out or f"diagnosis_{base}.md"
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    write_markdown(result, md_out)
    print(f"\nReports written:\n  {json_out}\n  {md_out}")


if __name__ == "__main__":
    main()
