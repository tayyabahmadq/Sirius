#!/usr/bin/env python3
"""Merge the Stage B LoRA adapter into Qwen2.5-Coder-1.5B-Instruct locally."""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE = r"C:\Users\ctayy\AppData\Local\Temp\qwen15b"
ADAPTER = "artifacts/sirius_lora_adapter_pass5"
OUT = "stageb_merged"

print("loading base...", flush=True)
base = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float16,
                                            device_map="cpu")
tok = AutoTokenizer.from_pretrained(ADAPTER)
print("loading adapter...", flush=True)
model = PeftModel.from_pretrained(base, ADAPTER)
print("merging...", flush=True)
merged = model.merge_and_unload()
merged.save_pretrained(OUT, safe_serialization=True)
tok.save_pretrained(OUT)
print("MERGED ->", OUT, flush=True)
