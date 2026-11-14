import tempfile
import unittest
from pathlib import Path

from romboot.registry import PlatformRegistry, default_registry_path
from romboot.wizard import run_wizard
from tests.test_core import _write_test_image


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.registry = PlatformRegistry.load(default_registry_path())
        self.temp_context = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_context.name)
        self.rom = self.temp / "homebrew.nes"
        self.rom.write_bytes(b"NES\x1a" + bytes(range(64)))

    def tearDown(self):
        self.temp_context.cleanup()

    def drive(self, inputs, **kwargs):
        """Run the wizard against a scripted list of inputs; return its output."""

        outputs = []
        iterator = iter(inputs)
        status = run_wizard(
            self.registry,
            reader=lambda: next(iterator),
            writer=outputs.append,
            project_root=self.temp,
            env={},
            **kwargs,
        )
        return status, "".join(outputs)

    def test_menu_renders_and_quits_cleanly(self):
        status, output = self.drive(["q"])
        self.assertEqual(status, 0)
        self.assertIn("RomBoot", output)
        self.assertIn("Build an appliance image", output)
        self.assertIn("Bye.", output)

    def test_eof_quits_without_error(self):
        status, output = self.drive([])
        self.assertEqual(status, 0)
        self.assertIn("RomBoot", output)

    def test_lists_consoles(self):
        status, output = self.drive(["5", "", "q"])
        self.assertEqual(status, 0)
        self.assertIn("Consoles & targets", output)
        self.assertIn("snes", output)
        self.assertIn("nes", output)

    def test_inspect_detects_platform(self):
        status, output = self.drive(["2", str(self.rom), "", "q"])
        self.assertEqual(status, 0)
        self.assertIn("Detected:", output)
        self.assertIn("nes", output)
        self.assertIn("sha256", output)

    def test_build_prepares_staging_without_buildroot(self):
        # 1=build, rom, target(default), save(default), splash=no, prepare=yes, pause, quit
        status, output = self.drive(
            ["1", str(self.rom), "", "", "", "", "", "q"]
        )
        self.assertEqual(status, 0)
        self.assertIn("Prepared nes", output)
        self.assertIn("Staging verification passed", output)
        # No Buildroot configured -> the wizard explains the compile step, does not run it.
        self.assertIn("Buildroot", output)
        self.assertTrue(any((self.temp / "build").glob("*")))

    def test_verify_raw_image(self):
        image = self.temp / "card.img"
        _write_test_image(image)
        status, output = self.drive(["3", str(image), "1", "", "q"])
        self.assertEqual(status, 0)
        self.assertIn("Raw image verification: ok", output)

    def test_flash_screen_warns_and_cancels_on_blank_device(self):
        dummy = self.temp / "some.img"
        dummy.write_bytes(b"\x00" * 16)
        status, output = self.drive(["4", str(dummy), "", "", "q"])
        self.assertEqual(status, 0)
        self.assertIn("DESTRUCTIVE", output)

    def test_path_prompt_tolerates_escaping_and_trailing_space(self):
        spaced = self.temp / "My Game (USA).nes"
        spaced.write_bytes(b"NES\x1a" + bytes(range(16)))
        # Emulate a macOS drag-and-drop path (backslash-escaped) with a stray
        # trailing space, which is exactly what tripped up manual entry.
        escaped = (
            str(spaced).replace(" ", "\\ ").replace("(", "\\(").replace(")", "\\)") + " "
        )
        status, output = self.drive(["2", escaped, "", "q"])
        self.assertEqual(status, 0)
        self.assertIn("Detected:", output)
        self.assertNotIn("No such path", output)


if __name__ == "__main__":
    unittest.main()
