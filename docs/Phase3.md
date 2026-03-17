# Phase 3: CWL Integration for PredictStructureApp

## Context

Phases 1-2 are complete:
- **Phase 1**: Unified CLI with adapters, converters, normalizers, and backends (subprocess + docker) — 39 tests passing
- **Phase 2**: ESMFold HF migration in ESMFoldApp (rename, entry points, tests, BV-BRC Dockerfile) — 20 tests passing

Phase 3 adds CWL (Common Workflow Language) as a third execution backend, enabling PredictStructureApp to run predictions through `cwltool` or the GoWe workflow scheduler. This is the bridge between the Python CLI (Phases 1-2) and the BV-BRC service layer (Phase 4).

**Why CWL**: Per-tool CWL definitions already exist (`boltzApp/cwl/boltz.cwl`, `ChaiApp/cwl/chailab.cwl`, `ESMFoldApp/cwl/esmfold.cwl`). Phase 3 creates a **unified** CWL tool that wraps `predict-structure` and a CWL backend that invokes it, so users get one tool definition that dispatches to any of the four prediction tools.

---

## Scope: PredictStructureApp only

All changes in `PredictStructureApp/`. The per-tool CWL files in other repos are not modified.

---

## Design Decisions

1. **Single CWL tool, not four**: `predict-structure.cwl` wraps the unified CLI. Tool selection is a CWL enum input. This mirrors Phase 1's adapter pattern at the CWL level.

2. **`--backend subprocess` hardcoded in CWL**: When CWL runs `predict-structure` inside a Docker container, the CLI uses subprocess backend (tools are installed in the container). The CWL backend is only for the *outer* invocation.

3. **Per-tool Docker images in CWL**: The CWL tool uses `InlineJavascriptRequirement` to select the correct Docker image based on the `tool` input, maintaining the delegation pattern.

4. **GoWe compatibility**: Includes `cwltool:CUDARequirement` in hints section matching the pattern from existing CWL tools across the workspace.

---

## Files Created (7 new)

### 1. `cwl/tools/predict-structure.cwl` (~160 LOC)

Unified CWL v1.2 CommandLineTool wrapping `predict-structure <tool> <input>`.

**Inputs** (14 total):
| Input | CWL Type | CLI Flag | Description |
|-------|----------|----------|-------------|
| `tool` | enum (boltz,chai,alphafold,esmfold) | positional | Prediction tool |
| `input_file` | File | positional | Input FASTA file |
| `output_dir` | string? | `--output-dir` | Output directory |
| `num_samples` | int? | `--num-samples` | Structure samples (Boltz/Chai) |
| `num_recycles` | int? | `--num-recycles` | Recycling iterations |
| `seed` | int? | `--seed` | Random seed |
| `device` | enum? (gpu,cpu) | `--device` | Compute device |
| `msa` | File? | `--msa` | MSA file |
| `output_format` | enum? (pdb,mmcif) | `--output-format` | Structure format |
| `sampling_steps` | int? | `--sampling-steps` | Sampling steps |
| `use_msa_server` | boolean? | `--use-msa-server` | MSA server toggle |
| `af2_data_dir` | Directory? | `--af2-data-dir` | AlphaFold DB dir |
| `af2_model_preset` | string? | `--af2-model-preset` | AF2 model preset |
| `af2_db_preset` | string? | `--af2-db-preset` | AF2 DB preset |

**Outputs** (4):
| Output | CWL Type | Glob | Description |
|--------|----------|------|-------------|
| `predictions` | Directory | `$(inputs.output_dir)` | All prediction outputs |
| `structure_files` | File[]? | `output_dir/**/*.{pdb,cif}` | Structure files |
| `metadata` | File? | `output_dir/metadata.json` | Metadata |
| `confidence` | File? | `output_dir/confidence.json` | Confidence scores |

**Key features**:
- Dynamic Docker image selection via JavaScript expression
- `cwltool:CUDARequirement` hint for GPU
- `NetworkAccess` for MSA server
- Hardcoded `--backend subprocess` argument

