"""Unified CLI entry point for protein structure prediction.

Usage:
    predict-structure <tool> <input> [OPTIONS]

Examples:
    predict-structure boltz input.fasta -o output/ --num-samples 5 --use-potentials
    predict-structure esmfold input.fasta -o output/ --num-recycles 4 --fp16
    predict-structure chai input.fasta -o output/ --msa alignment.a3m
    predict-structure alphafold input.fasta -o output/ --af2-data-dir /data
"""

from __future__ import annotations

import functools
import shutil
import sys
import time
from pathlib import Path

import click
from click_option_group import optgroup

from predict_structure import __version__
from predict_structure.adapters import get_adapter
from predict_structure.backends import get_backend
from predict_structure.normalizers import write_metadata_json


# ---------------------------------------------------------------------------
# Tool auto-discovery
# ---------------------------------------------------------------------------

from predict_structure.config import get_command, get_tools

# Default AlphaFold database directory (checked during discovery)
AF2_DEFAULT_DATA_DIR = Path("/databases")


def _is_tool_available(tool: str) -> bool:
    """Check if a prediction tool is installed and accessible.

    Checks the first element of the tool's ``command`` list from
    ``tools.yml`` — either on PATH (via ``shutil.which``) or as an
    absolute filesystem path.
    """
    try:
        cmd = get_command(tool)
    except KeyError:
        return False
    if not cmd:
        return False
    exe = cmd[0]
    # Absolute path — check if file exists
    if exe.startswith("/"):
        return Path(exe).exists()
    # Relative — check PATH
    return shutil.which(exe) is not None


def discover_tool(input_file: Path, device: str = "gpu") -> str:
    """Auto-discover the best available prediction tool.

    Selection rules:
      - ``.yaml`` / ``.yml`` input forces Boltz (only tool supporting YAML).
      - ``device=cpu`` prefers ESMFold (others are impractical on CPU).
      - Otherwise pick first available in accuracy-priority order:
        Boltz > Chai > AlphaFold > ESMFold.

    AlphaFold is only considered available when both an executable **and**
    the default database directory (``/databases``) are found.

    Raises:
        click.UsageError: If no suitable tool is found.
    """
    suffix = input_file.suffix.lower()

    # YAML input → must be Boltz
    if suffix in (".yaml", ".yml"):
        if _is_tool_available("boltz"):
            return "boltz"
        raise click.UsageError(
            "YAML input requires Boltz, but 'boltz' is not found on PATH."
        )

    # CPU → strongly prefer ESMFold (others are impractical without GPU)
    if device == "cpu":
        if _is_tool_available("esmfold"):
            return "esmfold"
        # Fall through to general priority

    # Accuracy-priority order
    for tool in ("boltz", "chai", "alphafold", "esmfold"):
        if tool == "alphafold":
            # AlphaFold also requires its database directory
            if _is_tool_available(tool) or AF2_DEFAULT_DATA_DIR.is_dir():
                # Need both executable AND data
                has_exe = any(
                    shutil.which(e) for e in _TOOL_EXECUTABLES.get(tool, [])
                ) or any(Path(p).exists() for p in _TOOL_PATHS.get(tool, []))
                if has_exe and AF2_DEFAULT_DATA_DIR.is_dir():
                    return tool
        elif _is_tool_available(tool):
            return tool

    raise click.UsageError(
        "No prediction tool found on PATH. "
        "Install one of: boltz, chai-lab, run_alphafold.py, esm-fold-hf"
    )


# ---------------------------------------------------------------------------
# Shared options applied to every tool subcommand
# ---------------------------------------------------------------------------

def shared_options(func):
    """Decorator that applies options common to all prediction tools.

    Help order (top to bottom): Global options, [Tool options], Execution options.
    Click decorators stack bottom-up, so Execution is applied last (via backend_options).
    """
    @click.argument("input_file", type=click.Path(exists=True))
    @optgroup.group("Global options")
    @optgroup.option("-o", "--output-dir", type=click.Path(), required=True, help="Output directory")
    @optgroup.option("--num-samples", "-n", type=int, default=1, help="Number of structure samples")
    @optgroup.option("--num-recycles", type=int, default=3, help="Recycling iterations")
    @optgroup.option("--seed", type=int, default=None, help="Random seed")
    @optgroup.option("--msa", type=click.Path(), default=None, help="MSA file (.a3m, .sto, .pqt)")
    @optgroup.option("--output-format", type=click.Choice(["pdb", "mmcif"]), default="pdb")
    @click.option("--debug", is_flag=True, default=False, help="Print the command instead of executing it")
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


