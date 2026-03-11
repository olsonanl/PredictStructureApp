"""Tests for CLI argument parsing and error handling."""

from click.testing import CliRunner
from predict_structure.cli import main


class TestCLI:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Predict protein structure" in result.output
        assert "boltz" in result.output
        assert "--output-dir" in result.output
        assert "--backend" in result.output
        assert "--num-samples" in result.output
        assert "--use-msa-server" in result.output

    def test_unknown_tool(self):
        runner = CliRunner()
        result = runner.invoke(main, ["nonexistent", "input.fasta", "-o", "/tmp/out"])
        assert result.exit_code != 0

    def test_missing_output_dir(self, sample_fasta):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", str(sample_fasta)])
        assert result.exit_code != 0

    def test_missing_input_file(self):
        runner = CliRunner()
        result = runner.invoke(main, ["boltz", "/nonexistent/file.fasta", "-o", "/tmp/out"])
        assert result.exit_code != 0


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

    def test_get_backend_unknown(self):
        from predict_structure.backends import get_backend

        import pytest
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend("nonexistent")
