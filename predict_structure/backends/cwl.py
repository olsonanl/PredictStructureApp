"""CWL execution backend for workflow-based tool invocation."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Mapping from CLI flags to CWL job input names.
# Flags not in this map are passed through with the flag name (minus --)
# converted to underscore.
_FLAG_TO_CWL: dict[str, str] = {
    "--output-dir": "output_dir",
    "--num-samples": "num_samples",
    "--num-recycles": "num_recycles",
    "--seed": "seed",
    "--device": "device",
    "--msa": "msa",
    "--output-format": "output_format",
    "--sampling-steps": "sampling_steps",
    "--use-msa-server": "use_msa_server",
    "--af2-data-dir": "af2_data_dir",
    "--af2-model-preset": "af2_model_preset",
    "--af2-db-preset": "af2_db_preset",
    "--image": None,       # consumed by docker backend, skip
    "--backend": None,     # meta-flag, skip
}

# Flags that are boolean (presence = true)
_BOOLEAN_FLAGS = {"--use-msa-server"}

# Flags whose CWL type is File (need class: File wrapper)
_FILE_FLAGS = {"--msa"}

# Flags whose CWL type is Directory (need class: Directory wrapper)
_DIRECTORY_FLAGS = {"--af2-data-dir"}

# Integer-valued CWL inputs
_INT_FLAGS = {"--num-samples", "--num-recycles", "--seed", "--sampling-steps"}


class CWLBackend:
    """Run predictions via CWL (cwltool, toil-cwl-runner, or GoWe).

    The backend takes the command list produced by an adapter's
    ``build_command()`` method, reverse-maps it into a CWL job YAML,
    and invokes the CWL runner with the unified predict-structure.cwl
    tool definition.
    """

    DEFAULT_CWL_TOOL = Path(__file__).resolve().parents[2] / "cwl" / "tools" / "predict-structure.cwl"
    DEFAULT_RUNNER = "cwltool"

    def __init__(
        self,
        cwl_tool: str | Path | None = None,
        runner: str | None = None,
    ):
        self._cwl_tool = str(cwl_tool or self.DEFAULT_CWL_TOOL)
        self._runner = runner or self.DEFAULT_RUNNER

    def run(
        self,
        command: list[str],
        *,
        tool_name: str | None = None,
        gpu: bool = True,
        timeout: int | None = None,
        **kwargs,
    ) -> int:
        """Build a CWL job YAML from command args and invoke the runner.

        Args:
            command: The tool command as a list of strings (from adapter.build_command).
            tool_name: Tool name (boltz, chai, alphafold, esmfold).
            gpu: Whether GPU is requested (encoded in CWL hints, not job YAML).
            timeout: Max seconds for the CWL runner.

        Returns:
            Exit code from the CWL runner.
        """
        job = self._build_job_yaml(command, tool_name)

        job_dir = Path(tempfile.mkdtemp(prefix="cwl-job-"))
        job_path = job_dir / "job.yml"
        job_path.write_text(yaml.dump(job, default_flow_style=False))

        cwl_cmd = [self._runner, str(self._cwl_tool), str(job_path)]
        logger.info("Running: %s", " ".join(cwl_cmd))

        result = subprocess.run(cwl_cmd, timeout=timeout)
        return result.returncode

    def _build_job_yaml(
        self,
        command: list[str],
        tool_name: str | None,
    ) -> dict:
        """Parse a predict-structure CLI command into CWL job inputs.

        The adapter produces something like:
            ["boltz", "predict", "/path/input.yaml", "--out_dir", "/path/out", ...]

        But the CWL tool wraps ``predict-structure <tool> <input> [OPTIONS]``,
        so we need to extract the tool name and input file from the native
        command and map the options to CWL input names.

        Args:
            command: Native tool command list from adapter.build_command().
            tool_name: Tool identifier from the adapter.

        Returns:
            Dict suitable for yaml.dump as a CWL job file.
        """
        job: dict = {}

        if tool_name:
            job["tool"] = tool_name

        # Find the input file — first positional arg that looks like a file path
        input_file = self._find_input_file(command)
        if input_file:
            job["input_file"] = {"class": "File", "path": str(input_file)}

        # Parse flags from the command
        i = 0
        while i < len(command):
            arg = command[i]
            if arg.startswith("--"):
                cwl_name = _FLAG_TO_CWL.get(arg)
                if cwl_name is None and arg in _FLAG_TO_CWL:
                    # Explicitly skipped flag
                    i += 2 if (i + 1 < len(command) and not command[i + 1].startswith("--")) else 1
                    continue
                if cwl_name is None:
                    # Unknown flag — convert to underscore name
                    cwl_name = arg.lstrip("-").replace("-", "_")

                if arg in _BOOLEAN_FLAGS:
                    job[cwl_name] = True
                    i += 1
                    continue

                # Consume next token as value
                if i + 1 < len(command):
                    val = command[i + 1]
                    if arg in _FILE_FLAGS:
                        job[cwl_name] = {"class": "File", "path": val}
                    elif arg in _DIRECTORY_FLAGS:
                        job[cwl_name] = {"class": "Directory", "path": val}
                    elif arg in _INT_FLAGS:
                        job[cwl_name] = int(val)
                    else:
                        job[cwl_name] = val
                    i += 2
                else:
                    i += 1
            else:
                i += 1

        return job

    @staticmethod
    def _find_input_file(command: list[str]) -> Path | None:
        """Extract the input file path from a native tool command.

        Heuristic: find the first argument that looks like a file path
        (contains a dot or slash) and is not a flag value.
        """
        for i, arg in enumerate(command):
            if arg.startswith("-"):
                continue
            # Skip the tool subcommand (e.g., "predict", "fold")
            if arg in ("predict", "fold", "run_alphafold.py"):
                continue
            # Check if this looks like a file path
            p = Path(arg)
            if p.suffix or "/" in arg:
                return p
        return None
