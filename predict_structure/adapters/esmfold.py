"""ESMFold adapter for protein structure prediction (HuggingFace)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from predict_structure.adapters.base import BaseAdapter
from predict_structure.normalizers import normalize_esmfold_output

logger = logging.getLogger(__name__)


class ESMFoldAdapter(BaseAdapter):
    """Adapter for ESMFold protein structure prediction (HuggingFace).

    ESMFold is a single-sequence model — no MSA required. Deterministic
    output (no sampling). Can run on CPU. Uses the modern HuggingFace
    transformers implementation (not legacy fair-esm/OpenFold).
    """

    tool_name: str = "esmfold"
    supports_msa: bool = False
    requires_gpu: bool = False

    def prepare_input(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        msa_path: Path | None = None,
        **kwargs: Any,
    ) -> Path:
        """FASTA pass-through. Warn if MSA provided."""
        if msa_path is not None:
            logger.warning("ESMFold does not use MSA input; ignoring --msa")
        return input_path

    def build_command(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        num_samples: int = 1,
        num_recycles: int = 3,
        seed: int | None = None,
        device: str = "gpu",
        **kwargs: Any,
    ) -> list[str]:
        """Construct the ``esm-fold-hf`` CLI command."""
        if num_samples > 1:
            logger.info("ESMFold is deterministic; ignoring --num-samples %d", num_samples)

        cmd = [
            "esm-fold-hf",
            "-i", str(input_path),
            "-o", str(output_dir),
            "--num-recycles", str(num_recycles),
        ]

        if device == "cpu":
            cmd.append("--cpu-only")

        # Pass-through ESMFold-specific flags
        if kwargs.get("esm_fp16"):
            cmd.append("--fp16")
        if kwargs.get("esm_chunk_size") is not None:
            cmd.extend(["--chunk-size", str(kwargs["esm_chunk_size"])])
        if kwargs.get("esm_max_tokens") is not None:
            cmd.extend(["--max-tokens-per-batch", str(kwargs["esm_max_tokens"])])

        return cmd

    def run(self, command: list[str], **kwargs: Any) -> int:
        """Execute prediction via the configured backend."""
        backend = kwargs.get("backend")
        if backend is None:
            from predict_structure.backends.subprocess import SubprocessBackend
            backend = SubprocessBackend()
        return backend.run(command, tool_name=self.tool_name, **kwargs)

    def normalize_output(self, raw_output_dir: Path, output_dir: Path) -> Path:
        """Normalize ESMFold output to standardized layout."""
        return normalize_esmfold_output(raw_output_dir, output_dir)

    def preflight(self) -> dict[str, Any]:
        return {
            "cpu": 8,
            "memory": "32G",
            "runtime": 3600,
        }