### 2. `predict_structure/backends/cwl.py` (~160 LOC)

CWL execution backend that:
- Reverse-maps adapter `build_command()` output into CWL job YAML
- Generates temp job YAML file
- Invokes configurable CWL runner (`cwltool`, `toil-cwl-runner`, or custom)

Handles File/Directory CWL types, boolean flags, integer values, and skips meta-flags (`--backend`, `--image`).

### 3-6. `cwl/jobs/crambin-{boltz,chai,esmfold,alphafold}.yml`

Example/test job YAML files for each tool, using `test_data/simple_protein.fasta`.

### 7. `docs/Phase3.md` (this document)

---

## Files Modified (3)

### `predict_structure/backends/__init__.py`
- Import `CWLBackend`
- Add `"cwl": CWLBackend` to `BACKENDS` dict
- Update `get_backend()` return type

### `predict_structure/cli.py`
- Add `"cwl"` to `--backend` choices
- Add `--cwl-runner` and `--cwl-tool` options
- Pass CWL options to backend constructor

### `pyproject.toml`
- Add `cwl` optional dependency group (`pyyaml>=6.0`, `cwltool>=3.1`)
- Add `cwl` to `all` group
- Register pytest markers (`cwl`, `docker`, `gpu`)

---

## Tests (30 new tests across 3 files + 4 in test_cli.py)

### `tests/test_cwl_tool.py` (~110 LOC, 25 tests)

CWL structure validation by YAML parsing + cwltool:
- 12 structure tests (version, class, baseCommand, inputs, outputs, Docker JS, CUDA)
- 1 cwltool validation test
- 12 job YAML tests (parametrized: 4 files x 3 assertions)

### `tests/test_cwl_backend.py` (~170 LOC, 16 tests)

Backend unit tests with mocked subprocess:
- 4 registry tests
- 3 defaults tests
- 7 job YAML building tests (boltz, esmfold, chai, msa, alphafold, skip flags)
- 5 run() tests (invocation, exit codes, custom runner, YAML on disk, timeout)

### `tests/test_cwl_acceptance.py` (~80 LOC, 7 tests)

Three-tier acceptance tests:
- **Tier 1** (5 tests, `@pytest.mark.cwl`): CWL validation, job YAML loading, backend roundtrip, tool coverage
- **Tier 2** (1 test, `@pytest.mark.docker`): ESMFold dry-run with `--no-container`
- **Tier 3** (1 test, `@pytest.mark.gpu`): Full ESMFold prediction (manual/nightly)

### `tests/test_cli.py` (4 new tests added)
- `test_help_shows_cwl_backend`, `test_help_shows_cwl_options`
- `test_get_backend_cwl`, `test_get_backend_cwl_with_runner`

---

## Verification

1. **CWL validation**: `cwltool --validate cwl/tools/predict-structure.cwl` — valid
2. **Full test suite**: `pytest tests/ -v` — 92 passed (2 pre-existing pyarrow failures)
3. **CWL tests only**: `pytest tests/test_cwl_*.py tests/test_cli.py -v` — 63 passed
4. **CLI help**: `predict-structure --help` — shows `cwl` backend and `--cwl-runner`/`--cwl-tool` options

---

## Test Results Summary

| Test file | Tests | Status |
|-----------|-------|--------|
| test_cwl_tool.py | 25 | All pass |
| test_cwl_backend.py | 16 | All pass |
| test_cwl_acceptance.py | 7 | All pass |
| test_cli.py (CWL additions) | 4 | All pass |
| **Total new** | **52** | **All pass** |

---

## What is NOT in scope

- Per-tool CWL files (already exist in boltzApp, ChaiApp, ESMFoldApp)
- CWL workflows (scatter/gather, multi-tool pipelines)
- GoWe scheduler integration testing (requires BV-BRC infrastructure)
- BV-BRC service script (`App-PredictStructure.pl`) — Phase 4
- Full GPU acceptance tests (requires GPU nodes)
