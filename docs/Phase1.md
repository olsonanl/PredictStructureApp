# Phase 1 Implementation Plan: PredictStructureApp Foundation

## Context

PredictStructureApp wraps 4 protein structure prediction tools (Boltz-2, Chai-1, AlphaFold2, ESMFold) behind a unified Python CLI (`predict-structure`). Phase 0 created the scaffold: abstract `BaseAdapter`, a click CLI stub, `pyproject.toml`, and BV-BRC app spec. Phase 1 fills in all concrete implementations — adapters, format converters, output normalizers, execution backends, and tests — so the CLI can actually dispatch predictions to any of the 4 tools through a single interface.

**Root directory**: `/Users/me/Development/dxkb/PredictStructureApp/`

### ESMFold CLI Decision

Phase 1 targets the modern **HuggingFace-based** `hf_fold.py` (`ESMFoldApp/esm_hf/scripts/hf_fold.py`), NOT the legacy `esm-fold` from `fair-esm`. Rationale:
- Simpler dependencies: `transformers` + `torch` (no OpenFold compile)
- Lighter Docker image (~8GB vs ~15GB)
- Active ecosystem, standard HuggingFace `pipeline` interface
- Better long-term maintenance

**Prerequisite**: `hf_fold.py` currently lacks `--num-recycles`. We must add it (small edit — `argparse` flag + `model.config.esmfold_config.trunk.num_recycles = args.num_recycles` after model load) before the adapter can map the unified `--num-recycles` parameter.

After prerequisite edit, the full `hf_fold.py` CLI:
```
python hf_fold.py -i <FASTA> -o <PDB_DIR> [--num-recycles N] [--cpu-only] [--fp16]
  [--chunk-size N] [--max-tokens-per-batch N] [--model-name NAME] [--low-cpu-mem]
```

---

## Files to Create/Modify (12 files, ~1100 LOC)

### Batch 1 — No internal dependencies (parallelize)

#### 1. `predict_structure/converters.py` (~130 LOC)

**Purpose**: Stateless format conversion functions that bridge the gap between the unified FASTA-based input and each tool's native format. Each tool expects slightly different input formats (Boltz needs YAML, Chai needs Parquet MSAs, etc.), and produces different output formats (mmCIF vs PDB). These functions handle all conversions so adapters can focus on parameter mapping.

---

**`fasta_to_boltz_yaml(fasta_path, output_path, msa_path=None) -> Path`**

Convert a standard FASTA file into a Boltz-2 YAML input manifest.

- **Why**: Boltz-2's native input is YAML (supports multi-entity complexes, ligands, constraints, MSA paths). When users provide standard FASTA through the unified CLI, this function generates the required YAML wrapper.
- **Inputs**:
  - `fasta_path: Path` — Input FASTA file with one or more protein sequences
  - `output_path: Path` — Where to write the generated YAML file
  - `msa_path: Path | None` — Optional A3M MSA file to embed in the YAML
- **Output**: Returns `output_path`. The YAML file contains:
  ```yaml
  version: 1
  sequences:
    - protein:
        id: A
        sequence: TTCCPSIVARSNFNVCRLPGTPEALCATYTGCIIIPGATCPGDYAN
        msa: /path/to/alignment.a3m   # only if msa_path provided
    - protein:
        id: B
        sequence: ...                  # second chain, if multi-seq FASTA
  ```
- **Logic**: Parse with `Bio.SeqIO.parse(fasta_path, "fasta")`. Chain IDs cycle A, B, C... per record. Guard `import yaml` with `RuntimeError("pip install predict-structure[boltz]")`.

---

**`a3m_to_parquet(a3m_path, output_path) -> Path`**

Convert an A3M multiple sequence alignment to Chai-1's Parquet format.

- **Why**: A3M is the lingua franca MSA format (output by MMseqs2, JackHMMER, used by Boltz and AlphaFold), but Chai-1 requires `.aligned.pqt` Parquet files. This lets users provide A3M and have it transparently converted.
- **Inputs**:
  - `a3m_path: Path` — Input A3M alignment file
  - `output_path: Path` — Where to write the `.aligned.pqt` Parquet file
- **Output**: Returns `output_path`. The Parquet file contains aligned sequences matching Chai's expected schema.
- **Logic**:
  - Primary: `subprocess.run(["chai", "a3m-to-pqt", str(a3m_path), str(output_path)])` — uses Chai's built-in converter
  - Fallback (if `chai` not on PATH): parse A3M manually (skip `#` lines, first sequence is query, rest are alignments), write with `pandas.DataFrame.to_parquet()` using pyarrow engine
  - Guard `import pyarrow` with `RuntimeError("pip install predict-structure[chai]")`

---

**`mmcif_to_pdb(cif_path, pdb_path) -> Path`**

