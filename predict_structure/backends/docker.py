"""Docker execution backend for containerized tool invocation."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Each tool has its own dedicated container image (delegation pattern).
DEFAULT_IMAGES: dict[str, str] = {
    "boltz": "dxkb/boltz-bvbrc:latest-gpu",
    "chai": "dxkb/chai-bvbrc:latest-gpu",
    "alphafold": "wilke/alphafold",
    "esmfold": "dxkb/esmfold-bvbrc:latest-gpu",
}


class DockerBackend:
    """Run prediction commands inside per-tool Docker containers.

    Each prediction tool runs in its own isolated Docker image. The backend
    resolves the correct image from DEFAULT_IMAGES using tool_name, then
    builds a ``docker run`` invocation with GPU passthrough and volume mounts.
    """

    def __init__(self, default_image: str | None = None):
        self._default_image = default_image

    def run(
        self,
        command: list[str],
        *,
        image: str | None = None,
        tool_name: str | None = None,
        volumes: dict[str, str] | None = None,
        gpu: bool = True,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        **kwargs,
    ) -> int:
        """Build and execute a docker run command.

        Image resolution order:
        1. ``image`` parameter (explicit override)
        2. ``self._default_image`` (from constructor / CLI --image flag)
        3. ``DEFAULT_IMAGES[tool_name]`` (per-tool default)

        Args:
            command: The tool command to run inside the container.
            image: Docker image override.
            tool_name: Tool name for looking up DEFAULT_IMAGES.
            volumes: Host→container volume mounts.
            gpu: Whether to pass ``--gpus all``.
            env: Environment variables for the container.
            timeout: Max seconds for the container to run.

        Returns:
            Exit code from ``docker run``.
        """
        resolved_image = image or self._default_image
        if resolved_image is None:
            if tool_name and tool_name in DEFAULT_IMAGES:
                resolved_image = DEFAULT_IMAGES[tool_name]
            else:
                raise ValueError(
                    f"No Docker image specified and no default for tool '{tool_name}'. "
                    f"Use --image or provide a recognized tool_name."
                )

        docker_cmd: list[str] = ["docker", "run", "--rm"]

        if gpu:
            docker_cmd.extend(["--gpus", "all"])

        for host_path, container_path in (volumes or {}).items():
            docker_cmd.extend(["-v", f"{host_path}:{container_path}"])

        for key, val in (env or {}).items():
            docker_cmd.extend(["-e", f"{key}={val}"])

        docker_cmd.append(resolved_image)
        docker_cmd.extend(command)

        logger.info("Running: %s", " ".join(docker_cmd))
        result = subprocess.run(docker_cmd, timeout=timeout)
        return result.returncode
