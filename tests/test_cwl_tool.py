"""Tests for the unified CWL tool definition.

Validates the CWL structure by parsing the YAML directly and by
running cwltool --validate. No Docker or GPU required.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

CWL_TOOL = Path(__file__).resolve().parents[1] / "cwl" / "tools" / "predict-structure.cwl"
JOBS_DIR = Path(__file__).resolve().parents[1] / "cwl" / "jobs"


@pytest.fixture
def cwl_doc():
    """Load the CWL tool definition as a dict."""
    return yaml.safe_load(CWL_TOOL.read_text())


class TestCWLStructure:
    """Validate CWL tool definition structure by parsing YAML."""

    def test_cwl_version(self, cwl_doc):
        assert cwl_doc["cwlVersion"] == "v1.2"

    def test_class_is_command_line_tool(self, cwl_doc):
        assert cwl_doc["class"] == "CommandLineTool"

    def test_base_command(self, cwl_doc):
        assert cwl_doc["baseCommand"] == ["predict-structure"]

    def test_has_backend_subprocess_argument(self, cwl_doc):
        args = cwl_doc["arguments"]
        values = [a["valueFrom"] for a in args]
        assert "--backend" in values
        assert "subprocess" in values

    def test_tool_input_is_enum(self, cwl_doc):
        tool_input = cwl_doc["inputs"]["tool"]
        type_def = tool_input["type"]
        assert type_def["type"] == "enum"
        assert set(type_def["symbols"]) == {"boltz", "chai", "alphafold", "esmfold"}

    def test_input_file_is_required(self, cwl_doc):
        input_file = cwl_doc["inputs"]["input_file"]
        assert input_file["type"] == "File"

    def test_has_all_expected_inputs(self, cwl_doc):
        expected = {
            "tool", "input_file", "output_dir", "num_samples", "num_recycles",
            "seed", "device", "msa", "output_format", "sampling_steps",
            "use_msa_server", "af2_data_dir", "af2_model_preset", "af2_db_preset",
        }
        actual = set(cwl_doc["inputs"].keys())
        assert expected.issubset(actual), f"Missing inputs: {expected - actual}"

    def test_predictions_output_is_directory(self, cwl_doc):
        assert cwl_doc["outputs"]["predictions"]["type"] == "Directory"

    def test_has_metadata_output(self, cwl_doc):
        assert "metadata" in cwl_doc["outputs"]

    def test_has_confidence_output(self, cwl_doc):
        assert "confidence" in cwl_doc["outputs"]

    def test_docker_requirement_uses_javascript(self, cwl_doc):
        reqs = cwl_doc["requirements"]
        assert "InlineJavascriptRequirement" in reqs
        docker_pull = reqs["DockerRequirement"]["dockerPull"]
        assert "inputs.tool" in docker_pull

    def test_cuda_hint(self, cwl_doc):
        hints = cwl_doc["hints"]
        cuda = hints["cwltool:CUDARequirement"]
        assert cuda["cudaDeviceCountMin"] == 1


class TestCWLValidation:
    """Run cwltool --validate on the tool definition."""

    def test_cwltool_validates(self):
        result = subprocess.run(
            ["cwltool", "--validate", str(CWL_TOOL)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"cwltool validation failed:\n{result.stderr}"
        # cwltool may output to stdout or stderr depending on version
        combined = result.stdout + result.stderr
        assert "is valid CWL" in combined


class TestJobYAMLs:
    """Validate that all job YAML files are well-formed."""

    @pytest.fixture(params=sorted(JOBS_DIR.glob("*.yml")), ids=lambda p: p.stem)
    def job_doc(self, request):
        return yaml.safe_load(request.param.read_text())

    def test_has_tool(self, job_doc):
        assert "tool" in job_doc
        assert job_doc["tool"] in {"boltz", "chai", "alphafold", "esmfold"}

    def test_has_input_file(self, job_doc):
        assert "input_file" in job_doc
        assert job_doc["input_file"]["class"] == "File"

    def test_has_output_dir(self, job_doc):
        assert "output_dir" in job_doc
