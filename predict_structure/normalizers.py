"""Output normalization for structure prediction tools.

Transforms raw, tool-specific output directories into a standardized layout:
    output_dir/
    ├── model_1.pdb
    ├── model_1.cif
    ├── confidence.json   # {plddt_mean, ptm, per_residue_plddt[]}
    ├── metadata.json     # {tool, params, runtime, version}
    └── raw/              # Original tool output (unmodified)

All pLDDT values are normalized to 0-100 scale.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from Bio.PDB import PDBParser

from predict_structure.converters import mmcif_to_pdb, pdb_to_mmcif

logger = logging.getLogger(__name__)


def write_confidence_json(
    output_dir: Path,
    plddt_mean: float,
    ptm: float | None,
    per_residue_plddt: list[float],
) -> Path:
    """Write standardized confidence metrics.

    Args:
        output_dir: Target directory.
        plddt_mean: Average per-residue confidence (0-100 scale).
        ptm: Predicted TM-score (None if unavailable).
        per_residue_plddt: Per-residue pLDDT array (0-100 scale).

    Returns:
        Path to confidence.json.
    """
    path = output_dir / "confidence.json"
    data = {
        "plddt_mean": round(plddt_mean, 2),
        "ptm": round(ptm, 4) if ptm is not None else None,
        "per_residue_plddt": [round(v, 2) for v in per_residue_plddt],
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def write_metadata_json(
    output_dir: Path,
    tool: str,
    params: dict,
    runtime_seconds: float,
    version: str,
) -> Path:
    """Write prediction provenance metadata.

    Args:
        output_dir: Target directory.
        tool: Tool name.
        params: Unified parameters used.
        runtime_seconds: Wall-clock time for the prediction.
        version: predict-structure package version.

    Returns:
        Path to metadata.json.
    """
    path = output_dir / "metadata.json"
    data = {
        "tool": tool,
        "params": params,
        "runtime_seconds": round(runtime_seconds, 1),
        "version": version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def _extract_ca_bfactors(pdb_path: Path) -> list[float]:
    """Extract B-factors from CA atoms in a PDB file."""
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("s", str(pdb_path))
    bfactors = []
    for model in structure:
        for chain in model:
            for residue in chain:
                if "CA" in residue:
                    bfactors.append(residue["CA"].get_bfactor())
        break  # first model only
    return bfactors


def _copy_raw(raw_dir: Path, output_dir: Path) -> None:
    """Copy raw output to output_dir/raw/."""
    dest = output_dir / "raw"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(str(raw_dir), str(dest))


def normalize_boltz_output(raw_dir: Path, output_dir: Path) -> Path:
    """Normalize Boltz-2 output to standardized layout.

    Raw structure:
        raw_dir/predictions/{name}/{name}_model_0.cif
        raw_dir/predictions/{name}/confidence_{name}_model_0.json
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find the predictions subdirectory
    pred_dir = raw_dir / "predictions"
    if not pred_dir.exists():
        raise FileNotFoundError(f"No predictions/ directory in {raw_dir}")

    # Get first (usually only) prediction subdirectory
    subdirs = [d for d in pred_dir.iterdir() if d.is_dir()]
    if not subdirs:
        raise FileNotFoundError(f"No prediction subdirectories in {pred_dir}")
    pred_subdir = subdirs[0]
    name = pred_subdir.name

    # Copy CIF → model_1.cif
    cif_files = list(pred_subdir.glob(f"{name}_model_0.cif"))
    if not cif_files:
        cif_files = list(pred_subdir.glob("*.cif"))
    if not cif_files:
        raise FileNotFoundError(f"No CIF files in {pred_subdir}")
    cif_src = cif_files[0]
    cif_dst = output_dir / "model_1.cif"
    shutil.copy2(str(cif_src), str(cif_dst))

    # Convert CIF → PDB
    mmcif_to_pdb(cif_dst, output_dir / "model_1.pdb")

    # Extract confidence
    conf_files = list(pred_subdir.glob(f"confidence_{name}_model_0.json"))
    if not conf_files:
        conf_files = list(pred_subdir.glob("confidence_*.json"))

    if conf_files:
        conf_data = json.loads(conf_files[0].read_text())
        plddt_array = conf_data.get("plddt", [])
        # Scale 0-1 → 0-100 if needed
        if plddt_array and max(plddt_array) <= 1.0:
            plddt_array = [v * 100 for v in plddt_array]
        plddt_mean = sum(plddt_array) / len(plddt_array) if plddt_array else 0.0
        ptm = conf_data.get("ptm")
        write_confidence_json(output_dir, plddt_mean, ptm, plddt_array)
    else:
        logger.warning("No confidence JSON found in %s", pred_subdir)

    _copy_raw(raw_dir, output_dir)
    return output_dir


