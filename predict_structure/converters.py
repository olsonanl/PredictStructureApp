"""Format conversion functions for structure prediction I/O.

Stateless converters that bridge universal FASTA/A3M input to tool-native
formats (Boltz YAML, Chai Parquet) and convert between structure file
formats (mmCIF ↔ PDB).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from Bio import SeqIO
from Bio.PDB import MMCIFParser, MMCIFIO, PDBParser, PDBIO

logger = logging.getLogger(__name__)

_CHAIN_IDS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def fasta_to_boltz_yaml(
    fasta_path: Path,
    output_path: Path,
    msa_path: Path | None = None,
) -> Path:
    """Convert a FASTA file to a Boltz-2 YAML input manifest.

    Boltz-2 requires YAML input for full feature support (multi-entity
    complexes, ligands, constraints, MSA paths). This wraps a standard
    FASTA into the required YAML format.

    Args:
        fasta_path: Input FASTA file with one or more protein sequences.
        output_path: Where to write the generated YAML file.
        msa_path: Optional A3M MSA file to reference in the YAML.

    Returns:
        Path to the written YAML file.
    """
    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            "PyYAML is required for Boltz YAML conversion. "
            "Install with: pip install predict-structure[boltz]"
        )

    records = list(SeqIO.parse(str(fasta_path), "fasta"))
    if not records:
        raise ValueError(f"No sequences found in {fasta_path}")

    sequences = []
    for i, record in enumerate(records):
        chain_id = _CHAIN_IDS[i % len(_CHAIN_IDS)]
        entry: dict = {
            "id": chain_id,
            "sequence": str(record.seq),
        }
        if msa_path is not None:
            entry["msa"] = str(msa_path.resolve())
        sequences.append({"protein": entry})

    manifest = {"version": 1, "sequences": sequences}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    logger.info("Wrote Boltz YAML with %d chain(s) to %s", len(records), output_path)
    return output_path


def a3m_to_parquet(a3m_path: Path, output_path: Path) -> Path:
    """Convert an A3M multiple sequence alignment to Chai-1's Parquet format.

    Tries Chai's built-in converter first; falls back to manual parsing
    with pandas + pyarrow.

    Args:
        a3m_path: Input A3M alignment file.
        output_path: Where to write the .aligned.pqt Parquet file.

    Returns:
        Path to the written Parquet file.
    """
    # Try Chai's built-in converter
    if shutil.which("chai"):
        result = subprocess.run(
            ["chai", "a3m-to-pqt", str(a3m_path), str(output_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("Converted A3M to Parquet via chai CLI: %s", output_path)
            return output_path
        logger.warning("chai a3m-to-pqt failed: %s; falling back to manual parsing", result.stderr)

    # Manual fallback
    try:
        import pandas as pd
        import pyarrow  # noqa: F401 — ensure engine is available
    except ImportError:
        raise RuntimeError(
            "pyarrow is required for A3M→Parquet conversion. "
            "Install with: pip install predict-structure[chai]"
        )

    sequences = []
    with open(a3m_path) as f:
        current_seq: list[str] = []
        for line in f:
            line = line.strip()
            if line.startswith("#"):
                continue
            if line.startswith(">"):
                if current_seq:
                    sequences.append("".join(current_seq))
                current_seq = []
            elif line:
                current_seq.append(line)
        if current_seq:
            sequences.append("".join(current_seq))

    if not sequences:
        raise ValueError(f"No sequences found in {a3m_path}")

    df = pd.DataFrame({"sequence": sequences})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(output_path), engine="pyarrow")
    logger.info("Converted A3M (%d seqs) to Parquet: %s", len(sequences), output_path)
    return output_path


def mmcif_to_pdb(cif_path: Path, pdb_path: Path) -> Path:
    """Convert an mmCIF structure file to PDB format.

    Args:
        cif_path: Input mmCIF file.
        pdb_path: Where to write the PDB file.

    Returns:
        Path to the written PDB file.
    """
    parser = MMCIFParser(QUIET=True)
    structure = parser.get_structure("s", str(cif_path))
    io = PDBIO()
    io.set_structure(structure)
    pdb_path.parent.mkdir(parents=True, exist_ok=True)
    io.save(str(pdb_path))
    return pdb_path


def pdb_to_mmcif(pdb_path: Path, cif_path: Path) -> Path:
    """Convert a PDB structure file to mmCIF format.

    Args:
        pdb_path: Input PDB file.
        cif_path: Where to write the mmCIF file.

    Returns:
        Path to the written mmCIF file.
    """
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("s", str(pdb_path))
    io = MMCIFIO()
    io.set_structure(structure)
    cif_path.parent.mkdir(parents=True, exist_ok=True)
    io.save(str(cif_path))
    return cif_path
