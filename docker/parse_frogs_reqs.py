#!/usr/bin/env python3
"""
Parse frogs-conda-requirements.yaml and print only the bioinformatics tool
packages (one per line), skipping:
  - R / Bioconductor packages (incompatible libffi with python=3.7)
  - blast (openssl conflict with python=3.7 / openssl=1.0.2)
  - frogs itself (already installed in pass 1)
  - rdptool (bundled inside the frogs package)
  - channel names (conda-forge, bioconda)
"""
import re
import sys

SKIP_NAMES = {"frogs", "blast", "rdptool", "conda-forge", "bioconda"}
yaml_path = sys.argv[1]

pkgs = []
with open(yaml_path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line in ("channels:", "dependencies:"):
            continue
        m = re.match(r"^-\s*(.+)", line)
        if not m:
            continue
        # Normalize "name =version" or "name= version" → "name=version"
        pkg = re.sub(r"\s*=\s*", "=", m.group(1).split("#")[0].strip())
        name = re.split(r"[=<>!]", pkg)[0]
        if name in SKIP_NAMES:
            continue
        if name.startswith("r-") or name.startswith("bioconductor-"):
            continue
        pkgs.append(pkg)

print(" ".join(pkgs))
