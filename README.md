# PredictStructureApp

Unified protein structure prediction for BV-BRC. Wraps **Boltz-2**, **Chai-1**, **AlphaFold 2**, and **ESMFold** behind a single CLI, CWL tool, and BV-BRC AppService interface with automatic parameter mapping, format conversion, and output normalization.

## Installation

### Prerequisites

- Python 3.10+
- [conda](https://docs.conda.io/en/latest/) or [miniconda](https://docs.anaconda.com/miniconda/)

### Quick start

```bash
# Create and activate environment
conda create -n predict-structure python=3.12 -y
conda activate predict-structure

# Install with all optional dependencies
pip install -e ".[all]"

# Verify
predict-structure --version
predict-structure --help
```

### Minimal install (core only)

```bash
pip install -e .
```

### Optional dependency groups

| Group | What it adds | Install |
|-------|-------------|---------|
| `boltz` | PyYAML (FASTA→YAML conversion) | `pip install -e ".[boltz]"` |
| `chai` | PyArrow (A3M→Parquet MSA conversion) | `pip install -e ".[chai]"` |
| `esmfold` | PyTorch, Transformers, Accelerate | `pip install -e ".[esmfold]"` |
| `cwl` | cwltool, PyYAML | `pip install -e ".[cwl]"` |
| `dev` | pytest, black, ruff, mypy | `pip install -e ".[dev]"` |
| `all` | Everything above | `pip install -e ".[all]"` |

> **Note:** The prediction tools themselves (boltz, chai-lab, etc.) must be installed separately or run inside their respective Docker containers.

## Usage

### CLI

Each prediction tool is a subcommand with its own options:

```bash
# Auto-discover best available tool
predict-structure auto input.fasta -o output/

# Boltz-2 (diffusion-based, proteins/DNA/RNA/ligands)
predict-structure boltz input.fasta -o output/ --num-samples 5 --use-potentials

# Chai-1 (diffusion-based protein prediction)
predict-structure chai input.fasta -o output/ --use-msa-server

# AlphaFold 2 (MSA-based, high accuracy)
predict-structure alphafold input.fasta -o output/ --af2-data-dir /databases

# ESMFold (single-sequence, no MSA, CPU-capable)
predict-structure esmfold input.fasta -o output/ --fp16

# Debug mode — print the command without executing
predict-structure boltz input.fasta -o output/ --debug

# Per-tool help
predict-structure boltz --help
predict-structure auto --help
```

### Auto-discovery

The `auto` subcommand detects which tools are installed and picks the best one:

| Condition | Selection |
|-----------|-----------|
| `.yaml`/`.yml` input | Boltz (only tool supporting YAML) |
| `--device cpu` | ESMFold (others impractical on CPU) |
| GPU available | Boltz > Chai > AlphaFold > ESMFold (accuracy priority) |

AlphaFold is only auto-selected when both the executable and the database directory (`/databases`) are found.

### Custom MSA server

Boltz and Chai support a custom ColabFold MMseqs2 server URL:

```bash
predict-structure boltz input.fasta -o output/ \
  --msa-server-url https://my-mmseqs-server.com

# --msa-server-url implies --use-msa-server
```

### CWL

```bash
# Validate
cwltool --validate cwl/tools/predict-structure.cwl

# Run
cwltool cwl/tools/predict-structure.cwl cwl/jobs/crambin-esmfold.yml
```

### Docker

```bash
# Build BV-BRC integration layer
cd container
docker build -t dxkb/predict-structure-bvbrc:latest-gpu \
  -f Dockerfile.PredictStructure-bvbrc .

# Run as BV-BRC service
docker run --gpus all -v $(pwd)/test_data:/data \
  dxkb/predict-structure-bvbrc:latest-gpu \
  App-PredictStructure /data/params.json

# Convert to Apptainer/Singularity for HPC
singularity build predict-structure-bvbrc.sif \
  docker://dxkb/predict-structure-bvbrc:latest-gpu
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  CLI  (predict-structure <tool> <input> [OPTIONS])      │
│  click.group() with per-tool subcommands                │
├─────────────────────────────────────────────────────────┤
│  Adapter Layer                                          │
│  Boltz │ Chai │ AlphaFold │ ESMFold                     │
│  Input conversion · Param mapping · Output normalization│
├─────────────────────────────────────────────────────────┤
│  Execution Backends                                     │
│  subprocess │ docker │ cwl                              │
├─────────────────────────────────────────────────────────┤
│  Per-Tool Containers (delegation, not bundled)          │
│  dxkb/boltz │ dxkb/chai │ wilke/alphafold │ dxkb/esmfold│
└─────────────────────────────────────────────────────────┘
```

PredictStructureApp does **not** bundle all tools into a single image. The CLI and BV-BRC service script dispatch to the appropriate per-tool container. This keeps images small and independently updatable.

### Project layout

```
PredictStructureApp/
├── predict_structure/          # Python package
│   ├── cli.py                  # CLI entry point (click group + subcommands)
│   ├── adapters/               # Per-tool adapters (build_command, normalize_output)
│   │   ├── base.py             # Abstract BaseAdapter
│   │   ├── boltz.py            # Boltz-2 (FASTA→YAML, mmCIF→PDB)
│   │   ├── chai.py             # Chai-1 (A3M→Parquet MSA)
│   │   ├── alphafold.py        # AlphaFold 2 (database path wiring)
│   │   └── esmfold.py          # ESMFold (HuggingFace transformers)
│   ├── converters.py           # Format conversions (FASTA→YAML, A3M→Parquet, mmCIF↔PDB)
│   ├── normalizers.py          # Unified output layout + confidence.json
│   └── backends/               # Execution backends
│       ├── subprocess.py       # Direct subprocess execution
│       ├── docker.py           # Docker with volume mounts
│       └── cwl.py              # CWL via cwltool/toil
├── app_specs/                  # BV-BRC service parameter definitions
│   └── PredictStructure.json
├── cwl/                        # CWL tool and workflow definitions
│   ├── tools/predict-structure.cwl
│   └── jobs/                   # Example job YAMLs
├── service-scripts/            # BV-BRC AppService entry point (Perl)
├── container/                  # Dockerfiles for BV-BRC integration layer
├── tests/                      # pytest test suite
├── test_data/                  # Sample inputs for testing
└── pyproject.toml              # Package metadata and dependencies
```

## Testing

```bash
conda activate predict-structure

# Full test suite
pytest

# Verbose with coverage
pytest -v --cov=predict_structure

# Specific test classes
pytest tests/test_cli.py -v                     # CLI argument parsing
pytest tests/test_adapters.py -v                # Adapter logic
pytest tests/test_cwl_tool.py -v                # CWL validation
pytest tests/test_cwl_backend.py -v             # CWL backend

# CWL validation only
cwltool --validate cwl/tools/predict-structure.cwl
```

### BV-BRC Makefile tests

```bash
make test-client     # t/client-tests/*.t
make test-server     # t/server-tests/*.t
make test-prod       # t/prod-tests/*.t
```

## Output format

Every prediction produces a standardized output directory:

```
output/
├── model_1.pdb          # Structure (PDB)
├── model_1.cif          # Structure (mmCIF)
├── confidence.json      # {plddt_mean, ptm, per_residue_plddt[]}
├── metadata.json        # {tool, params, runtime, version}
└── raw_output/          # Original tool output (unmodified)
```

## Defaults

| Parameter | Default | Notes |
|-----------|---------|-------|
| `tool` | `auto` | Auto-discovers best available tool |
| `num_samples` | 1 | |
| `num_recycles` | 3 | |
| `output_format` | `pdb` | |
| `device` | `gpu` | |
| `backend` | `subprocess` | |
| `sampling_steps` | 200 | Boltz, Chai only |
| `af2_model_preset` | `monomer` | AlphaFold only |
| `af2_db_preset` | `reduced_dbs` | AlphaFold only |
| `af2_max_template_date` | `2022-01-01` | AlphaFold only; prevents template data leakage |
| `af2_data_dir` | `/databases` | AlphaFold only; container default |

## Resource requirements

| Tool | CPU | Memory | GPU | Typical runtime |
|------|-----|--------|-----|-----------------|
| Boltz-2 | 8 | 64-96 GB | A100/H100/H200 | 2-4 h |
| Chai-1 | 8 | 64 GB | A100/H100/H200 | 2-3 h |
| AlphaFold 2 | 8 | 64 GB | A100/H100/H200 | 2-8 h |
| ESMFold | 8 | 32 GB | Optional (CPU OK) | 5-15 min |

GPU constraint in SLURM: `A100|H100|H200` on `gpu2` partition.

## License

MIT