Convert an mmCIF structure file to PDB format.

- **Why**: Boltz-2 and Chai-1 produce mmCIF output. Many downstream tools (PyMOL, stabiliNNator) and users prefer PDB. Called by normalizers to ensure both formats always exist.
- **Inputs**:
  - `cif_path: Path` — Input mmCIF file (.cif)
  - `pdb_path: Path` — Where to write the PDB file (.pdb)
- **Output**: Returns `pdb_path`. The PDB file contains the same structure with atom coordinates, B-factors, and chain IDs preserved.
- **Logic**: `Bio.PDB.MMCIFParser(QUIET=True).get_structure("s", cif_path)` → `PDBIO().set_structure(s)` → `PDBIO().save(pdb_path)`

---

**`pdb_to_mmcif(pdb_path, cif_path) -> Path`**

Convert a PDB structure file to mmCIF format.

- **Why**: AlphaFold2 and ESMFold produce PDB output. mmCIF is the modern archival format and handles large structures better. Called by normalizers to ensure both formats always exist.
- **Inputs**:
  - `pdb_path: Path` — Input PDB file (.pdb)
  - `cif_path: Path` — Where to write the mmCIF file (.cif)
- **Output**: Returns `cif_path`. The mmCIF file contains the same structure in CIF format.
- **Logic**: `Bio.PDB.PDBParser(QUIET=True).get_structure("s", pdb_path)` → `MMCIFIO().set_structure(s)` → `MMCIFIO().save(cif_path)`

---

#### 2. `predict_structure/backends/subprocess.py` (~35 LOC)

**Purpose**: Simplest execution backend — runs prediction tools as local subprocesses. Used when tools are installed directly on the machine (e.g., inside a container, or in a conda environment). This is the default backend for development and testing.

```python
class SubprocessBackend:
    """Run prediction commands as local subprocesses.

    Use when the prediction tool is installed locally (inside a container,
    conda env, or system-wide). Streams stdout/stderr to the terminal.
    """

    def run(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        **kwargs,  # absorbs tool_name, gpu, etc. from CLI
    ) -> int:
        """Execute a command as a local subprocess.

        Args:
            command: CLI command as list of strings (e.g. ["boltz", "predict", ...])
            cwd: Working directory for the subprocess
            env: Environment variables (merges with os.environ)
            timeout: Max seconds before killing the process

        Returns:
            Exit code (0 = success, non-zero = failure)
        """
```

---

#### 3. `predict_structure/backends/docker.py` (~70 LOC)

**Purpose**: Docker execution backend — wraps prediction commands inside `docker run` with GPU passthrough, volume mounts, and environment variables. Every tool has its own dedicated Docker image (delegation pattern — no monolithic image). This keeps images small, independently updatable, and avoids dependency conflicts between tools.

```python
# Each tool has its own dedicated container image.
# These are the BV-BRC runtime images (Layer 3) that include
# the tool + Python + CUDA + Perl runtime + AppService framework.
DEFAULT_IMAGES: dict[str, str] = {
    "boltz": "dxkb/boltz-bvbrc:latest-gpu",       # Boltz-2 + Python 3.11 + CUDA 12.1
    "chai": "dxkb/chai-bvbrc:latest-gpu",          # Chai-1 + Python 3.10 (uv) + CUDA 12.1
    "alphafold": "wilke/alphafold",                 # AF2 + databases + CUDA
    "esmfold": "dxkb/esmfold-bvbrc:latest-gpu",    # ESMFold HF + transformers + torch
}


class DockerBackend:
    """Run prediction commands inside per-tool Docker containers.

    Design: Each prediction tool runs in its own isolated Docker image.
    The backend resolves the correct image from DEFAULT_IMAGES using tool_name,
    then builds a `docker run` invocation with GPU passthrough and volume mounts.

    No shared container exists — when the user runs:
        predict-structure boltz input.fasta -o output/ --backend docker
    this dispatches to the dxkb/boltz-bvbrc image. When they run:
        predict-structure esmfold input.fasta -o output/ --backend docker
    it dispatches to dxkb/esmfold-bvbrc instead.

    The CLI's --image flag overrides the default for any tool.
    """

    def __init__(self, default_image: str | None = None):
        """Initialize with an optional override image (applies to any tool)."""

    def run(
        self,
        command: list[str],
        *,
        image: str | None = None,
        tool_name: str | None = None,
        volumes: dict[str, str] | None = None,
        gpu: bool = True,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> int:
        """Build and execute a docker run command.

        Image resolution order:
        1. `image` parameter (explicit override)
        2. `self._default_image` (from constructor / CLI --image flag)
        3. `DEFAULT_IMAGES[tool_name]` (per-tool default)

        Args:
            command: The tool command to run inside the container
            image: Docker image override (takes precedence over all defaults)
            tool_name: Tool name for looking up DEFAULT_IMAGES (e.g. "boltz")
            volumes: Host-to-container volume mounts {"/host/path": "/container/path"}
            gpu: Whether to pass --gpus all (True for boltz/chai/alphafold, False for esmfold on CPU)
            env: Environment variables to set in the container
            timeout: Max seconds for the container to run

        Returns:
            Exit code from docker run (0 = success)

        Produces shell command:
            docker run --rm [--gpus all] [-v h:c]... [-e K=V]... <image> <command>
        """
```

