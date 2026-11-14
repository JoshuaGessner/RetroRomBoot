import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from romboot.cli import main
from tests.test_core import _write_test_image


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_context.name)
        self.rom = self.temp / "homebrew.nes"
        self.rom.write_bytes(b"NES\x1a" + bytes(range(64)))

    def tearDown(self):
        self.temp_context.cleanup()

    def run_cli(self, arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_platforms_lists_implemented_and_registry_proof_entries(self):
        status, output, error = self.run_cli(["platforms"])
        self.assertEqual(status, 0, error)
        self.assertIn("nes", output)
        self.assertIn("psx", output)

    def test_inspect_detects_nes_and_hashes_content(self):
        status, output, error = self.run_cli(["inspect", str(self.rom)])
        self.assertEqual(status, 0, error)
        self.assertIn('"platform": "nes"', output)
        self.assertIn('"sha256":', output)

    def test_prepare_only_and_verify(self):
        workspace = self.temp / "workspace"
        status, output, error = self.run_cli(
            [
                "build",
                "--rom",
                str(self.rom),
                "--target",
                "rpi4",
                "--workspace",
                str(workspace),
                "--prepare-only",
            ]
        )
        self.assertEqual(status, 0, error)
        self.assertIn("Staging verification: ok", output)
        status, output, error = self.run_cli(["verify", str(workspace)])
        self.assertEqual(status, 0, error)
        self.assertIn("Staging verification: ok", output)

    def test_verify_raw_image(self):
        image = self.temp / "card.img"
        _write_test_image(image)
        status, output, error = self.run_cli(["verify", "--raw", str(image)])
        self.assertEqual(status, 0, error)
        self.assertIn("Raw image verification: ok (3 partitions)", output)

    def test_wrong_extension_returns_actionable_error(self):
        wrong = self.temp / "game.bin"
        wrong.write_bytes(b"not a registered format")
        status, output, error = self.run_cli(["inspect", str(wrong)])
        self.assertEqual(status, 2)
        self.assertIn("not accepted", error)


if __name__ == "__main__":
    unittest.main()
