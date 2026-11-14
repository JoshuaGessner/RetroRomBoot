"""Guards for the appliance controller configuration.

These are static checks over the Buildroot overlay + autoconfig package, not
runtime tests: they cannot prove a physical pad works, but they lock in the
invariants that made the D-pad regress once already (a duplicate autoconfig
profile shadowing the correct one, and the analog-stick -> D-pad fallback).
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RETROARCH_CFG = (
    REPO_ROOT
    / "buildroot/board/romboot/common/rootfs-overlay/etc/retroarch.cfg"
)
AUTOCONFIG_MK = (
    REPO_ROOT
    / "buildroot/package/romboot-joypad-autoconfig/romboot-joypad-autoconfig.mk"
)


def _parse_cfg(path: Path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"')
    return values


class ControllerConfigTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(RETROARCH_CFG.is_file(), RETROARCH_CFG)
        self.assertTrue(AUTOCONFIG_MK.is_file(), AUTOCONFIG_MK)
        self.cfg = _parse_cfg(RETROARCH_CFG)
        self.mk = AUTOCONFIG_MK.read_text(encoding="utf-8")

    def test_autodetect_and_autoconfig_dir(self):
        self.assertEqual(self.cfg.get("input_autodetect_enable"), "true")
        self.assertEqual(self.cfg.get("input_driver"), "udev")
        self.assertEqual(
            self.cfg.get("joypad_autoconfig_dir"),
            "/usr/share/libretro/autoconfig/udev",
        )

    def test_analog_stick_also_drives_dpad(self):
        # The general hardening: a pad reporting movement on an analog stick must
        # still move the character, so player 1 (and 2) map the left stick -> D-pad.
        self.assertEqual(self.cfg.get("input_player1_analog_dpad_mode"), "1")
        self.assertEqual(self.cfg.get("input_player2_analog_dpad_mode"), "1")

    def test_broken_duplicate_profile_is_removed(self):
        # The autoconfig package must delete the profile that maps the shared
        # DragonRise VID/PID to an analog stick (leaving the D-pad unbound).
        self.assertIn("Qnix_SNES_Replica.cfg", self.mk)
        self.assertRegex(self.mk, r"rm\s+-f[^\n]*Qnix_SNES_Replica\.cfg")

    def test_autoconfig_dir_is_consistent_between_cfg_and_package(self):
        # The directory RetroArch scans must be exactly where the package installs
        # the udev profiles, or autoconfig silently matches nothing.
        self.assertRegex(
            self.mk,
            r"cp\s+-rf\s+\$\(@D\)/udev\s+\$\(TARGET_DIR\)/usr/share/libretro/autoconfig/",
        )
        installed_dir = "/usr/share/libretro/autoconfig/udev"
        self.assertEqual(self.cfg.get("joypad_autoconfig_dir"), installed_dir)
        self.assertIn(
            "$(TARGET_DIR)" + installed_dir + "/Qnix_SNES_Replica.cfg",
            self.mk,
        )


if __name__ == "__main__":
    unittest.main()
