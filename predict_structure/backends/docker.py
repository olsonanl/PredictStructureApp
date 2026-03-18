"""Docker execution backend for containerized tool invocation."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from predict_structure.config import get_docker_image, get_image_uri, get_image_scheme

logger = logging.getLogger(__name__)

# Container mount points.
CONTAINER_INPUT = "/input"
CONTAINER_OUTPUT = "/output"
CONTAINER_DATA = "/databases"


class DockerBackend:
    """Run prediction commands inside per-tool Docker containers.

    Each prediction tool runs in its own isolated Docker image. Images are
    resolved from ``tools.yml`` via :func:`get_docker_image`. The ``--image``
    CLI flag can override the configured image.

    Volume mounts and path rewriting are handled by the caller (``run_prediction``
    in cli.py) which has full context of input, output, and data directories.
    """

    def __init__(self, default_image: str | None = None):
        self._default_image = default_image

    def _resolve_image(
        self,
        image: str | None = None,
        tool_name: str | None = None,
    ) -> str:
        """Resolve the Docker image to use.

        Resolution order:
        1. ``image`` parameter (explicit override)
        2. ``self._default_image`` (from constructor / CLI --image flag)
        3. ``tools.yml`` config via :func:`get_docker_image`
        """
        resolved = image or self._default_image
        if resolved is None:
            if tool_name:
                resolved = get_docker_image(tool_name)
            else:
                raise ValueError(
                    f"No Docker image specified and no tool_name to look up. "
                    f"Use --image or provide a recognized tool_name."
                )
        return resolved

    def _build_docker_cmd(
        self,
        command: list[str],
        *,
        image: str | None = None,
        tool_name: str | None = None,
        volumes: dict[str, str] | None = None,
        gpu: bool = True,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Build the full ``docker run`` command list."""
        resolved_image = self._resolve_image(image, tool_name)

        docker_cmd: list[str] = ["docker", "run", "--rm"]

        if gpu:
            docker_cmd.extend(["--gpus", "all"])

        for host_path, container_path in (volumes or {}).items():
            docker_cmd.extend(["-v", f"{host_path}:{container_path}"])

        for key, val in (env or {}).items():
            docker_cmd.extend(["-e", f"{key}={val}"])

        docker_cmd.append(resolved_image)
        docker_cmd.extend(command)
        return docker_cmd

    def format_command(
        self,
        command: list[str],
        **kwargs,
    ) -> list[str]:
        """Return the full ``docker run ...`` command as a single shell-ready string."""
        docker_cmd = self._build_docker_cmd(command, **kwargs)
        return [" ".join(docker_cmd)]

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

        Args:
            command: The tool command to run inside the container.
            image: Docker image override.
            tool_name: Tool name for resolving image from config.
            volumes: Host→container volume mounts ({host: container}).
            gpu: Whether to pass ``--gpus all``.
            env: Environment variables for the container.
            timeout: Max seconds for the container to run.

        Returns:
            Exit code from ``docker run``.
        """
        docker_cmd = self._build_docker_cmd(
            command, image=image, tool_name=tool_name,
            volumes=volumes, gpu=gpu, env=env,
        )

        logger.info("Running: %s", " ".join(docker_cmd))
        result = subprocess.run(docker_cmd, timeout=timeout)
        return result.returncode
