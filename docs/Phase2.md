# Phase 2: ESMFold HuggingFace Migration

## Context

Phase 1 is complete — PredictStructureApp has a working unified CLI with adapters, converters, normalizers, and backends (39 tests passing). The ESMFold adapter references the `esm-fold-hf` CLI command from `ESMFoldApp/esm_hf/scripts/hf_fold.py`.

Phase 2 promotes the HuggingFace ESMFold implementation as the primary interface by:
1. Renaming `hf_fold.py` → `esmfold_hf.py` (clearer name, matches the package)
2. Updating the CWL tool definition from legacy `esm-fold` → `esm-fold-hf`
3. Adding tests to ESMFoldApp's `esm_hf/` package (currently has zero pytest tests)
4. Building Docker images (Layer 2 base + Layer 3 BV-BRC) for GPU testing

**Why rename**: `hf_fold.py` is a generic name that doesn't identify the tool. `esmfold_hf.py` is self-documenting and matches the package name (`esm-hf`), the Dockerfile name (`esmfold_hf.def`), and the CLI command (`esm-fold-hf`).

**Console script name stays `esm-fold-hf`** — no change to the CLI command that users and PredictStructureApp reference.

---

## Scope

All changes are in the **ESMFoldApp** repository (`dxkb/ESMFoldApp/`). No PredictStructureApp changes needed (it references the CLI command `esm-fold-hf`, not the filename).

---

## Files Modified (in ESMFoldApp)

### 1. Rename: `esm_hf/scripts/hf_fold.py` → `esm_hf/scripts/esmfold_hf.py`

`git mv esm_hf/scripts/hf_fold.py esm_hf/scripts/esmfold_hf.py`

### 2. `esm_hf/__init__.py` — update import

```python
# Line 8: change
from .scripts.hf_fold import (
# to
from .scripts.esmfold_hf import (
```

### 3. `esm_hf/pyproject.toml` — update entry point

```toml
# Line 54: change
esm-fold-hf = "scripts.hf_fold:main"
# to
esm-fold-hf = "scripts.esmfold_hf:main"
```

### 4. `esm_hf/setup.py` — update entry point

```python
# Line 64: change
"esm-fold-hf=scripts.hf_fold:main",
# to
"esm-fold-hf=scripts.esmfold_hf:main",
```

### 5. `cwl/esmfold.cwl` — update baseCommand + Docker image

```yaml
# Line 10: change
baseCommand: [esm-fold]
# to
baseCommand: [esm-fold-hf]

# Line 14: change
dockerPull: "esmfold:latest"
# to
dockerPull: "dxkb/esmfold-bvbrc:latest-gpu"
```

Also removed the `cpu_offload` input (lines 73-79) — `esm-fold-hf` doesn't support `--cpu-offload` (that was legacy).

### 6. `esm_hf/Dockerfile` — update CMD (Layer 2 image)

The Dockerfile installs the package via `pip install -e .`, so the rename is picked up automatically.

```dockerfile
# Line 234: change
CMD ["python", "/workspace/test_installation.py"]
# to
CMD ["esm-fold-hf", "--help"]
```

**Build command**: `docker build -t dxkb/esmfold:latest-gpu -f Dockerfile .` (from `ESMFoldApp/esm_hf/`)

### 7. `esm_hf/esmfold_hf.def` — no changes needed

Copies the entire `scripts/` directory and resolves the entry point via `pip install -e .`.

### 8. NEW: `container/docker/Dockerfile.esmfold-hf-bvbrc` — Layer 3 BV-BRC image

Creates the `dxkb/esmfold-bvbrc:latest-gpu` image that PredictStructureApp's Docker backend references. Based on the HuggingFace base image (not the legacy OpenFold one).

Follows the same two-stage pattern as `Dockerfile.bvbrc` but uses `dxkb/esmfold:latest-gpu` (the HF image from step 6) as the base instead of `esmfold:prod`.

```dockerfile
# Stage 1: PATRIC Runtime Builder (identical to existing Dockerfile.bvbrc)
FROM ubuntu:20.04 AS runtime-builder
# ... clone runtime_build, build Perl, clone dev_container ...

# Stage 2: Final ESMFold HF + PATRIC Image
FROM dxkb/esmfold:latest-gpu

# Install Perl for BV-BRC integration
RUN apt-get -y update && apt-get -y install --no-install-recommends \
      perl cpanminus libfindbin-libs-perl libjson-perl libjson-xs-perl \
      libwww-perl libio-socket-ssl-perl libfile-slurp-perl make git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy PATRIC runtime from builder
COPY --from=runtime-builder /opt/patric-common /opt/patric-common
COPY --from=runtime-builder /dev_container /dev_container

# BV-BRC environment
ENV RT=/opt/patric-common/runtime
ENV KB_TOP=/kb/deployment
ENV IN_BVBRC_CONTAINER=1
ENV PATH=$PATH:$RT/bin
ENV PERL5LIB=$RT/lib/perl5:<BV-BRC module paths>

# Copy service files
COPY service-scripts/App-ESMFold.pl /service-scripts/
COPY app_specs/ESMFold.json /app_specs/

# Verify both ESMFold HF and Perl work
RUN esm-fold-hf --help && \
    perl -MBio::KBase::AppService::AppScript -e 'print "OK\n"'

CMD ["esm-fold-hf", "--help"]
```