def normalize_chai_output(raw_dir: Path, output_dir: Path) -> Path:
    """Normalize Chai-1 output to standardized layout.

    Raw structure:
        raw_dir/pred.model_idx_0.cif
        raw_dir/scores.model_idx_0.npz
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find best model CIF
    cif_files = sorted(raw_dir.glob("pred.model_idx_*.cif"))
    if not cif_files:
        raise FileNotFoundError(f"No pred.model_idx_*.cif files in {raw_dir}")
    cif_src = cif_files[0]  # model_idx_0 = best
    cif_dst = output_dir / "model_1.cif"
    shutil.copy2(str(cif_src), str(cif_dst))

    # Convert CIF → PDB
    mmcif_to_pdb(cif_dst, output_dir / "model_1.pdb")

    # Extract confidence from NPZ
    score_files = sorted(raw_dir.glob("scores.model_idx_*.npz"))
    if score_files:
        data = np.load(str(score_files[0]))
        plddt_array = data["plddt"].flatten().tolist()
        # Scale 0-1 → 0-100 if needed
        if plddt_array and max(plddt_array) <= 1.0:
            plddt_array = [v * 100 for v in plddt_array]
        plddt_mean = sum(plddt_array) / len(plddt_array) if plddt_array else 0.0
        ptm = float(data["ptm"]) if "ptm" in data else None
        write_confidence_json(output_dir, plddt_mean, ptm, plddt_array)
    else:
        logger.warning("No scores NPZ found in %s", raw_dir)

    _copy_raw(raw_dir, output_dir)
    return output_dir


def normalize_alphafold_output(raw_dir: Path, output_dir: Path) -> Path:
    """Normalize AlphaFold2 output to standardized layout.

    Raw structure:
        raw_dir/{target}/ranked_0.pdb
        raw_dir/{target}/ranking_debug.json
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # AF2 nests under a target subdirectory
    ranked_pdb = None
    ranking_json = None

    # Check for direct files first, then subdirectories
    if (raw_dir / "ranked_0.pdb").exists():
        ranked_pdb = raw_dir / "ranked_0.pdb"
        ranking_json = raw_dir / "ranking_debug.json"
    else:
        for subdir in raw_dir.iterdir():
            if subdir.is_dir() and (subdir / "ranked_0.pdb").exists():
                ranked_pdb = subdir / "ranked_0.pdb"
                ranking_json = subdir / "ranking_debug.json"
                break

    if ranked_pdb is None:
        raise FileNotFoundError(f"No ranked_0.pdb found in {raw_dir}")

    # Copy PDB → model_1.pdb
    pdb_dst = output_dir / "model_1.pdb"
    shutil.copy2(str(ranked_pdb), str(pdb_dst))

    # Convert PDB → CIF
    pdb_to_mmcif(pdb_dst, output_dir / "model_1.cif")

    # Extract confidence
    # Per-residue pLDDT from CA B-factors (AF2 stores pLDDT in B-factor, 0-100)
    per_residue = _extract_ca_bfactors(pdb_dst)
    plddt_mean = sum(per_residue) / len(per_residue) if per_residue else 0.0

    # Try ranking_debug.json for mean pLDDT (more accurate)
    ptm = None
    if ranking_json and ranking_json.exists():
        rdata = json.loads(ranking_json.read_text())
        plddts = rdata.get("plddts", {})
        if plddts:
            # Use the mean from ranking_debug if available
            order = rdata.get("order", [])
            if order:
                top_model = order[0]
                plddt_mean = plddts.get(top_model, plddt_mean)

    write_confidence_json(output_dir, plddt_mean, ptm, per_residue)
    _copy_raw(raw_dir, output_dir)
    return output_dir


def normalize_esmfold_output(raw_dir: Path, output_dir: Path) -> Path:
    """Normalize ESMFold output to standardized layout.

    Raw structure:
        raw_dir/{header}.pdb  (B-factors = pLDDT at 0-1 scale!)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find the first PDB file
    pdb_files = sorted(raw_dir.glob("*.pdb"))
    if not pdb_files:
        raise FileNotFoundError(f"No PDB files found in {raw_dir}")
    pdb_src = pdb_files[0]

    # Copy PDB → model_1.pdb
    pdb_dst = output_dir / "model_1.pdb"
    shutil.copy2(str(pdb_src), str(pdb_dst))

    # Convert PDB → CIF
    pdb_to_mmcif(pdb_dst, output_dir / "model_1.cif")

    # Extract confidence — ESMFold B-factors are 0-1, scale to 0-100
    raw_bfactors = _extract_ca_bfactors(pdb_dst)
    if raw_bfactors and max(raw_bfactors) <= 1.0:
        per_residue = [b * 100 for b in raw_bfactors]
    else:
        per_residue = raw_bfactors
    plddt_mean = sum(per_residue) / len(per_residue) if per_residue else 0.0

    # pTM not available in PDB output (logged to stdout by hf_fold.py)
    write_confidence_json(output_dir, plddt_mean, None, per_residue)
    _copy_raw(raw_dir, output_dir)
    return output_dir
