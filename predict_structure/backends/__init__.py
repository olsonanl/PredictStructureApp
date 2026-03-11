"""Execution backends for structure prediction tools."""

from __future__ import annotations

from predict_structure.backends.docker import DockerBackend
from predict_structure.backends.subprocess import SubprocessBackend

BACKENDS: dict[str, type] = {
    "docker": DockerBackend,
    "subprocess": SubprocessBackend,
}


def get_backend(name: str, **kwargs) -> DockerBackend | SubprocessBackend:
    """Return a backend instance by name.

    Args:
        name: "docker" or "subprocess".
        **kwargs: Passed to backend constructor (e.g., default_image for Docker).

    Returns:
        Configured backend instance.

    Raises:
        ValueError: If name is not recognized.
    """
    cls = BACKENDS.get(name)
    if cls is None:
        raise ValueError(f"Unknown backend '{name}'. Choose from: {list(BACKENDS)}")
    return cls(**kwargs)


__all__ = ["DockerBackend", "SubprocessBackend", "BACKENDS", "get_backend"]
