# Deviation log — Option A (2026-11-28)

- Kaggle environment shipped `torchao 0.10.0`, incompatible with the installed PEFT
  (requires >0.16.0). R1's first attempt failed at adapter injection before any training
  step. This is an environment dependency, not a recipe or data change.
- Fix applied to the notebook setup cell: `pip install -U torchao`. The frozen recipe,
  data hashes, seed, grader and gates are unchanged.
- Local GTX 1650 Ti lost its CUDA driver mid-run; all ablation training returned to
  Kaggle T4 x2 (same class as Pass 5). R0 remains the shipped Pass 5 adapter.
