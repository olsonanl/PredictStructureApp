"""Tests for the CWL execution backend.

All tests mock subprocess.run to avoid requiring cwltool at runtime.
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
        assert backend._cwl_tool == str(tool_path)


class TestCWLBackendDefaults:
    """Verify default configuration."""

    def test_default_runner(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        assert backend._runner == "cwltool"

    def test_default_cwl_tool_exists(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        assert Path(backend._cwl_tool).exists()

    def test_default_cwl_tool_is_predict_structure(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        assert "predict-structure.cwl" in backend._cwl_tool


class TestBuildJobYAML:
    """Test command-to-job-YAML conversion."""

    def test_boltz_command(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "boltz", "predict", "/data/input.yaml",
            "--out_dir", "/data/output",
            "--diffusion_samples", "3",
        ]
        job = backend._build_job_yaml(command, tool_name="boltz")

        assert job["tool"] == "boltz"
        assert job["input_file"]["class"] == "File"
        assert job["input_file"]["path"] == "/data/input.yaml"

    def test_esmfold_command(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "esm-fold-hf", "-i", "/data/input.fasta",
            "-o", "/data/output",
            "--num-recycles", "4",
        ]
        job = backend._build_job_yaml(command, tool_name="esmfold")

        assert job["tool"] == "esmfold"
        assert job["num_recycles"] == 4

    def test_chai_with_msa(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "chai-lab", "fold", "/data/input.fasta", "output",
            "--num-samples", "5",
            "--msa", "/data/alignment.a3m",
        ]
        job = backend._build_job_yaml(command, tool_name="chai")

        assert job["tool"] == "chai"
        assert job["num_samples"] == 5
        assert job["msa"]["class"] == "File"
        assert job["msa"]["path"] == "/data/alignment.a3m"

    def test_use_msa_server_boolean(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "boltz", "predict", "/data/input.yaml",
            "--use-msa-server",
        ]
        job = backend._build_job_yaml(command, tool_name="boltz")

        assert job["use_msa_server"] is True

    def test_alphafold_with_data_dir(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "run_alphafold.py",
            "--fasta_paths", "/data/input.fasta",
            "--output_dir", "/data/output",
            "--af2-data-dir", "/databases/alphafold",
        ]
        job = backend._build_job_yaml(command, tool_name="alphafold")

        assert job["tool"] == "alphafold"
        assert job["af2_data_dir"]["class"] == "Directory"
        assert job["af2_data_dir"]["path"] == "/databases/alphafold"

    def test_skips_backend_flag(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "boltz", "predict", "/data/input.yaml",
            "--backend", "subprocess",
        ]
        job = backend._build_job_yaml(command, tool_name="boltz")

        assert "backend" not in job

    def test_skips_image_flag(self):
        from predict_structure.backends.cwl import CWLBackend

        backend = CWLBackend()
        command = [
            "boltz", "predict", "/data/input.yaml",
            "--image", "my/image:latest",
        ]
        job = backend._build_job_yaml(command, tool_name="boltz")

        assert "image" not in job


class TestCWLBackendRun:
    """Test the run() method with mocked subprocess."""

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_invokes_cwltool(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend()

        command = ["boltz", "predict", "/data/input.yaml"]
        rc = backend.run(command, tool_name="boltz")

        assert rc == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "cwltool"
        assert "predict-structure.cwl" in call_args[1]
        # Third arg is the job YAML path
        assert call_args[2].endswith(".yml")

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_returns_nonzero_exit_code(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=1)
        backend = CWLBackend()

        rc = backend.run(["boltz", "predict", "/data/input.yaml"], tool_name="boltz")
        assert rc == 1

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_custom_runner(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend(runner="toil-cwl-runner")

        backend.run(["boltz", "predict", "/data/input.yaml"], tool_name="boltz")

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "toil-cwl-runner"

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_job_yaml_written_to_disk(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend()

        backend.run(
            ["boltz", "predict", "/data/input.yaml", "--num-samples", "3"],
            tool_name="boltz",
        )

        job_path = Path(mock_run.call_args[0][0][2])
        assert job_path.exists()
        job_doc = yaml.safe_load(job_path.read_text())
        assert job_doc["tool"] == "boltz"
        assert job_doc["num_samples"] == 3

    @patch("predict_structure.backends.cwl.subprocess.run")
    def test_timeout_passed(self, mock_run):
        from predict_structure.backends.cwl import CWLBackend

        mock_run.return_value = MagicMock(returncode=0)
        backend = CWLBackend()

        backend.run(
            ["boltz", "predict", "/data/input.yaml"],
            tool_name="boltz",
            timeout=3600,
        )

        assert mock_run.call_args[1]["timeout"] == 3600
