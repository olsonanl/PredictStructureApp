"""Tests for CLI argument parsing and error handling."""

from click.testing import CliRunner
from predict_structure.cli import main


class TestCLIGroup:
    """Test the top-level click group."""

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Predict protein structure" in result.output
        assert "boltz" in result.output
        assert "chai" in result.output
        assert "alphafold" in result.output
        assert "esmfold" in result.output

    def test_unknown_subcommand(self):
        runner = CliRunner()
        result = runner.invoke(main, ["nonexistent", "input.fasta", "-o", "/tmp/out"])
        assert result.exit_code != 0

    def test_no_subcommand(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert "boltz" in result.output


class TestBoltzSubcommand:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", "--help"])
        assert result.exit_code == 0
        assert "--output-dir" in result.output
        assert "--num-samples" in result.output
        assert "--backend" in result.output
        assert "--debug" in result.output
        # Boltz-specific
        assert "--sampling-steps" in result.output
        assert "--use-msa-server" in result.output
        assert "--use-potentials" in result.output

    def test_help_does_not_show_other_tool_options(self):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", "--help"])
        assert "--fp16" not in result.output
        assert "--af2-data-dir" not in result.output
        assert "--chunk-size" not in result.output

    def test_missing_output_dir(self, sample_fasta):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", str(sample_fasta)])
        assert result.exit_code != 0

    def test_missing_input_file(self):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", "/nonexistent/file.fasta", "-o", "/tmp/out"])
        assert result.exit_code != 0

    def test_debug_prints_command(self, sample_fasta, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "boltz", str(sample_fasta), "-o", str(tmp_path / "out"), "--debug",
        ])
        assert result.exit_code == 0
        assert "boltz predict" in result.output
        assert "--diffusion_samples" in result.output

    def test_debug_with_use_potentials(self, sample_fasta, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "boltz", str(sample_fasta), "-o", str(tmp_path / "out"),
            "--debug", "--use-potentials",
        ])
        assert result.exit_code == 0
        assert "--use_potentials" in result.output


class TestChaiSubcommand:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["chai", "--help"])
        assert result.exit_code == 0
        assert "--sampling-steps" in result.output
        assert "--use-msa-server" in result.output
        # Should not show other tool options
        assert "--fp16" not in result.output
        assert "--af2-data-dir" not in result.output

    def test_debug_prints_command(self, sample_fasta, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "chai", str(sample_fasta), "-o", str(tmp_path / "out"), "--debug",
        ])
        assert result.exit_code == 0
        assert "chai-lab fold" in result.output


class TestAlphaFoldSubcommand:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["alphafold", "--help"])
        assert result.exit_code == 0
        assert "--af2-data-dir" in result.output
        assert "--af2-model-preset" in result.output
        assert "--af2-db-preset" in result.output
        assert "--af2-max-template-date" in result.output
        # Should not show other tool options
        assert "--fp16" not in result.output
        assert "--use-potentials" not in result.output

    def test_requires_af2_data_dir(self, sample_fasta, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "alphafold", str(sample_fasta), "-o", str(tmp_path / "out"), "--debug",
        ])
        assert result.exit_code != 0  # --af2-data-dir is required

    def test_debug_prints_command(self, sample_fasta, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "alphafold", str(sample_fasta), "-o", str(tmp_path / "out"),
            "--af2-data-dir", "/data/alphafold", "--debug",
        ])
        assert result.exit_code == 0
        assert "run_alphafold.py" in result.output
        assert "--data_dir" in result.output


class TestESMFoldSubcommand:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["esmfold", "--help"])
        assert result.exit_code == 0
        assert "--fp16" in result.output
        assert "--chunk-size" in result.output
        assert "--max-tokens-per-batch" in result.output
        # Should not show other tool options
        assert "--use-potentials" not in result.output
        assert "--af2-data-dir" not in result.output
        assert "--sampling-steps" not in result.output

    def test_debug_prints_command(self, sample_fasta, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "esmfold", str(sample_fasta), "-o", str(tmp_path / "out"), "--debug",
        ])
        assert result.exit_code == 0
        assert "esm-fold-hf" in result.output

    def test_debug_with_fp16(self, sample_fasta, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "esmfold", str(sample_fasta), "-o", str(tmp_path / "out"),
            "--debug", "--fp16",
        ])
        assert result.exit_code == 0
        assert "--fp16" in result.output

    def test_debug_with_chunk_size(self, sample_fasta, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "esmfold", str(sample_fasta), "-o", str(tmp_path / "out"),
            "--debug", "--chunk-size", "64",
        ])
        assert result.exit_code == 0
        assert "--chunk-size 64" in result.output


class TestSharedOptions:
    """Test that shared options work across subcommands."""

    def test_backend_choices_shown(self):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", "--help"])
        assert "docker" in result.output
        assert "subprocess" in result.output
        assert "cwl" in result.output

    def test_cwl_options_shown(self):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", "--help"])
        assert "--cwl-runner" in result.output
        assert "--cwl-tool" in result.output

    def test_image_option_shown(self):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", "--help"])
        assert "--image" in result.output


class TestBackendRegistry:
    def test_get_backend_subprocess(self):
        from predict_structure.backends import get_backend
        from predict_structure.backends.subprocess import SubprocessBackend

        backend = get_backend("subprocess")
        assert isinstance(backend, SubprocessBackend)

    def test_get_backend_docker(self):
        from predict_structure.backends import get_backend
        from predict_structure.backends.docker import DockerBackend

        backend = get_backend("docker")
        assert isinstance(backend, DockerBackend)

    def test_get_backend_docker_with_image(self):
        from predict_structure.backends import get_backend
        from predict_structure.backends.docker import DockerBackend

        backend = get_backend("docker", default_image="my/image:latest")
        assert isinstance(backend, DockerBackend)
        assert backend._default_image == "my/image:latest"

    def test_get_backend_cwl(self):
        from predict_structure.backends import get_backend
        from predict_structure.backends.cwl import CWLBackend

        backend = get_backend("cwl")
        assert isinstance(backend, CWLBackend)

    def test_get_backend_cwl_with_runner(self):
        from predict_structure.backends import get_backend

        backend = get_backend("cwl", runner="toil-cwl-runner")
        assert backend._runner == "toil-cwl-runner"

    def test_get_backend_unknown(self):
        from predict_structure.backends import get_backend

        import pytest
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend("nonexistent")
