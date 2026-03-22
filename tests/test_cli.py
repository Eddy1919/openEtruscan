"""Tests for the CLI interface."""

from click.testing import CliRunner

from openetruscan.cli import main


class TestCLI:
    """Test CLI commands."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_normalize_command(self):
        result = self.runner.invoke(main, ["normalize", "LARTHAL"])
        assert result.exit_code == 0
        assert "canonical" in result.output

    def test_normalize_json_output(self):
        result = self.runner.invoke(main, ["normalize", "-j", "Larθal"])
        assert result.exit_code == 0
        assert '"canonical"' in result.output

    def test_convert_to_old_italic(self):
        result = self.runner.invoke(main, ["convert", "--to", "old_italic", "Larθal"])
        assert result.exit_code == 0

    def test_convert_to_phonetic(self):
        result = self.runner.invoke(main, ["convert", "--to", "phonetic", "Larθal"])
        assert result.exit_code == 0
        assert "tʰ" in result.output

    def test_list_adapters(self):
        result = self.runner.invoke(main, ["adapters"])
        assert result.exit_code == 0
        assert "etruscan" in result.output

    def test_validate_nonexistent_file(self):
        result = self.runner.invoke(main, ["validate", "/tmp/nonexistent_file.txt"])
        # click.Path(exists=True) will catch this
        assert result.exit_code != 0

    def test_version(self):
        result = self.runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
