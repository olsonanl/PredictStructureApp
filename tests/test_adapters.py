"""Tests for tool-specific adapters — parameter mapping and command construction."""

import pytest
from pathlib import Path


class TestBoltzAdapter:
    def test_build_command_defaults(self, sample_fasta, tmp_output):
        from predict_structure.adapters.boltz import BoltzAdapter

        adapter = BoltzAdapter()
        prepared = adapter.prepare_input(sample_fasta, tmp_output)
        cmd = adapter.build_command(prepared, tmp_output / "raw")

        assert cmd[0].endswith("boltz")
        assert cmd[1] == "predict"
        assert "--diffusion_samples" in cmd
        assert cmd[cmd.index("--diffusion_samples") + 1] == "1"
        assert "--recycling_steps" in cmd
        assert "--output_format" in cmd
        assert cmd[cmd.index("--output_format") + 1] == "mmcif"
        assert "--accelerator" in cmd
        assert cmd[cmd.index("--accelerator") + 1] == "gpu"

    def test_build_command_custom(self, sample_fasta, tmp_output):
        from predict_structure.adapters.boltz import BoltzAdapter

        adapter = BoltzAdapter()
        prepared = adapter.prepare_input(sample_fasta, tmp_output)
        cmd = adapter.build_command(
            prepared, tmp_output / "raw",
            num_samples=5, num_recycles=10, device="cpu",
            use_msa_server=True, boltz_use_potentials=True,
        )

        assert cmd[cmd.index("--diffusion_samples") + 1] == "5"
        assert cmd[cmd.index("--recycling_steps") + 1] == "10"
        assert cmd[cmd.index("--accelerator") + 1] == "cpu"
        assert "--use_msa_server" in cmd
        assert "--use_potentials" in cmd

    def test_prepare_input_fasta_to_yaml(self, sample_fasta, tmp_output):
        from predict_structure.adapters.boltz import BoltzAdapter

        adapter = BoltzAdapter()
        result = adapter.prepare_input(sample_fasta, tmp_output)
        assert result.suffix == ".yaml"
        assert result.exists()

    def test_prepare_input_yaml_passthrough(self, tmp_path, tmp_output):
        from predict_structure.adapters.boltz import BoltzAdapter
        import yaml

        yaml_file = tmp_path / "input.yaml"
        yaml_file.write_text(yaml.dump({"version": 1, "sequences": []}))

        adapter = BoltzAdapter()
        result = adapter.prepare_input(yaml_file, tmp_output)
        assert result == yaml_file

    def test_preflight(self):
        from predict_structure.adapters.boltz import BoltzAdapter

        pf = BoltzAdapter().preflight()
        assert pf["cpu"] == 8
        assert pf["memory"] == "96G"
        assert "policy_data" in pf


class TestChaiAdapter:
    def test_build_command(self, sample_fasta, tmp_output):
        from predict_structure.adapters.chai import ChaiAdapter

        adapter = ChaiAdapter()
        adapter.prepare_input(sample_fasta, tmp_output)
        cmd = adapter.build_command(
            sample_fasta, tmp_output / "raw",
            num_samples=3, num_recycles=5, seed=42,
        )

        assert cmd[0].endswith("chai-lab")
        assert cmd[1] == "fold"
        assert "--num-diffn-samples" in cmd
        assert cmd[cmd.index("--num-diffn-samples") + 1] == "3"
        assert "--num-trunk-recycles" in cmd
        assert cmd[cmd.index("--num-trunk-recycles") + 1] == "5"
        assert "--seed" in cmd
        assert cmd[cmd.index("--seed") + 1] == "42"

    def test_msa_conversion(self, sample_fasta, sample_a3m, tmp_output):
        from predict_structure.adapters.chai import ChaiAdapter

        adapter = ChaiAdapter()
        adapter.prepare_input(sample_fasta, tmp_output, msa_path=sample_a3m)
        assert adapter._msa_dir is not None

        cmd = adapter.build_command(sample_fasta, tmp_output / "raw")
        assert "--msa-directory" in cmd


class TestAlphaFoldAdapter:
    def test_build_command_requires_data_dir(self, sample_fasta, tmp_output):
        from predict_structure.adapters.alphafold import AlphaFoldAdapter

        adapter = AlphaFoldAdapter()
        with pytest.raises(ValueError, match="af2-data-dir"):
            adapter.build_command(sample_fasta, tmp_output / "raw")

    def test_build_command_with_data_dir(self, sample_fasta, tmp_output, tmp_path):
        from predict_structure.adapters.alphafold import AlphaFoldAdapter

        adapter = AlphaFoldAdapter()
        cmd = adapter.build_command(
            sample_fasta, tmp_output / "raw",
            af2_data_dir=str(tmp_path / "databases"),
            seed=123,
        )

        assert "run_alphafold.py" in cmd[1]
        assert "--fasta_paths" in cmd
        assert "--data_dir" in cmd
        assert "--uniref90_database_path" in cmd
        assert "--random_seed" in cmd
        assert cmd[cmd.index("--random_seed") + 1] == "123"

    def test_build_command_multimer(self, sample_fasta, tmp_output, tmp_path):
        from predict_structure.adapters.alphafold import AlphaFoldAdapter

        adapter = AlphaFoldAdapter()
        cmd = adapter.build_command(
            sample_fasta, tmp_output / "raw",
            af2_data_dir=str(tmp_path / "databases"),
            af2_model_preset="multimer",
        )

        assert "--pdb_seqres_database_path" in cmd
        assert "--uniprot_database_path" in cmd


class TestESMFoldAdapter:
    def test_build_command(self, sample_fasta, tmp_output):
        from predict_structure.adapters.esmfold import ESMFoldAdapter

        adapter = ESMFoldAdapter()
        cmd = adapter.build_command(
            sample_fasta, tmp_output / "raw",
            num_recycles=8, device="cpu",
        )

        assert cmd[0].endswith("esm-fold-hf")
        assert "-i" in cmd
        assert "-o" in cmd
        assert "--num-recycles" in cmd
        assert cmd[cmd.index("--num-recycles") + 1] == "8"
        assert "--cpu-only" in cmd

    def test_msa_warning(self, sample_fasta, sample_a3m, tmp_output, caplog):
        from predict_structure.adapters.esmfold import ESMFoldAdapter
        import logging

        with caplog.at_level(logging.WARNING):
            adapter = ESMFoldAdapter()
            adapter.prepare_input(sample_fasta, tmp_output, msa_path=sample_a3m)

        assert "does not use MSA" in caplog.text

    def test_preflight_no_gpu(self):
        from predict_structure.adapters.esmfold import ESMFoldAdapter

        pf = ESMFoldAdapter().preflight()
        assert "policy_data" not in pf
        assert pf["memory"] == "32G"

    def test_requires_gpu_false(self):
        from predict_structure.adapters.esmfold import ESMFoldAdapter

        assert ESMFoldAdapter.requires_gpu is False


class TestAdapterRegistry:
    def test_get_adapter_all_tools(self):
        from predict_structure.adapters import get_adapter

        for tool in ["boltz", "chai", "alphafold", "esmfold"]:
            adapter = get_adapter(tool)
            assert adapter.tool_name == tool

    def test_get_adapter_unknown(self):
        from predict_structure.adapters import get_adapter

        with pytest.raises(ValueError, match="Unknown tool"):
            get_adapter("nonexistent")

    def test_case_insensitive(self):
        from predict_structure.adapters import get_adapter

        adapter = get_adapter("Boltz")
        assert adapter.tool_name == "boltz"
