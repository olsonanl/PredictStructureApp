"""Chai-1 adapter for protein structure prediction."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from predict_structure.adapters.base import BaseAdapter
from predict_structure.converters import a3m_to_parquet
from predict_structure.normalizers import normalize_chai_output

logger = logging.getLogger(__name__)


class ChaiAdapter(BaseAdapter):
    """Adapter for Chai-1 protein structure prediction.

    Chai-1 is a diffusion-based model for protein structure prediction.
    Takes FASTA input directly. MSA must be in Parquet format (.aligned.pqt)
    — A3M files are auto-converted. Outputs mmCIF + NPZ confidence scores.
    """

    tool_name: str = "chai"
    supports_msa: bool = True
    requires_gpu: bool = True

    def __init__(self) -> None:
        self._msa_dir: Path | None = None

    def prepare_input(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        msa_path: Path | None = None,
        **kwargs: Any,
    ) -> Path:
        """Pass FASTA through; convert A3M MSA to Parquet if provided."""
        if msa_path is not None:
            if msa_path.suffix.lower() == ".a3m":
                msa_out_dir = output_dir / "msa"
                msa_out_dir.mkdir(parents=True, exist_ok=True)
                parquet_path = msa_out_dir / (msa_path.stem + ".aligned.pqt")
                a3m_to_parquet(msa_path, parquet_path)
                self._msa_dir = msa_out_dir
            elif msa_path.is_dir():
                self._msa_dir = msa_path
            else:
                # Assume it's already in the right format; use parent as msa dir
                self._msa_dir = msa_path.parent
        return input_path

    def build_command(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        num_samples: int = 5,
        num_recycles: int = 3,
        seed: int | None = None,
        device: str = "gpu",
        **kwargs: Any,
    ) -> list[str]:
        """Construct the ``chai-lab fold`` CLI command."""
        from predict_structure.config import get_command
        sampling_steps = kwargs.get("sampling_steps", 200)
        num_trunk_samples = kwargs.get("num_trunk_samples", 1)
        recycle_msa_subsample = kwargs.get("recycle_msa_subsample", 0)

        cmd = [
            *get_command("chai"),
            str(input_path), str(output_dir),
            "--num-diffn-samples", str(num_samples),
            "--num-trunk-recycles", str(num_recycles),
            "--num-diffn-timesteps", str(sampling_steps),
            "--num-trunk-samples", str(num_trunk_samples),
            "--recycle-msa-subsample", str(recycle_msa_subsample),
            "--device", "cpu" if device == "cpu" else "cuda",
        ]

        if seed is not None:
            cmd.extend(["--seed", str(seed)])
        if self._msa_dir is not None:
            cmd.extend(["--msa-directory", str(self._msa_dir)])

        # MSA server
        if kwargs.get("use_msa_server"):
            cmd.append("--use-msa-server")
        if kwargs.get("msa_server_url"):
            cmd.extend(["--msa-server-url", kwargs["msa_server_url"]])

        # ESM embeddings (on by default; only emit flag when disabled)
        if kwargs.get("use_esm_embeddings") is False:
            cmd.append("--no-use-esm-embeddings")

        # Templates
        if kwargs.get("use_templates_server"):
            cmd.append("--use-templates-server")
        if kwargs.get("template_hits_path"):
            cmd.extend(["--template-hits-path", str(kwargs["template_hits_path"])])

        # Constraints
        if kwargs.get("constraint_path"):
            cmd.extend(["--constraint-path", str(kwargs["constraint_path"])])

        # Low memory (on by default; only emit flag when disabled)
        if kwargs.get("low_memory") is False:
            cmd.append("--no-low-memory")

        return cmd

    def run(self, command: list[str], **kwargs: Any) -> int:
        """Execute prediction via the configured backend."""
        backend = kwargs.get("backend")
        if backend is None:
            from predict_structure.backends.subprocess import SubprocessBackend
            backend = SubprocessBackend()
        return backend.run(command, tool_name=self.tool_name, **kwargs)

    def normalize_output(self, raw_output_dir: Path, output_dir: Path) -> Path:
        """Normalize Chai output to standardized layout."""
        return normalize_chai_output(raw_output_dir, output_dir)

    def preflight(self) -> dict[str, Any]:
        return {
            "cpu": 8,
            "memory": "64G",
            "runtime": 10800,
            "storage": "50G",
            "policy_data": {
                "gpu_count": 1,
                "partition": "gpu2",
                "constraint": "A100|H100|H200",
            },
        }
