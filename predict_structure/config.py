"""Tool configuration loader.

Reads ``tools.yml`` from the package directory (or a path set via the
``PREDICT_STRUCTURE_CONFIG`` environment variable) and exposes helpers
for resolving container images, CWL tool definitions, and local
execution paths.

Image URIs use a scheme prefix:
    docker://dxkb/boltz-bvbrc:latest-gpu   → Docker image
    file:///path/to/image.sif              → Apptainer/Singularity image

Local execution fields:
    conda_env   — Conda environment name (subprocess wraps with conda run)
    executable  — Tool command name or path
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

# Default config ships with the package.
_DEFAULT_CONFIG = Path(__file__).resolve().parent / "tools.yml"

# Workspace root: two levels up from predict_structure/config.py
# (predict_structure/ → PredictStructureApp/ → dxkb/)
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _load_config() -> dict:
    """Load and cache the tools configuration."""
    config_path = os.environ.get("PREDICT_STRUCTURE_CONFIG", str(_DEFAULT_CONFIG))
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    return yaml.safe_load(path.read_text())


def get_tools() -> dict[str, dict]:
    """Return the full tools dict from config."""
    return _load_config().get("tools", {})


def get_tool_config(tool_name: str) -> dict:
    """Return config for a single tool. Raises KeyError if not found."""
    tools = get_tools()
    if tool_name not in tools:
        raise KeyError(
            f"Unknown tool '{tool_name}'. "
            f"Known tools: {', '.join(tools)}"
        )
    return tools[tool_name]


# -----------------------------------------------------------------
# Image helpers
# -----------------------------------------------------------------

def get_image_uri(tool_name: str) -> str:
    """Return the raw image URI (e.g. ``docker://dxkb/boltz:latest-gpu``)."""
    return get_tool_config(tool_name)["image"]


def get_image_scheme(tool_name: str) -> str:
    """Return the URI scheme: ``docker`` or ``file``."""
    uri = get_image_uri(tool_name)
    return uri.split("://", 1)[0]


def get_docker_image(tool_name: str) -> str:
    """Return the Docker image name (strip ``docker://`` prefix).

    Raises ValueError if the image is not a Docker image.
    """
    uri = get_image_uri(tool_name)
    if not uri.startswith("docker://"):
        raise ValueError(
            f"Tool '{tool_name}' image is not a Docker image: {uri}. "
            f"Use get_image_uri() for the raw URI."
        )
    return uri[len("docker://"):]


def get_sif_path(tool_name: str) -> Path:
    """Return the Apptainer .sif file path (strip ``file://`` prefix).

    Raises ValueError if the image is not a file URI.
    """
    uri = get_image_uri(tool_name)
    if not uri.startswith("file://"):
        raise ValueError(
            f"Tool '{tool_name}' image is not a file URI: {uri}. "
            f"Use get_image_uri() for the raw URI."
        )
    return Path(uri[len("file://"):])


# -----------------------------------------------------------------
# Local execution helpers
# -----------------------------------------------------------------

def get_conda_env(tool_name: str) -> str | None:
    """Return the conda environment name, or None if not configured."""
    return get_tool_config(tool_name).get("conda_env")


def get_command(tool_name: str) -> list[str]:
    """Return the base command (executable + subcommand) as a list.

    Example: ``["boltz", "predict"]`` or
    ``["/opt/conda-alphafold/bin/python", "/app/alphafold/run_alphafold.py"]``
    """
    cmd = get_tool_config(tool_name).get("command", [])
    if isinstance(cmd, str):
        return cmd.split()
    return list(cmd)


def get_shared_sif() -> Path | None:
    """Return the shared Apptainer .sif path from ``container.sif``, or None.

    Used when all tools live in a single container with per-tool conda envs.
    """
    container = _load_config().get("container", {})
    sif = container.get("sif")
    if sif and sif.startswith("file://"):
        return Path(sif[len("file://"):])
    return None


# -----------------------------------------------------------------
# CWL helpers
# -----------------------------------------------------------------

def get_cwl_path(tool_name: str) -> Path:
    """Return the absolute path to the tool's CWL definition."""
    rel = get_tool_config(tool_name).get("cwl")
    if not rel:
        raise KeyError(f"No CWL path configured for tool '{tool_name}'")
    return WORKSPACE_ROOT / rel
