"""Tests for the CWL execution backend.

All tests mock subprocess.run to avoid requiring cwltool at runtime.
The CWL backend now dispatches to per-tool CWL definitions (boltz.cwl,
chailab.cwl, etc.) rather than the unified predict-structure.cwl.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


class TestCWLBackendRegistry:
    """Verify CWL backend is properly registered."""

    def test_backend_registered(self):
        from predict_structure.backends import BACKENDS
        assert "cwl" in BACKENDS

    def test_get_backend_cwl(self):
        from predict_structure.backends import get_backend
        from predict_structure.backends.cwl import CWLBackend

        backend = get_backend("cwl")
        assert isinstance(backend, CWLBackend)

    def test_get_backend_cwl_with_runner(self):
        from predict_structure.backends import get_backend

        backend = get_backend("cwl", runner="toil-cwl-runner")
        assert backend._runner == "toil-cwl-runner"

    def test_get_backend_cwl_with_tool(self, tmp_path):
        from predict_structure.backends import get_backend

        tool_path = tmp_path / "my-tool.cwl"
        backend = get_backend("cwl", cwl_tool=str(tool_path))
        assert backend._cwl_tool_override == str(tool_path)


class TestCWLBackendDefaults:
    """Verify default configuration."""

    def test_default_runner(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        assert backend._runner == "cwltool"

    def test_per_tool_cwl_definitions_exist(self):
        """Each tool has a CWL definition in its app repo."""
        from predict_structure.config import get_tools, get_cwl_path

        for tool in get_tools():
            cwl_path = get_cwl_path(tool)
            assert cwl_path.exists(), f"CWL tool for '{tool}' not found at {cwl_path}"

    def test_resolves_per_tool_cwl(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        for tool in ("boltz", "chai", "alphafold", "esmfold"):
            cwl_path = backend._resolve_cwl_tool(tool)
            assert Path(cwl_path).exists()
            assert tool in cwl_path.lower() or tool[:4] in cwl_path.lower()

    def test_override_takes_precedence(self, tmp_path):
        from predict_structure.backends.cwl import CWLBackend

        override = tmp_path / "custom.cwl"
        override.touch()
        backend = CWLBackend(cwl_tool=str(override))
        assert backend._resolve_cwl_tool("boltz") == str(override)


class TestBuildJobYAML:
    """Test command-to-job-YAML conversion with native CWL input names."""

    def test_boltz_command(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "boltz", "predict", "/data/input.yaml",
            "--out_dir", "/data/output",
            "--diffusion_samples", "3",
        ]
        job = backend._build_job_yaml(command, tool_name="boltz")

        # No "tool" key — the CWL definition IS the tool
        assert "tool" not in job
        assert job["input_file"]["class"] == "File"
        assert job["input_file"]["path"] == "/data/input.yaml"
        assert job["output_dir"] == "/data/output"
        assert job["diffusion_samples"] == 3

    def test_esmfold_command(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "esm-fold-hf", "-i", "/data/input.fasta",
            "-o", "/data/output",
            "--num-recycles", "4",
        ]
        job = backend._build_job_yaml(command, tool_name="esmfold")

        assert "tool" not in job
        assert job["sequences"]["class"] == "File"
        assert job["sequences"]["path"] == "/data/input.fasta"
        assert job["output_dir"] == "/data/output"
        assert job["num_recycles"] == 4

    def test_chai_positional_output(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "chai-lab", "fold", "/data/input.fasta", "/data/output",
            "--num-diffn-samples", "5",
            "--num-trunk-recycles", "3",
            "--num-diffn-timesteps", "200",
            "--device", "cuda",
            "--use-msa-server",
        ]
        job = backend._build_job_yaml(command, tool_name="chai")

        assert "tool" not in job
        assert job["input_fasta"]["class"] == "File"
        assert job["input_fasta"]["path"] == "/data/input.fasta"
        assert job["output_directory"] == "/data/output"
        assert job["num_diffn_samples"] == 5
        assert job["num_trunk_recycles"] == 3
        assert job["num_diffn_timesteps"] == 200
        assert job["device"] == "cuda"
        assert job["use_msa_server"] is True

    def test_boltz_use_msa_server_boolean(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "boltz", "predict", "/data/input.yaml",
            "--out_dir", "/data/output",
            "--use_msa_server",
        ]
        job = backend._build_job_yaml(command, tool_name="boltz")

        assert job["use_msa_server"] is True

    def test_alphafold_with_data_dir(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "python", "/app/alphafold/run_alphafold.py",
            "--fasta_paths", "/data/input.fasta",
            "--output_dir", "/data/output",
            "--data_dir", "/databases",
            "--model_preset", "monomer",
            "--db_preset", "reduced_dbs",
            "--max_template_date", "2022-01-01",
            "--uniref90_database_path", "/databases/uniref90/uniref90.fasta",
            "--pdb70_database_path", "/databases/pdb70/pdb70",
            "--use_gpu_relax=true",
        ]
        job = backend._build_job_yaml(command, tool_name="alphafold")

        assert "tool" not in job
        assert job["fasta_paths"]["class"] == "File"
        assert job["fasta_paths"]["path"] == "/data/input.fasta"
        assert job["output_dir"] == "/data/output"
        assert job["data_dir"] == "/databases"
        assert job["model_preset"] == "monomer"
        assert job["use_gpu_relax"] is True
        # Database sub-paths should be skipped (derived from data_dir)
        assert "uniref90_database_path" not in job
        assert "pdb70_database_path" not in job

    def test_skips_unknown_flags(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "boltz", "predict", "/data/input.yaml",
            "--out_dir", "/data/output",
            "--backend", "subprocess",
            "--image", "my/image:latest",
        ]
        job = backend._build_job_yaml(command, tool_name="boltz")

        assert "backend" not in job
        assert "image" not in job


class TestCWLBackendRun:
    """Test the run() method with mocked subprocess."""

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_invokes_per_tool_cwl(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend()

        command = ["boltz", "predict", "/data/input.yaml", "--out_dir", "/data/output"]
        rc = backend.run(command, tool_name="boltz")

        assert rc == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "cwltool"
        assert "boltz.cwl" in call_args[1]
        assert call_args[2].endswith(".yml")

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_returns_nonzero_exit_code(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=1)
        backend = CWLBackend()

        rc = backend.run(
            ["boltz", "predict", "/data/input.yaml", "--out_dir", "/data/output"],
            tool_name="boltz",
        )
        assert rc == 1

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_custom_runner(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend(runner="toil-cwl-runner")

        backend.run(
            ["boltz", "predict", "/data/input.yaml", "--out_dir", "/data/output"],
            tool_name="boltz",
        )

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "toil-cwl-runner"

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_job_yaml_written_to_disk(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend()

        backend.run(
            ["boltz", "predict", "/data/input.yaml",
             "--out_dir", "/data/output",
             "--diffusion_samples", "3"],
            tool_name="boltz",
        )

        job_path = Path(mock_run.call_args[0][0][2])
        assert job_path.exists()
        job_doc = yaml.safe_load(job_path.read_text())
        assert "tool" not in job_doc
        assert job_doc["input_file"]["path"] == "/data/input.yaml"
        assert job_doc["diffusion_samples"] == 3

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_timeout_passed(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend()

        backend.run(
            ["boltz", "predict", "/data/input.yaml", "--out_dir", "/data/output"],
            tool_name="boltz",
            timeout=3600,
        )

        assert mock_run.call_args[1]["timeout"] == 3600

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_esmfold_resolves_to_esmfold_cwl(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend()

        backend.run(
            ["esm-fold-hf", "-i", "/data/input.fasta", "-o", "/data/output"],
            tool_name="esmfold",
        )

        call_args = mock_run.call_args[0][0]
        assert "esmfold.cwl" in call_args[1]
