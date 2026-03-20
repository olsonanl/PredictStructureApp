"""Entity data model for multi-entity structure prediction.

Defines entity types (protein, DNA, RNA, ligand, SMILES, glycan), sequence
type detection, and FASTA parsing with entity classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterator

from Bio import SeqIO


class EntityType(Enum):
    """Biological entity types supported by structure prediction tools."""

    PROTEIN = "protein"
    DNA = "dna"
    RNA = "rna"
    LIGAND = "ligand"
    SMILES = "smiles"
    GLYCAN = "glycan"


# Entity types that are represented as sequences in FASTA format
_FASTA_TYPES = frozenset({EntityType.PROTEIN, EntityType.DNA, EntityType.RNA})

# Entity types that are inline values (CCD codes, SMILES strings, etc.)
_INLINE_TYPES = frozenset({EntityType.LIGAND, EntityType.SMILES, EntityType.GLYCAN})

# Chain ID alphabet for entity assignment
_CHAIN_IDS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# DNA-only nucleotides (no U)
_DNA_BASES = set("ACGTN")

# RNA includes U
_RNA_BASES = set("ACGUN")


def detect_sequence_type(sequence: str) -> EntityType:
    """Detect whether a sequence is protein, DNA, or RNA.

    Rules:
      - Contains U and no T → RNA
      - All characters in {A, C, G, T, N} and length > 10 → DNA
      - Otherwise → protein

    Args:
        sequence: Uppercase sequence string.

    Returns:
        Detected EntityType (PROTEIN, DNA, or RNA).
    """
    seq_upper = sequence.upper().replace("\n", "").replace(" ", "")
    chars = set(seq_upper)

    # U present, no T → RNA
    if "U" in chars and "T" not in chars:
        return EntityType.RNA

    # All ACGTN and long enough → DNA
    if chars <= _DNA_BASES and len(seq_upper) > 10:
        return EntityType.DNA

    return EntityType.PROTEIN


@dataclass
class Entity:
    """A single biological entity for structure prediction.

    Attributes:
        entity_type: Type of entity (protein, DNA, RNA, ligand, etc.).
        value: File path (for FASTA entities) or inline value (CCD code, SMILES).
        name: Optional descriptive name (from FASTA header or user label).
        chain_id: Chain identifier assigned during conversion.
    """

    entity_type: EntityType
    value: str
    name: str = ""
    chain_id: str = ""


@dataclass
class EntityList:
    """Ordered collection of entities for a single prediction job.

    Manages chain ID assignment and provides filtered views by entity category.
    """

    entities: list[Entity] = field(default_factory=list)

    def add(self, entity_type: EntityType, value: str, name: str = "") -> None:
        """Add an entity and assign the next available chain ID."""
        chain_id = _CHAIN_IDS[len(self.entities) % len(_CHAIN_IDS)]
        self.entities.append(Entity(
            entity_type=entity_type,
            value=value,
            name=name or chain_id,
            chain_id=chain_id,
        ))

    @property
    def entity_types(self) -> set[EntityType]:
        """Return the set of distinct entity types present."""
        return {e.entity_type for e in self.entities}

    def fasta_entities(self) -> list[Entity]:
        """Return entities that are sequence-based (protein, DNA, RNA)."""
        return [e for e in self.entities if e.entity_type in _FASTA_TYPES]

    def inline_entities(self) -> list[Entity]:
        """Return entities that are inline values (ligand, SMILES, glycan)."""
        return [e for e in self.entities if e.entity_type in _INLINE_TYPES]

    def __len__(self) -> int:
        return len(self.entities)

    def __iter__(self) -> Iterator[Entity]:
        return iter(self.entities)

    def __bool__(self) -> bool:
        return len(self.entities) > 0


def parse_fasta_entities(
    fasta_path: Path,
    explicit_type: EntityType | None = None,
) -> list[Entity]:
    """Parse a FASTA file and return one Entity per sequence.

    If ``explicit_type`` is given, all sequences are assigned that type.
    Otherwise, each sequence is auto-detected via ``detect_sequence_type``.

    Args:
        fasta_path: Path to FASTA file.
        explicit_type: Force all sequences to this type (PROTEIN, DNA, or RNA).

    Returns:
        List of Entity objects (without chain IDs — caller assigns via EntityList.add).
    """
    records = list(SeqIO.parse(str(fasta_path), "fasta"))
    if not records:
        raise ValueError(f"No sequences found in {fasta_path}")

    entities = []
    for record in records:
        seq = str(record.seq)
        etype = explicit_type if explicit_type is not None else detect_sequence_type(seq)
        entities.append(Entity(
            entity_type=etype,
            value=seq,
            name=record.id,
        ))
    return entities


def is_boltz_yaml(path: Path) -> bool:
    """Check if a file is a Boltz-2 YAML input manifest.

    A valid Boltz YAML has a ``.yaml`` or ``.yml`` extension and contains
    both ``version`` and ``sequences`` keys at the top level.

    Args:
        path: File path to check.

    Returns:
        True if the file is a Boltz YAML manifest.
    """
    if path.suffix.lower() not in (".yaml", ".yml"):
        return False
    try:
        import yaml

        data = yaml.safe_load(path.read_text())
        return isinstance(data, dict) and "version" in data and "sequences" in data
    except Exception:
        return False