**Key difference from legacy `Dockerfile.bvbrc`**: No conda, no OpenFold — just standard pip-installed `esm-fold-hf` CLI. Much simpler.

**Build command** (from ESMFoldApp root):
```bash
docker build --platform linux/amd64 \
  -t dxkb/esmfold-bvbrc:latest-gpu \
  -f container/docker/Dockerfile.esmfold-hf-bvbrc .
```

---

## New Files: Tests (~200 LOC across 3 files)

ESMFoldApp's `esm_hf/` package had zero pytest tests. The `pyproject.toml` already declared `testpaths = ["tests"]` and `pytest` in dev dependencies, but no `tests/` directory existed inside `esm_hf/`.

### `esm_hf/tests/conftest.py` (~15 LOC)

Shared fixtures:
- `sample_fasta(tmp_path)` — single-sequence FASTA (crambin, 46 residues)
- `multi_seq_fasta(tmp_path)` — two-sequence FASTA for batching tests

### `esm_hf/tests/test_cli.py` (~60 LOC)

Test CLI argument parsing **without loading the model** (no GPU needed):

| Test | What it verifies |
|------|-----------------|
| `test_create_parser_defaults` | Default values: model=facebook/esmfold_v1, max_tokens=1024, num_recycles=4, chunk_size=None, cpu_only=False, fp16=False |
| `test_create_parser_custom_args` | Custom args: `-i foo.fasta -o out/ --num-recycles 8 --cpu-only --fp16 --chunk-size 64` |
| `test_create_parser_required_args` | Missing `-i` or `-o` raises SystemExit |
| `test_num_recycles_range` | `--num-recycles 0` and `--num-recycles 48` both parse (no artificial bounds in argparse) |

### `esm_hf/tests/test_fasta.py` (~60 LOC)

Test FASTA reading and batching logic (pure functions, no model):

| Test | What it verifies |
|------|-----------------|
| `test_read_fasta_single` | Single-sequence FASTA returns `[("header", "SEQUENCE")]` |
| `test_read_fasta_multi` | Multi-sequence FASTA returns correct count and headers |
| `test_read_fasta_empty` | Empty file returns `[]` |
| `test_read_fasta_multiline_seq` | Multi-line sequence is concatenated |
| `test_batched_sequences_single_batch` | Short sequences fit in one batch |
| `test_batched_sequences_split` | Long sequences split across batches based on `max_tokens_per_batch` |
| `test_batched_sequences_exact_boundary` | Sequences at exact token limit stay in one batch |

### `esm_hf/tests/test_convert.py` (~60 LOC)

Test PDB output conversion (requires torch but NOT the ESMFold model):

| Test | What it verifies |
|------|-----------------|
| `test_convert_outputs_to_pdb_shape` | Mock tensor outputs produce valid PDB string list |
| `test_convert_outputs_pdb_content` | PDB string contains ATOM lines with correct residue info |
| `test_convert_outputs_bfactors` | B-factor column contains pLDDT values (0-1 range) |

These tests create minimal mock tensors mimicking `EsmForProteinFolding` output shape, so they run without GPU or model download.

---

## Execution Order

```
Step 1:  git mv hf_fold.py → esmfold_hf.py
Step 2:  Update __init__.py, pyproject.toml, setup.py (entry points)
Step 3:  Update cwl/esmfold.cwl (baseCommand + Docker image)
Step 4:  Update esm_hf/Dockerfile CMD
Step 5:  Create container/docker/Dockerfile.esmfold-hf-bvbrc (Layer 3)
Step 6:  Create esm_hf/tests/ (conftest, test_cli, test_fasta, test_convert)
Step 7:  Verify: cd esm_hf && pip install -e ".[dev]" && pytest tests/ -v
Step 8:  Verify: which esm-fold-hf (CLI still works)
Step 9:  Verify: cwltool --validate cwl/esmfold.cwl
```

---

## Verification

1. **Pytest**: `cd ESMFoldApp/esm_hf && pip install -e ".[dev]" && pytest tests/ -v`
2. **CLI entry point**: `which esm-fold-hf && esm-fold-hf --help` (should show all flags including `--num-recycles`)
3. **CWL validation**: `cd ESMFoldApp && cwltool --validate cwl/esmfold.cwl`
4. **Import check**: `python -c "from scripts.esmfold_hf import main; print('OK')"`
5. **Package import**: `python -c "from esm_hf import main; print('OK')"`
6. **Docker Layer 2**: `docker build -t dxkb/esmfold:latest-gpu -f Dockerfile .` (from `ESMFoldApp/esm_hf/`)
7. **Docker Layer 3**: `docker build --platform linux/amd64 -t dxkb/esmfold-bvbrc:latest-gpu -f container/docker/Dockerfile.esmfold-hf-bvbrc .` (from ESMFoldApp root)

---

## What is NOT in scope

- BV-BRC service script (`App-ESMFold.pl`) — uses legacy `esm-fold`, separate migration
- Legacy Dockerfiles in `ESMFoldApp/container/docker/` — those are for the old OpenFold-based `esm-fold`
- PredictStructureApp changes — it uses the CLI name `esm-fold-hf`, not the filename
- Output parity validation (requires GPU + model download, deferred to integration testing)