---

#### 4. `predict_structure/backends/__init__.py` (update, ~20 LOC)

**Purpose**: Backend registry and factory. Lets the CLI resolve a backend by name ("docker" or "subprocess") without importing concrete classes directly.

```python
from predict_structure.backends.docker import DockerBackend
from predict_structure.backends.subprocess import SubprocessBackend

BACKENDS: dict[str, type] = {
    "docker": DockerBackend,
    "subprocess": SubprocessBackend,
}


def get_backend(name: str, **kwargs) -> DockerBackend | SubprocessBackend:
    """Return a backend instance by name.

    Args:
        name: "docker" or "subprocess"
        **kwargs: Passed to backend constructor (e.g., default_image for Docker)

    Returns:
        Configured backend instance ready to call .run()

    Raises:
        ValueError: If name is not a recognized backend
    """
```

---

### Batch 2 — Depends on converters (parallelize these 5 files)

#### 5. `predict_structure/normalizers.py` (~200 LOC)

**Purpose**: Transforms the raw, tool-specific output directory into a standardized layout that downstream consumers can rely on. Each tool produces different file names, formats, and confidence metric layouts. The normalizers extract what matters (structure, confidence scores) and present it uniformly, while preserving the original output in `raw/` for debugging or advanced use.

All pLDDT values normalized to **0-100 scale** in `confidence.json` (ESMFold B-factors are 0-1, must multiply by 100).

---

**`write_confidence_json(output_dir, plddt_mean, ptm, per_residue_plddt) -> Path`**

Write a standardized confidence metrics file.