def backend_options(func):
    """Decorator that applies execution/backend options (shown last in help)."""
    @optgroup.group("Execution options")
    @optgroup.option(
        "--backend",
        type=click.Choice(["docker", "subprocess", "cwl"]),
        default="subprocess",
        help="Execution backend",
    )
    @optgroup.option("--device", type=click.Choice(["gpu", "cpu"]), default="gpu", help="Compute device")
    @optgroup.option("--image", default=None, help="Override Docker image (docker backend only)")
    @optgroup.option("--cwl-runner", default=None, help="CWL runner command (default: cwltool)")
    @optgroup.option("--cwl-tool", default=None, help="Path to CWL tool definition")
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Shared prediction logic
# ---------------------------------------------------------------------------

def _docker_volumes_and_rewrite(
    cmd: list[str],
    *,
    input_path: Path,
    output_dir: Path,
    data_dir: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Build Docker volume mounts and rewrite host paths in the command.

    Returns:
        (volumes, rewritten_cmd) where *volumes* is ``{host: container}``
        and *rewritten_cmd* has host paths replaced with container paths.
    """
    from predict_structure.backends.docker import (
        CONTAINER_INPUT, CONTAINER_OUTPUT, CONTAINER_DATA,
    )

    volumes: dict[str, str] = {}
    input_host = str(input_path.resolve().parent)
    output_host = str(output_dir.resolve())

    volumes[input_host] = CONTAINER_INPUT
    volumes[output_host] = CONTAINER_OUTPUT

    if data_dir:
        data_host = str(Path(data_dir).resolve())
        volumes[data_host] = CONTAINER_DATA

    # Build replacement map sorted longest-prefix-first so
    # /databases/uniref90 is not matched before /databases.
    replacements = sorted(volumes.items(), key=lambda kv: -len(kv[0]))

    rewritten: list[str] = []
    for arg in cmd:
        new_arg = arg
        # Only rewrite if arg contains a path-like string
        if "/" in arg or Path(arg).is_absolute():
            # Always resolve symlinks (e.g. /tmp → /private/tmp on macOS)
            resolved = str(Path(arg).resolve())
            for host_dir, container_dir in replacements:
                if resolved.startswith(host_dir + "/") or resolved == host_dir:
                    new_arg = container_dir + resolved[len(host_dir):]
                    break
        rewritten.append(new_arg)

    return volumes, rewritten


def run_prediction(tool_name: str, extra_kwargs: dict, **shared):
    """Core prediction logic shared by all tool subcommands.

    Args:
        tool_name: Adapter key (boltz, chai, alphafold, esmfold).
        extra_kwargs: Tool-specific keyword arguments for build_command.
        **shared: Shared CLI options (input_file, output_dir, backend, etc.).
    """
    output_path = Path(shared["output_dir"])
    output_path.mkdir(parents=True, exist_ok=True)
    raw_dir = output_path / "raw_output"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. Resolve adapter and backend
    adapter = get_adapter(tool_name)
    backend = shared["backend"]
    backend_kwargs = {}
    if backend == "docker" and shared.get("image"):
        backend_kwargs["default_image"] = shared["image"]
    if backend == "cwl":
        if shared.get("cwl_runner"):
            backend_kwargs["runner"] = shared["cwl_runner"]
        if shared.get("cwl_tool"):
            backend_kwargs["cwl_tool"] = shared["cwl_tool"]
    execution_backend = get_backend(backend, **backend_kwargs)

    # 2. Prepare input (FASTA → tool-native format, MSA conversion)
    msa_path = Path(shared["msa"]) if shared.get("msa") else None
    prepared = adapter.prepare_input(
        Path(shared["input_file"]), output_path, msa_path=msa_path
    )

    # 3. Build tool-specific command
    cmd = adapter.build_command(
        prepared,
        raw_dir,
        num_samples=shared["num_samples"],
        num_recycles=shared["num_recycles"],
        seed=shared.get("seed"),
        device=shared["device"],
        **extra_kwargs,
    )

    # 4. For docker backend: build volume mounts and rewrite host paths
    run_kwargs: dict = {
        "tool_name": adapter.tool_name,
        "gpu": adapter.requires_gpu and shared["device"] != "cpu",
    }

    if backend == "docker":
        data_dir = extra_kwargs.get("af2_data_dir")
        volumes, cmd = _docker_volumes_and_rewrite(
            cmd,
            input_path=prepared,
            output_dir=raw_dir,
            data_dir=data_dir,
        )
        run_kwargs["volumes"] = volumes

    if backend == "cwl":
        run_kwargs["output_dir"] = str(output_path)

    # 5. Execute prediction (or print command in debug mode)
    if shared.get("debug"):
        debug_lines = execution_backend.format_command(cmd, **run_kwargs)
        click.echo("\n".join(str(l) for l in debug_lines))
        return

    start = time.time()
    rc = execution_backend.run(cmd, **run_kwargs)
    elapsed = time.time() - start

    if rc != 0:
        click.echo(f"Prediction failed with exit code {rc}", err=True)
        sys.exit(rc)

    # 6. Normalize output
    adapter.normalize_output(raw_dir, output_path)

    params_dict = {
        "num_samples": shared["num_samples"],
        "num_recycles": shared["num_recycles"],
        "seed": shared.get("seed"),
        "device": shared["device"],
    }
    write_metadata_json(output_path, tool_name, params_dict, elapsed, __version__)

    click.echo(f"Prediction complete: {output_path}")


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__)
def main():
    """Predict protein structure using Boltz-2, Chai-1, AlphaFold 2, or ESMFold.

    Each subcommand dispatches to the appropriate prediction tool with
    automatic parameter mapping, input format conversion, and output
    normalization.
    """


# ---------------------------------------------------------------------------
# boltz subcommand
# ---------------------------------------------------------------------------

@main.command()
@shared_options
@optgroup.group("Boltz-2 options")
@optgroup.option("--sampling-steps", type=int, default=200, help="Number of diffusion sampling steps [default: 200]")
@optgroup.option("--use-msa-server", is_flag=True, default=False, help="Use remote MSA server")
@optgroup.option("--msa-server-url", default=None, help="Custom MSA server URL (implies --use-msa-server)")
@optgroup.option("--use-potentials", is_flag=True, default=False, help="Enable potential terms")
@backend_options
def boltz(input_file, sampling_steps, use_msa_server, msa_server_url, use_potentials, **shared):
    """Predict structure with Boltz-2 (diffusion-based, proteins/DNA/RNA/ligands)."""
    extra = {
        "sampling_steps": sampling_steps,
        "use_msa_server": use_msa_server or (msa_server_url is not None),
        "msa_server_url": msa_server_url,
        "boltz_use_potentials": use_potentials,
    }
    run_prediction("boltz", extra, input_file=input_file, **shared)


# ---------------------------------------------------------------------------
# chai subcommand
# ---------------------------------------------------------------------------

@main.command()
@shared_options
@optgroup.group("Chai-1 options")
@optgroup.option("--sampling-steps", type=int, default=200, help="Diffusion timesteps [default: 200]")
@optgroup.option("--use-msa-server", is_flag=True, default=False, help="Use remote MSA server")
@optgroup.option("--msa-server-url", default=None, help="Custom MSA server URL (implies --use-msa-server)")
@optgroup.option("--no-esm-embeddings", is_flag=True, default=False, help="Disable ESM2 language model embeddings")
@optgroup.option("--use-templates-server", is_flag=True, default=False, help="Use PDB template server")
@optgroup.option("--constraint-path", type=click.Path(), default=None, help="Constraint JSON file")
@optgroup.option("--template-hits-path", type=click.Path(), default=None, help="Pre-computed template hits file")
@optgroup.option("--num-trunk-samples", type=int, default=1, help="Trunk samples per prediction [default: 1]")
@optgroup.option("--recycle-msa-subsample", type=int, default=0, help="MSA subsample per recycle [default: 0 = all]")
@optgroup.option("--no-low-memory", is_flag=True, default=False, help="Disable low-memory mode")
@backend_options
def chai(input_file, sampling_steps, use_msa_server, msa_server_url,
         no_esm_embeddings, use_templates_server, constraint_path,
         template_hits_path, num_trunk_samples, recycle_msa_subsample,
         no_low_memory, **shared):
    """Predict structure with Chai-1 (diffusion-based protein prediction)."""
    extra = {
        "sampling_steps": sampling_steps,
        "use_msa_server": use_msa_server or (msa_server_url is not None),
        "msa_server_url": msa_server_url,
        "use_esm_embeddings": False if no_esm_embeddings else True,
        "use_templates_server": use_templates_server,
        "constraint_path": constraint_path,
        "template_hits_path": template_hits_path,
        "num_trunk_samples": num_trunk_samples,
        "recycle_msa_subsample": recycle_msa_subsample,
        "low_memory": False if no_low_memory else True,
    }
    run_prediction("chai", extra, input_file=input_file, **shared)


# ---------------------------------------------------------------------------
# alphafold subcommand
# ---------------------------------------------------------------------------

@main.command()
@shared_options
@optgroup.group("AlphaFold 2 options")
@optgroup.option("--af2-data-dir", type=click.Path(), required=True, help="AlphaFold database directory (~2TB)")
@optgroup.option("--af2-model-preset", default="monomer", help="Model preset (monomer, monomer_casp14, multimer)")
@optgroup.option("--af2-db-preset", default="reduced_dbs", help="DB preset (reduced_dbs, full_dbs)")
@optgroup.option("--af2-max-template-date", default="2022-01-01", help="Max template date (YYYY-MM-DD)")
@backend_options
def alphafold(input_file, af2_data_dir, af2_model_preset, af2_db_preset, af2_max_template_date, **shared):
    """Predict structure with AlphaFold 2 (MSA-based, high accuracy)."""
    extra = {
        "af2_data_dir": af2_data_dir,
        "af2_model_preset": af2_model_preset,
        "af2_db_preset": af2_db_preset,
        "af2_max_template_date": af2_max_template_date,
    }
    run_prediction("alphafold", extra, input_file=input_file, **shared)


# ---------------------------------------------------------------------------
# esmfold subcommand
# ---------------------------------------------------------------------------

@main.command()
@shared_options
@optgroup.group("ESMFold options")
@optgroup.option("--fp16", is_flag=True, default=False, help="Use half-precision (FP16) inference")
@optgroup.option("--chunk-size", type=int, default=None, help="Chunk size for long sequences")
@optgroup.option("--max-tokens-per-batch", type=int, default=None, help="Max tokens per batch")
@backend_options
def esmfold(input_file, fp16, chunk_size, max_tokens_per_batch, **shared):
    """Predict structure with ESMFold (single-sequence, no MSA needed, CPU-capable)."""
    extra = {
        "esm_fp16": fp16,
        "esm_chunk_size": chunk_size,
        "esm_max_tokens": max_tokens_per_batch,
    }
    run_prediction("esmfold", extra, input_file=input_file, **shared)


# ---------------------------------------------------------------------------
# auto subcommand
# ---------------------------------------------------------------------------

# Sensible defaults applied when auto-discovery selects a tool.
# These match the per-tool subcommand defaults so the user doesn't need
# to provide tool-specific flags.
_AUTO_DEFAULTS: dict[str, dict] = {
    "boltz": {},
    "chai": {},
    "alphafold": {
        "af2_data_dir": str(AF2_DEFAULT_DATA_DIR),
        "af2_model_preset": "monomer",
        "af2_db_preset": "reduced_dbs",
        "af2_max_template_date": "2022-01-01",
    },
    "esmfold": {},
}


@main.command()
@shared_options
@backend_options
def auto(input_file, **shared):
    """Auto-discover the best available tool and predict structure.

    Checks which prediction tools are installed and selects the best
    one based on input format, device, and availability.

    \b
    Priority order (GPU):  Boltz > Chai > AlphaFold > ESMFold
    Priority order (CPU):  ESMFold > Boltz > Chai > AlphaFold
    YAML input:            Boltz (only tool supporting YAML)
    """
    tool_name = discover_tool(Path(input_file), device=shared.get("device", "gpu"))
    click.echo(f"Auto-selected: {tool_name}")

    extra = dict(_AUTO_DEFAULTS.get(tool_name, {}))
    run_prediction(tool_name, extra, input_file=input_file, **shared)


if __name__ == "__main__":
    main()
