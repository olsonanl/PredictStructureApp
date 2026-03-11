"""Tests for format conversion functions."""

import pytest
from pathlib import Path


class TestFastaToBoltzYaml:
    def test_single_chain(self, sample_fasta, tmp_output):
        from predict_structure.converters import fasta_to_boltz_yaml
        import yaml

        out = tmp_output / "input.yaml"
        result = fasta_to_boltz_yaml(sample_fasta, out)
        assert result == out
        assert out.exists()

        data = yaml.safe_load(out.read_text())
        assert data["version"] == 1
        assert len(data["sequences"]) == 1
        assert data["sequences"][0]["protein"]["id"] == "A"
        assert "TTCCPSIVAR" in data["sequences"][0]["protein"]["sequence"]

    def test_multi_chain(self, multi_chain_fasta, tmp_output):
        from predict_structure.converters import fasta_to_boltz_yaml
        import yaml

        out = tmp_output / "input.yaml"
        fasta_to_boltz_yaml(multi_chain_fasta, out)

        data = yaml.safe_load(out.read_text())
        assert len(data["sequences"]) == 2
        assert data["sequences"][0]["protein"]["id"] == "A"
        assert data["sequences"][1]["protein"]["id"] == "B"

    def test_with_msa(self, sample_fasta, tmp_output, sample_a3m):
        from predict_structure.converters import fasta_to_boltz_yaml
        import yaml

        out = tmp_output / "input.yaml"
        fasta_to_boltz_yaml(sample_fasta, out, msa_path=sample_a3m)

        data = yaml.safe_load(out.read_text())
        assert "msa" in data["sequences"][0]["protein"]
        assert str(sample_a3m) in data["sequences"][0]["protein"]["msa"]

    def test_empty_fasta(self, tmp_path, tmp_output):
        empty = tmp_path / "empty.fasta"
        empty.write_text("")
        from predict_structure.converters import fasta_to_boltz_yaml

        with pytest.raises(ValueError, match="No sequences"):
            fasta_to_boltz_yaml(empty, tmp_output / "out.yaml")


class TestA3mToParquet:
    def test_fallback_parse(self, sample_a3m, tmp_output):
        """Test manual A3M parsing fallback (no chai CLI available)."""
        from predict_structure.converters import a3m_to_parquet
        import pandas as pd

        out = tmp_output / "test.aligned.pqt"
        result = a3m_to_parquet(sample_a3m, out)
        assert result == out
        assert out.exists()

        df = pd.read_parquet(str(out))
        assert "sequence" in df.columns
        assert len(df) == 3  # query + 2 hits


class TestStructureConversion:
    """Test mmCIF ↔ PDB round-trip using a minimal PDB."""

    @pytest.fixture
    def minimal_pdb(self, tmp_path):
        """Create a minimal valid PDB file with one CA atom."""
        pdb = tmp_path / "minimal.pdb"
        pdb.write_text(
            "ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00  0.50           C\n"
            "END\n"
        )
        return pdb

    def test_pdb_to_mmcif(self, minimal_pdb, tmp_output):
        from predict_structure.converters import pdb_to_mmcif

        cif = tmp_output / "out.cif"
        result = pdb_to_mmcif(minimal_pdb, cif)
        assert result == cif
        assert cif.exists()
        content = cif.read_text()
        assert "loop_" in content or "data_" in content

    def test_mmcif_to_pdb(self, minimal_pdb, tmp_output):
        from predict_structure.converters import pdb_to_mmcif, mmcif_to_pdb

        cif = tmp_output / "out.cif"
        pdb_to_mmcif(minimal_pdb, cif)

        pdb_back = tmp_output / "back.pdb"
        result = mmcif_to_pdb(cif, pdb_back)
        assert result == pdb_back
        assert pdb_back.exists()
        assert "ATOM" in pdb_back.read_text()