- **Why**: Provides a single, tool-agnostic JSON file with the key confidence metrics that users and downstream pipelines (e.g., stabiliNNator) need. Eliminates the need to know each tool's native score format.
- **Inputs**:
  - `output_dir: Path` — Target directory
  - `plddt_mean: float` — Average per-residue confidence (0-100 scale)
  - `ptm: float | None` — Predicted TM-score (None if tool doesn't produce it)
  - `per_residue_plddt: list[float]` — Per-residue pLDDT array (0-100 scale)
- **Output**: Returns path to `output_dir/confidence.json`. File contents:
  ```json
  {
    "plddt_mean": 87.3,
    "ptm": 0.92,
    "per_residue_plddt": [91.2, 88.5, 85.1, ...]
  }
  ```

---

**`write_metadata_json(output_dir, tool, params, runtime_seconds, version) -> Path`**

Write prediction provenance metadata.

- **Why**: Records which tool, what parameters, how long it took, what version. Essential for reproducibility, experiment tracking, and audit trails.
- **Inputs**:
  - `output_dir: Path` — Target directory
  - `tool: str` — Tool name ("boltz", "chai", "alphafold", "esmfold")
  - `params: dict` — The unified parameters used (num_samples, num_recycles, seed, etc.)
  - `runtime_seconds: float` — Wall-clock time for the prediction
  - `version: str` — predict-structure package version
- **Output**: Returns path to `output_dir/metadata.json`. File contents:
  ```json
  {
    "tool": "boltz",
    "params": {"num_samples": 5, "num_recycles": 3, "seed": null, "device": "gpu"},
    "runtime_seconds": 1823.4,
    "version": "0.1.0",
    "timestamp": "2026-03-11T14:30:00Z"
  }
  ```

---

**`normalize_boltz_output(raw_dir, output_dir) -> Path`**

Normalize Boltz-2's nested output into the standardized directory layout.

- **Why**: Boltz outputs mmCIF structures and confidence metrics in a deeply nested directory with tool-specific naming. This extracts the best model and confidence data into the unified layout.
- **Inputs**:
  - `raw_dir: Path` — Directory containing Boltz's raw output
  - `output_dir: Path` — Target directory for normalized output
- **Output**: Returns `output_dir`. Produces:
  ```
  output_dir/
  ├── model_1.pdb          # Converted from mmCIF via mmcif_to_pdb()
  ├── model_1.cif          # Copied from predictions/{name}/{name}_model_0.cif
  ├── confidence.json      # Extracted from confidence_{name}_model_0.json
  └── raw/                 # Full copy of raw_dir (shutil.copytree)
  ```
- **Raw input structure** (Boltz output):
  ```
  raw_dir/
  └── predictions/
      └── {input_name}/
          ├── {input_name}_model_0.cif          # Best model structure
          ├── confidence_{input_name}_model_0.json  # {"confidence_score": 0.87, "ptm": 0.92, "iptm": 0.89, "plddt": [0.91, 0.88, ...]}
          ├── plddt_{input_name}_model_0.npz     # Per-residue pLDDT array
          └── pae_{input_name}_model_0.npz       # PAE matrix (if --write_full_pae)
  ```
- **Confidence extraction**: Parse `confidence_*.json`. `plddt` array may be 0-1 (check max value; if all ≤ 1.0, scale × 100). `ptm` is already 0-1.

---

**`normalize_chai_output(raw_dir, output_dir) -> Path`**

Normalize Chai-1's indexed output into the standardized directory layout.

- **Why**: Chai outputs mmCIF and confidence scores in NPZ format with model-index-based naming. This extracts model 0 (best) and converts scores to the unified JSON format.
- **Inputs**:
  - `raw_dir: Path` — Directory containing Chai's raw output
  - `output_dir: Path` — Target directory for normalized output
- **Output**: Returns `output_dir`. Same normalized layout as above.
- **Raw input structure** (Chai output):
  ```
  raw_dir/
  ├── pred.model_idx_0.cif        # Best model structure (mmCIF)
  ├── scores.model_idx_0.npz      # numpy archive: {"plddt": array, "ptm": scalar}
  ├── pred.model_idx_1.cif        # Second model (if num_samples > 1)
  └── scores.model_idx_1.npz
  ```
- **Confidence extraction**: `np.load(scores_path)` → `data["plddt"]` (per-residue array, 0-1 scale → × 100), `data["ptm"]` (scalar, 0-1).

---

**`normalize_alphafold_output(raw_dir, output_dir) -> Path`**

Normalize AlphaFold2's ranked output into the standardized directory layout.

- **Why**: AF2 outputs up to 5 ranked PDB models with a JSON ranking file. This extracts the top-ranked model and its confidence scores.
- **Inputs**:
  - `raw_dir: Path` — Directory containing AF2's raw output
  - `output_dir: Path` — Target directory for normalized output
- **Output**: Returns `output_dir`. Same normalized layout as above.
- **Raw input structure** (AF2 output):
  ```
  raw_dir/
  └── {target_name}/
      ├── ranked_0.pdb              # Top-ranked model (already PDB)
      ├── ranked_1.pdb ... ranked_4.pdb
      ├── ranking_debug.json        # {"plddts": {"model_1": 87.3, ...}, "order": ["model_1", ...]}
      ├── result_model_1.pkl        # Full results (pickle, not parsed)
      ├── timings.json
      └── msas/                     # Generated MSAs
  ```
- **Confidence extraction**: Parse `ranking_debug.json`. `plddts` has per-model mean pLDDT (already 0-100 scale). For per-residue pLDDT: extract B-factors from CA atoms in `ranked_0.pdb` using `Bio.PDB.PDBParser` (AF2 stores pLDDT in B-factor column, 0-100 scale). `ptm`: not available in `ranking_debug.json` — set to `None`.

---

**`normalize_esmfold_output(raw_dir, output_dir) -> Path`**

Normalize ESMFold's PDB output into the standardized directory layout.

- **Why**: ESMFold outputs one PDB per sequence with pLDDT encoded in the B-factor column at 0-1 scale (non-standard). This scales to 0-100 and provides both formats.
- **Inputs**:
  - `raw_dir: Path` — Directory containing ESMFold's raw output
  - `output_dir: Path` — Target directory for normalized output
- **Output**: Returns `output_dir`. Same normalized layout as above.
- **Raw input structure** (ESMFold output from `hf_fold.py`):
  ```
  raw_dir/
  └── {sequence_header}.pdb    # One PDB per sequence; B-factors = pLDDT (0-1 range!)
  ```
- **Confidence extraction**: Parse PDB with `Bio.PDB.PDBParser`. Iterate CA atoms → collect B-factors. **Scale from 0-1 to 0-100**: `per_residue = [b * 100 for b in raw_bfactors]`. pTM: `hf_fold.py` logs pTM to stdout but doesn't write it to a file — set to `None` for now (future: parse stdout or add pTM file output to `hf_fold.py`).

---

#### 6. `predict_structure/adapters/boltz.py` (~90 LOC)

**Purpose**: Translates unified CLI parameters into Boltz-2's native `boltz predict` command. Handles Boltz's unique requirement for YAML input (converting FASTA when needed) and its mmCIF output format.

```python
class BoltzAdapter(BaseAdapter):
    """Adapter for Boltz-2 biomolecular structure prediction.

    Boltz-2 is a diffusion-based model for predicting structures of proteins,
    DNA, RNA, and ligand complexes. It uses YAML input format (auto-converted
    from FASTA) and outputs mmCIF structures with confidence metrics.
    """
    tool_name: str = "boltz"
    supports_msa: bool = True
    requires_gpu: bool = True
```

**`prepare_input(input_path, output_dir, *, msa_path=None, **kwargs) -> Path`**

Ensure input is in Boltz YAML format, converting from FASTA if needed.

- **Inputs**:
  - `input_path: Path` — User's input file (FASTA or YAML)
  - `output_dir: Path` — Working directory for prepared files
  - `msa_path: Path | None` — Optional A3M MSA file
- **Output**: Returns `Path` to the prepared YAML file (or the original if already YAML).
  - `.yaml/.yml` extension → return `input_path` unchanged
  - `.fasta/.fa` extension → call `fasta_to_boltz_yaml(input_path, output_dir / "input.yaml", msa_path)` → return new path
  - If MSA provided + YAML input → read YAML, inject `msa:` field per protein entry, write back

---

**`build_command(input_path, output_dir, *, num_samples=1, num_recycles=3, seed=None, device="gpu", **kwargs) -> list[str]`**

Construct the `boltz predict` CLI command.

- **Inputs**: Prepared input path + unified parameters
- **Output**: Returns command as `list[str]`, e.g.:
  ```python
  ["boltz", "predict", "/path/input.yaml",
   "--out_dir", "/path/output",
   "--diffusion_samples", "5",
   "--recycling_steps", "3",
   "--sampling_steps", "200",
   "--output_format", "mmcif",
   "--write_full_pae",
   "--accelerator", "gpu"]
  ```
- **Parameter mapping**:
  - `num_samples` → `--diffusion_samples`
  - `num_recycles` → `--recycling_steps`
  - `device == "cpu"` → `--accelerator cpu` (else `--accelerator gpu`)
  - `kwargs["use_msa_server"]` → `--use_msa_server`
  - `kwargs["sampling_steps"]` → `--sampling_steps` (default 200)
  - Pass-through: `kwargs["boltz_use_potentials"]` → `--use_potentials`, etc.

---

**`run(command, **kwargs) -> int`**

Execute prediction via the configured backend.

- **Inputs**: Command from `build_command` + backend in kwargs
- **Output**: Returns exit code (int). 0 = success.

---

**`normalize_output(raw_output_dir, output_dir) -> Path`**

Call `normalize_boltz_output()` to produce standardized layout.

- **Output**: Returns `output_dir` containing `model_1.pdb`, `model_1.cif`, `confidence.json`, `raw/`

---

**`preflight() -> dict`**

```python
{"cpu": 8, "memory": "96G", "runtime": 14400, "storage": "50G",
 "policy_data": {"gpu_count": 1, "partition": "gpu2", "constraint": "A100|H100|H200"}}
```

---

#### 7. `predict_structure/adapters/chai.py` (~80 LOC)

**Purpose**: Translates unified CLI parameters into Chai-1's native `chai-lab fold` command. Handles Chai's unique MSA requirement (Parquet format instead of A3M) by auto-converting when needed.

```python
class ChaiAdapter(BaseAdapter):
    """Adapter for Chai-1 protein structure prediction.

    Chai-1 is a diffusion-based model for protein structure prediction.
    Takes FASTA input directly. MSA must be in Parquet format (.aligned.pqt)
    — A3M files are auto-converted. Outputs mmCIF + NPZ confidence scores.
    """
    tool_name: str = "chai"
    supports_msa: bool = True
    requires_gpu: bool = True
```

**`prepare_input(input_path, output_dir, *, msa_path=None, **kwargs) -> Path`**

Pass FASTA through; convert A3M MSA to Parquet if provided.

- **Inputs**: Same signature as BaseAdapter
- **Output**: Returns `input_path` unchanged (FASTA pass-through). Side effect: if `msa_path` ends in `.a3m`, calls `a3m_to_parquet()` and stores result dir in `self._msa_dir` for use in `build_command`.

---

**`build_command(input_path, output_dir, *, num_samples=1, num_recycles=3, seed=None, device="gpu", **kwargs) -> list[str]`**

Construct the `chai-lab fold` CLI command.

- **Output**: Returns command as `list[str]`, e.g.:
  ```python
  ["chai-lab", "fold", "/path/input.fasta", "/path/output",
   "--num-diffn-samples", "5",
   "--num-trunk-recycles", "3",
   "--seed", "42",
   "--msa-directory", "/path/msa_dir"]
  ```
- **Parameter mapping**:
  - `num_samples` → `--num-diffn-samples`
  - `num_recycles` → `--num-trunk-recycles`
  - `seed` → `--seed` (if not None)
  - `self._msa_dir` → `--msa-directory` (if MSA was provided)
  - `kwargs["use_msa_server"]` → `--use-msa-server`
  - Pass-through: `kwargs["chai_constraint_path"]` → `--constraint-path`, etc. (underscore → hyphen)

---

**`normalize_output(raw_output_dir, output_dir) -> Path`** — Call `normalize_chai_output()`

**`preflight() -> dict`** — `{cpu: 8, memory: "64G", runtime: 10800, policy_data: {...}}`

---

#### 8. `predict_structure/adapters/alphafold.py` (~110 LOC)

**Purpose**: Translates unified CLI parameters into AlphaFold2's complex `run_alphafold.py` command. AlphaFold is unique in requiring a `data_dir` with ~2TB of reference databases — this adapter derives all database paths from that single directory, shielding users from AF2's many required flags.

```python
class AlphaFoldAdapter(BaseAdapter):
    """Adapter for AlphaFold 2 protein structure prediction.

    AlphaFold 2 uses co-evolutionary features from MSA databases for high-accuracy
    structure prediction. Requires a data_dir (~2TB) containing UniRef90, Mgnify,
    BFD/small_BFD, PDB70/PDB_seqres, and template databases. All database paths
    are derived from data_dir automatically.
    """
    tool_name: str = "alphafold"
    supports_msa: bool = True
    requires_gpu: bool = True
```

**`prepare_input(input_path, output_dir, *, msa_path=None, **kwargs) -> Path`**

FASTA pass-through. If precomputed MSA directory provided, flag for use in build_command.

- **Output**: Returns `input_path` unchanged. Side effect: sets `self._use_precomputed_msas = True` if `msa_path` is a directory.

---

**`build_command(input_path, output_dir, *, num_samples=1, num_recycles=3, seed=None, device="gpu", **kwargs) -> list[str]`**

Construct the `run_alphafold.py` command with all database paths.

- **Output**: Returns command as `list[str]`, e.g.:
  ```python
  ["python", "/app/alphafold/run_alphafold.py",
   "--fasta_paths", "/path/input.fasta",
   "--output_dir", "/path/output",
   "--data_dir", "/databases",
   "--uniref90_database_path", "/databases/uniref90/uniref90.fasta",
   "--mgnify_database_path", "/databases/mgnify/mgy_clusters_2022_05.fa",
   "--template_mmcif_dir", "/databases/pdb_mmcif/mmcif_files",
   "--obsolete_pdbs_path", "/databases/pdb_mmcif/obsolete.dat",
   "--small_bfd_database_path", "/databases/small_bfd/bfd-first_non_consensus_sequences.fasta",
   "--pdb70_database_path", "/databases/pdb70/pdb70",
   "--model_preset", "monomer",
   "--db_preset", "reduced_dbs",
   "--max_template_date", "2022-01-01",
   "--use_gpu_relax=true",
   "--random_seed", "42"]
  ```
- **Parameter mapping**:
  - `kwargs["af2_data_dir"]` → `--data_dir` + all derived DB paths (**required**, raises `ValueError` if missing)
  - `kwargs["af2_model_preset"]` → `--model_preset` (default "monomer")
  - `kwargs["af2_db_preset"]` → `--db_preset` (default "reduced_dbs")
  - `seed` → `--random_seed` (if not None)
  - `device != "cpu"` → `--use_gpu_relax=true`
  - `self._use_precomputed_msas` → `--use_precomputed_msas=true`
- **Database path derivation** (from [App-AlphaFold.pl:386-408](../AlphaFoldApp/service-scripts/App-AlphaFold.pl#L386-L408)):
  - Always: `uniref90/uniref90.fasta`, `mgnify/mgy_clusters_2022_05.fa`, `pdb_mmcif/mmcif_files`, `pdb_mmcif/obsolete.dat`
  - `reduced_dbs`: `small_bfd/bfd-first_non_consensus_sequences.fasta`
  - `full_dbs`: `bfd/bfd_metaclust_clu_complete_id30_c90_final_seq.sorted_opt`, `uniref30/UniRef30_2021_03`
  - `monomer*`: `pdb70/pdb70`
  - `multimer`: `pdb_seqres/pdb_seqres.txt`, `uniprot/uniprot.fasta`

---

**`normalize_output(raw_output_dir, output_dir) -> Path`** — Call `normalize_alphafold_output()`

**`preflight() -> dict`** — `{cpu: 8, memory: "64G", runtime: 28800, storage: "100G", policy_data: {...}}`

---

#### 9. `predict_structure/adapters/esmfold.py` (~60 LOC)

**Purpose**: Translates unified CLI parameters into the HuggingFace-based `hf_fold.py` command. ESMFold is the simplest adapter — it's single-sequence (no MSA), deterministic (no sampling), and can run on CPU. It's the fastest tool, ideal for quick predictions or when GPU isn't available.

```python
class ESMFoldAdapter(BaseAdapter):
    """Adapter for ESMFold protein structure prediction (HuggingFace).

    ESMFold is a single-sequence model — no MSA required. Deterministic
    output (no sampling). Can run on CPU. Uses the modern HuggingFace
    transformers implementation (not legacy fair-esm/OpenFold).
    """
    tool_name: str = "esmfold"
    supports_msa: bool = False
    requires_gpu: bool = False  # Can run on CPU (no GPU policy in preflight)
```

**`prepare_input(input_path, output_dir, *, msa_path=None, **kwargs) -> Path`**

FASTA pass-through. Warn if MSA provided (ESMFold can't use it).

- **Output**: Returns `input_path` unchanged. Logs `logger.warning("ESMFold does not use MSA input; ignoring --msa")` if `msa_path` is not None.

---

**`build_command(input_path, output_dir, *, num_samples=1, num_recycles=3, seed=None, device="gpu", **kwargs) -> list[str]`**

Construct the `hf_fold.py` CLI command.

- **Output**: Returns command as `list[str]`, e.g.:
  ```python
  ["esm-fold-hf", "-i", "/path/input.fasta",
   "-o", "/path/output",
   "--num-recycles", "4"]
  ```
- **Parameter mapping**:
  - `num_recycles` → `--num-recycles` (default 4 for ESMFold)
  - `num_samples` → **ignored** (ESMFold is deterministic; log info if > 1)
  - `seed` → **ignored** (deterministic)
  - `device == "cpu"` → `--cpu-only`
  - Pass-through: `kwargs["esm_fp16"]` → `--fp16`, `kwargs["esm_chunk_size"]` → `--chunk-size`, `kwargs["esm_max_tokens"]` → `--max-tokens-per-batch`

---

**`normalize_output(raw_output_dir, output_dir) -> Path`** — Call `normalize_esmfold_output()`

**`preflight() -> dict`** — `{cpu: 8, memory: "32G", runtime: 3600}` (no GPU policy)

---

### Batch 3 — Wire everything together

#### 10. `predict_structure/adapters/__init__.py` (update, ~25 LOC)

**Purpose**: Adapter registry and factory. Lets the CLI resolve an adapter by tool name without importing concrete classes directly. Central dispatch point for tool selection.

```python
from predict_structure.adapters.base import BaseAdapter
from predict_structure.adapters.boltz import BoltzAdapter
from predict_structure.adapters.chai import ChaiAdapter
from predict_structure.adapters.alphafold import AlphaFoldAdapter
from predict_structure.adapters.esmfold import ESMFoldAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "boltz": BoltzAdapter,
    "chai": ChaiAdapter,
    "alphafold": AlphaFoldAdapter,
    "esmfold": ESMFoldAdapter,
}


def get_adapter(tool_name: str) -> BaseAdapter:
    """Return an adapter instance for the given tool name.

    Args:
        tool_name: One of "boltz", "chai", "alphafold", "esmfold"

    Returns:
        Configured adapter instance ready for prepare_input → build_command → run → normalize_output

    Raises:
        ValueError: If tool_name is not recognized
    """
```

---

#### 11. `predict_structure/cli.py` (replace stub, ~90 LOC)

**Purpose**: The user-facing entry point. Wires together adapter + backend to execute the full prediction lifecycle: prepare input → build command → execute → normalize output → write metadata. Replaces the current stub that just prints "not yet implemented".

**Add options** to existing click decorator:
- `--backend` (`docker` | `subprocess`, default `subprocess`)
- `--image` (override Docker image)
- `--af2-data-dir` (AlphaFold database directory)
- `--af2-model-preset` (default `monomer`)
- `--af2-db-preset` (default `reduced_dbs`)
- `--sampling-steps` (default 200, Boltz/Chai only)
- `--use-msa-server` (flag, Boltz/Chai)

**Full `main()` interface**:
```python
@click.command()
@click.argument("tool", type=click.Choice(TOOLS, case_sensitive=False))
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-o", "--output-dir", type=click.Path(), required=True)
@click.option("--num-samples", "-n", type=int, default=1)
@click.option("--num-recycles", type=int, default=3)
@click.option("--seed", type=int, default=None)
@click.option("--device", type=click.Choice(["gpu", "cpu"]), default="gpu")
@click.option("--msa", type=click.Path(), default=None)
@click.option("--output-format", type=click.Choice(["pdb", "mmcif"]), default="pdb")
@click.option("--backend", type=click.Choice(["docker", "subprocess"]), default="subprocess")
@click.option("--image", default=None, help="Override Docker image")
@click.option("--sampling-steps", type=int, default=200)
@click.option("--use-msa-server", is_flag=True, default=False)
@click.option("--af2-data-dir", type=click.Path(), default=None)
@click.option("--af2-model-preset", default="monomer")
@click.option("--af2-db-preset", default="reduced_dbs")
def main(tool, input_file, output_dir, ...):
    """Predict protein structure using TOOL on INPUT_FILE.

    Dispatches to the appropriate prediction tool (Boltz-2, Chai-1,
    AlphaFold 2, or ESMFold) with automatic parameter mapping,
    input format conversion, and output normalization.
    """
```

**Body** — the 5-step prediction lifecycle:
```python
# 1. Resolve adapter and backend by name
adapter = get_adapter(tool)
backend = get_backend(backend_name, default_image=image)

# 2. Prepare input (FASTA → tool-native format, MSA conversion)
prepared = adapter.prepare_input(Path(input_file), output_dir, msa_path=msa)

# 3. Build tool-specific command from unified parameters
cmd = adapter.build_command(prepared, raw_dir, num_samples=..., num_recycles=..., ...)

# 4. Execute prediction
start = time.time()
rc = backend.run(cmd, tool_name=adapter.tool_name,
                 gpu=adapter.requires_gpu and device != "cpu")
elapsed = time.time() - start
if rc != 0: sys.exit(rc)

# 5. Normalize output (structure format conversion, confidence extraction)
adapter.normalize_output(raw_dir, output_dir)
write_metadata_json(output_dir, tool, params_dict, elapsed, __version__)
click.echo(f"Prediction complete: {output_dir}")
```

---

### Batch 4 — Tests

#### 12. `tests/` (~350 LOC across 5 files)

**Purpose**: Verify converters, adapters, normalizers, and CLI work correctly without requiring GPU or actual tool installations. Tests use mock subprocess calls and fixture directories mimicking real tool output.

| File | Purpose | Tests |
|------|---------|-------|
| `tests/conftest.py` | Shared fixtures for all tests | `sample_fasta` (→ `test_data/simple_protein.fasta`), `tmp_output` |
| `tests/test_converters.py` | Verify format conversion correctness | `fasta_to_boltz_yaml` single/multi-chain + MSA injection, `mmcif_to_pdb` + `pdb_to_mmcif` round-trip, `a3m_to_parquet` fallback |
| `tests/test_adapters.py` | Verify parameter mapping produces correct CLI commands | `build_command` output for each adapter (verify exact flags), `prepare_input` for Boltz FASTA→YAML, ESMFold MSA warning, AlphaFold missing data_dir ValueError |
| `tests/test_normalizers.py` | Verify output normalization and confidence extraction | `write_confidence_json` schema, `write_metadata_json` schema, ESMFold B-factor scaling (0-1 → 0-100) |
| `tests/test_cli.py` | Verify CLI argument parsing and error handling | `CliRunner` — help text, unknown tool error, missing `--output-dir` error |

---

## `pyproject.toml` Update

Add `numpy>=1.23` to core `dependencies` list (for NPZ parsing in normalizers).

---

## Prerequisite Edit (outside PredictStructureApp)

**File**: `/Users/me/Development/dxkb/ESMFoldApp/esm_hf/scripts/hf_fold.py`

Add `--num-recycles` argparse parameter so the unified CLI can control recycling iterations:

1. Add to `create_parser()` (after the `--chunk-size` argument, ~line 162):
   ```python
   parser.add_argument(
       "--num-recycles",
       type=int,
       default=4,
       help="Number of recycles to run. Defaults to number used in training (4).",
   )
   ```

2. In `run()` function, after model load and before `model.eval()` (~line 234):
   ```python
   if args.num_recycles is not None:
       model.config.esmfold_config.trunk.num_recycles = args.num_recycles
   ```

This is a small, backward-compatible change (default=4 matches the training default).

---

## Execution Order

```
Step 0 (first):                  Save this plan as docs/Phase1.md in PredictStructureApp
Prereq (do first):               hf_fold.py --num-recycles flag
Batch 1 (parallel, no deps):     converters.py, backends/subprocess.py, backends/docker.py, backends/__init__.py
Batch 2 (parallel, deps on B1):  normalizers.py, boltz.py, chai.py, alphafold.py, esmfold.py
Batch 3 (sequential):            adapters/__init__.py → cli.py
Batch 4 (after all):             tests/
```

---

## Verification

1. **Unit tests**: `cd /Users/me/Development/dxkb/PredictStructureApp && pip install -e ".[dev,boltz,chai]" && pytest tests/ -v`
2. **CLI smoke test**: `predict-structure --help` (verify all options listed)
3. **Converter test**: `predict-structure boltz test_data/simple_protein.fasta -o /tmp/test --backend subprocess` (will fail at execution since no boltz binary, but should confirm input preparation and command construction work)
4. **Type checking**: `mypy predict_structure/`
5. **Lint**: `ruff check predict_structure/`
