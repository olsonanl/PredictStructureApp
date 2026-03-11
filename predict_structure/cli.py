"""Unified CLI entry point for protein structure prediction.

Usage:
    predict-structure <tool> <input> [OPTIONS]

Examples:
    predict-structure boltz input.fasta -o output/ --num-samples 5
    predict-structure esmfold input.fasta -o output/ --num-recycles 4
    predict-structure chai input.fasta -o output/ --msa alignment.a3m
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import click

from predict_structure import __version__
from predict_structure.adapters import get_adapter
from predict_structure.backends import get_backend
from predict_structure.normalizers import write_metadata_json


TOOLS = ["boltz", "chai", "alphafold", "esmfold"]


@click.command()
@click.argument("tool", type=click.Choice(TOOLS, case_sensitive=False))
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-o", "--output-dir", type=click.Path(), required=True, help="Output directory")
@click.option("--num-samples", "-n", type=int, default=1, help="Number of structure samples")
@click.option("--num-recycles", type=int, default=3, help="Recycling iterations")
@click.option("--seed", type=int, default=None, help="Random seed")
@click.option("--device", type=click.Choice(["gpu", "cpu"]), default="gpu", help="Compute device")
@click.option("--msa", type=click.Path(), default=None, help="MSA file (.a3m, .sto, .pqt)")
@click.option("--output-format", type=click.Choice(["pdb", "mmcif"]), default="pdb")
@click.option(
    "--backend",
    type=click.Choice(["docker", "subprocess"]),
    default="subprocess",
    help="Execution backend",
)
@click.option("--image", default=None, help="Override Docker image for the tool")
@click.option("--sampling-steps", type=int, default=200, help="Sampling steps (Boltz/Chai)")
@click.option("--use-msa-server", is_flag=True, default=False, help="Use MSA server (Boltz/Chai)")
@click.option("--af2-data-dir", type=click.Path(), default=None, help="AlphaFold database dir")
@click.option("--af2-model-preset", default="monomer", help="AlphaFold model preset")
@click.option("--af2-db-preset", default="reduced_dbs", help="AlphaFold DB preset")
def main(
    tool,
    input_file,
    output_dir,
    num_samples,
    num_recycles,
    seed,
    device,
    msa,
    output_format,
    backend,
    image,
    sampling_steps,
    use_msa_server,
    af2_data_dir,
    af2_model_preset,
    af2_db_preset,
):
    """Predict protein structure using TOOL on INPUT_FILE.

    Dispatches to the appropriate prediction tool (Boltz-2, Chai-1,
    AlphaFold 2, or ESMFold) with automatic parameter mapping,
    input format conversion, and output normalization.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    raw_dir = output_path / "raw_output"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. Resolve adapter and backend
    adapter = get_adapter(tool)
    backend_kwargs = {}
    if image:
        backend_kwargs["default_image"] = image
    execution_backend = get_backend(backend, **backend_kwargs)

    # 2. Prepare input (FASTA → tool-native format, MSA conversion)
    msa_path = Path(msa) if msa else None
    prepared = adapter.prepare_input(
        Path(input_file), output_path, msa_path=msa_path
    )

    # 3. Build tool-specific command
    extra_kwargs = {
        "sampling_steps": sampling_steps,
        "use_msa_server": use_msa_server,
        "af2_data_dir": af2_data_dir,
        "af2_model_preset": af2_model_preset,
        "af2_db_preset": af2_db_preset,
    }
    cmd = adapter.build_command(
        prepared,
        raw_dir,
        num_samples=num_samples,
        num_recycles=num_recycles,
        seed=seed,
        device=device,
        **extra_kwargs,
    )

    # 4. Execute prediction
    start = time.time()
    rc = execution_backend.run(
        cmd,
        tool_name=adapter.tool_name,
        gpu=adapter.requires_gpu and device != "cpu",
    )
    elapsed = time.time() - start

    if rc != 0:
        click.echo(f"Prediction failed with exit code {rc}", err=True)
        sys.exit(rc)

    # 5. Normalize output
    adapter.normalize_output(raw_dir, output_path)

    params_dict = {
        "num_samples": num_samples,
        "num_recycles": num_recycles,
        "seed": seed,
        "device": device,
    }
    write_metadata_json(output_path, tool, params_dict, elapsed, __version__)

    click.echo(f"Prediction complete: {output_path}")


if __name__ == "__main__":
    main()
