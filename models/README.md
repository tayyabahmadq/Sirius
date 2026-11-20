# Model artifacts

The fine-tuned GGUFs are deliberately **not** in git: they are 420–506 MB and GitHub caps
individual files at 100 MB. Download the quant you want and place it next to
`../configs/Modelfile.sirius`.

## Downloads

| Artifact | Size | Link | Notes |
|---|---:|---|---|
| `sirius_final_Q6_K.gguf` | 505.7 MB | [Google Drive](https://drive.google.com/uc?id=1lSO3-OHGb6QJu7oNOiSU1BoOFKu5lCnD) | **Primary**, shipped model (Pass 5 adapter at scale s=0.5) |
| `sirius_final_Q5_K_M.gguf` | 420.1 MB | [Google Drive](https://drive.google.com/uc?id=1oNTgHNsoOabFGxqWroCCZ7XYbCFdGkYt) | Fallback if Q6_K is too large for your device |

```bash
# quick download with gdown
pip install gdown
gdown "https://drive.google.com/uc?id=1lSO3-OHGb6QJu7oNOiSU1BoOFKu5lCnD" -O sirius_final_Q6_K.gguf
```

## Load in Ollama

```bash
cd configs                       # the Modelfile uses a relative FROM path
ollama create sirius-final -f Modelfile.sirius
ollama run sirius-final "Review: hashlib.md5(pw.encode()).hexdigest() — name the vulnerability"
```

The `Modelfile.sirius` pins the exact acceptance settings:

```text
FROM ./sirius_final_Q6_K.gguf
PARAMETER temperature 0.2
PARAMETER num_predict 240
SYSTEM You are a security auditor assistant. Answer concisely, technically, and name the exact issue.
```

These match `04_sirius_baseline.py`, so scores are directly comparable to the reported
[results](../docs/04-final-results.md).

## Sizes & quantization notes

- Q8_0 base: 644.4 MB. Q6_K final: 505.7 MB. Q5_K_M final: 420.1 MB — all fit an 8 GB
  CPU laptop or a free Colab runtime.
- llama.cpp reported `144 of 290 tensors required fallback quantization`; the Q6_K artifact
  is 6.71 BPW. The dual PPL gate was re-checked after export (ratio 0.923 < 1.30).
