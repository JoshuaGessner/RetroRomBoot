import hashlib
import io
import json
import os
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

from romboot.bios import resolve_bios
from romboot.builder import prepare_build, select_platform
from romboot.config import load_effective_config
from romboot.errors import RomBootError
from romboot.flash import _write_stream, inspect_device
from romboot.image import _configure_custom_splash, _validate_buildroot_version, verify_raw_image
from romboot.layout import MIB, calculate_layout
from romboot.manifest import load_manifest, verify_staging
from romboot.models import BiosSpec, Platform
from romboot.registry import PlatformRegistry, default_registry_path
from romboot.security import inspect_rom


class TemporaryDirectoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_context.name)

    def tearDown(self):
        self.temp_context.cleanup()


class RegistryTests(unittest.TestCase):
    def test_loads_data_driven_platforms_and_aliases(self):
        registry = PlatformRegistry.load(default_registry_path())
        self.assertEqual(registry.get("famicom").id, "nes")
        self.assertEqual(registry.get("ps1").id, "psx")
        self.assertEqual([item.id for item in registry.detect_extension("game.nes")], ["nes"])

    def test_nes_supports_rpi4_and_rpizero2w_targets(self):
        registry = PlatformRegistry.load(default_registry_path())
        self.assertEqual(registry.get("nes").target_support, ("rpi4", "rpizero2w"))

    def test_duplicate_id_is_rejected(self):
        platform = _platform()
        with self.assertRaises(RomBootError):
            PlatformRegistry([platform, platform])

    def test_shared_alias_is_rejected(self):
        first = _platform()
        second = Platform(
            id="other",
            name="Other",
            aliases=("fc",),
            extensions=(".other",),
            emulator="retroarch",
            core="other",
            target_support=("rpi4",),
        )
        with self.assertRaises(RomBootError):
            PlatformRegistry([first, second])


class SecurityTests(TemporaryDirectoryTest):
    def test_plain_rom_hash_and_extension(self):
        rom = self.temp / "game.nes"
        rom.write_bytes(b"NES\x1a" + b"test")
        inspected = inspect_rom(rom, (".nes",))
        self.assertEqual(inspected.sha256, hashlib.sha256(rom.read_bytes()).hexdigest())
        self.assertIsNone(inspected.member)

    def test_archive_requires_exactly_one_matching_rom(self):
        archive = self.temp / "game.zip"
        with zipfile.ZipFile(str(archive), "w", zipfile.ZIP_STORED) as output:
            output.writestr("docs/readme.txt", "hello")
            output.writestr("games/game.nes", b"NES\x1a1234")
        inspected = inspect_rom(archive, (".nes",))
        self.assertEqual(inspected.member, "games/game.nes")
        self.assertEqual(inspected.display_name, "game.nes")

    def test_archive_path_traversal_is_rejected(self):
        archive = self.temp / "bad.zip"
        with zipfile.ZipFile(str(archive), "w", zipfile.ZIP_STORED) as output:
            output.writestr("../game.nes", b"NES\x1a")
        with self.assertRaises(RomBootError):
            inspect_rom(archive, (".nes",))

    def test_symlink_input_is_rejected(self):
        source = self.temp / "game.nes"
        source.write_bytes(b"NES\x1a")
        link = self.temp / "link.nes"
        link.symlink_to(source)
        with self.assertRaises(RomBootError):
            inspect_rom(link, (".nes",))


class BiosTests(TemporaryDirectoryTest):
    def test_required_bios_hash_is_validated(self):
        content = b"legal-test-bios"
        digest = hashlib.sha256(content).hexdigest()
        platform = _platform(
            bios=(
                BiosSpec(
                    id="test-bios",
                    filenames=("bios.bin",),
                    required=True,
                    sha256=(digest,),
                    size=len(content),
                ),
            )
        )
        bios = self.temp / "bios.bin"
        bios.write_bytes(content)
        result = resolve_bios(platform, [bios])
        self.assertEqual(result[0].sha256, digest)

    def test_missing_required_bios_is_rejected(self):
        platform = _platform(
            bios=(BiosSpec("required", ("missing.bin",), True),)
        )
        with self.assertRaises(RomBootError):
            resolve_bios(platform)


class BuilderTests(TemporaryDirectoryTest):
    def test_prepares_exactly_one_rom_and_verifiable_manifest(self):
        registry = PlatformRegistry.load(default_registry_path())
        rom = self.temp / "homebrew.nes"
        rom.write_bytes(b"NES\x1a" + bytes(range(32)))
        workspace = self.temp / "work"
        prepared = prepare_build(
            registry,
            rom,
            "rpi4",
            workspace,
            requested_platform="nes",
            save_mode="ephemeral",
        )
        self.assertEqual(verify_staging(prepared.directory), [])
        self.assertEqual(len(list((workspace / "rootfs" / "rom").iterdir())), 1)
        runtime = (workspace / "rootfs" / "etc" / "romboot" / "game.env").read_text()
        self.assertIn("ROMBOOT_ROM='/rom/game.nes'", runtime)
        self.assertIn("ROMBOOT_SAVE_MODE='ephemeral'", runtime)
        manifest = load_manifest(prepared.manifest)
        self.assertEqual(manifest["dependencies"]["buildroot"]["version"], "2025.02.16")
        self.assertEqual(manifest["verification"]["physical_hardware"], False)
        self.assertEqual(manifest["source_date_epoch"], 0)

    def test_custom_splash_must_be_png(self):
        registry = PlatformRegistry.load(default_registry_path())
        rom = self.temp / "game.nes"
        rom.write_bytes(b"NES\x1a")
        splash = self.temp / "splash.jpg"
        splash.write_bytes(b"not-an-image")
        with self.assertRaises(RomBootError):
            prepare_build(
                registry,
                rom,
                "rpi4",
                self.temp / "splash-work",
                splash=splash,
            )

    def test_custom_splash_dimensions_are_bounded_before_staging(self):
        registry = PlatformRegistry.load(default_registry_path())
        rom = self.temp / "game.nes"
        rom.write_bytes(b"NES\x1a")
        splash = self.temp / "splash.png"
        splash.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 5000, 100)
        )
        workspace = self.temp / "oversized-splash-work"
        with self.assertRaises(RomBootError):
            prepare_build(registry, rom, "rpi4", workspace, splash=splash)
        self.assertFalse(workspace.exists())

    def test_unsupported_target_is_rejected_before_staging(self):
        registry = PlatformRegistry.load(default_registry_path())
        rom = self.temp / "game.nes"
        rom.write_bytes(b"NES\x1a")
        with self.assertRaises(RomBootError):
            prepare_build(registry, rom, "rpi5", self.temp / "work")


class ConfigTests(TemporaryDirectoryTest):
    def test_precedence_is_builtin_user_project_cli(self):
        user = self.temp / "user.json"
        project = self.temp / "project.json"
        user.write_text(json.dumps({"schema_version": 1, "jobs": 2, "target": "user"}))
        project.write_text(json.dumps({"schema_version": 1, "target": "project"}))
        result = load_effective_config(project, user, {"target": "cli"})
        self.assertEqual(result["target"], "cli")
        self.assertEqual(result["jobs"], 2)

    def test_unknown_field_is_rejected(self):
        config = self.temp / "config.json"
        config.write_text(json.dumps({"schema_version": 1, "surprise": True}))
        with self.assertRaises(RomBootError):
            load_effective_config(config, self.temp / "absent")


class FlashSafetyTests(TemporaryDirectoryTest):
    def test_rejects_non_device_path_before_device_inspection(self):
        with patch("romboot.flash.verify_artifact"):
            with self.assertRaises(RomBootError):
                inspect_device(self.temp / "not-a-device", self.temp / "image.img")

    def test_stream_writer_records_verification_prefix(self):
        payload = b"romboot-test-payload"
        target = self.temp / "device"
        target.write_bytes(bytes(len(payload) * 2))
        first = _write_stream(io.BytesIO(payload), target)
        self.assertEqual(first, payload)
        self.assertEqual(target.read_bytes()[: len(payload)], payload)

class LayoutTests(unittest.TestCase):
    def test_layout_rounds_and_adds_headroom(self):
        layout = calculate_layout(MIB + 1, 2 * MIB, 0)
        self.assertEqual(layout.boot_mib, 10)
        self.assertEqual(layout.root_mib, 18)
        self.assertEqual(layout.data_mib, 32)
        self.assertEqual(layout.total_mib, 68)

    def test_negative_size_is_rejected(self):
        with self.assertRaises(RomBootError):
            calculate_layout(-1, 0, 0)


class BuildrootConfigurationTests(TemporaryDirectoryTest):
    def test_requires_the_pinned_buildroot_version(self):
        source = self.temp / "buildroot"
        source.mkdir()
        makefile = source / "Makefile"
        makefile.write_text("export BR2_VERSION := wrong\n")
        with self.assertRaises(RomBootError):
            _validate_buildroot_version(source)
        makefile.write_text("export BR2_VERSION := 2025.02.16\n")
        _validate_buildroot_version(source)

    def test_custom_splash_updates_generated_buildroot_config(self):
        registry = PlatformRegistry.load(default_registry_path())
        rom = self.temp / "game.nes"
        rom.write_bytes(b"NES\x1a")
        splash = self.temp / "splash.png"
        splash.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 320, 180))
        prepared = prepare_build(
            registry,
            rom,
            "rpi4",
            self.temp / "work",
            splash=splash,
        )
        output = self.temp / "output"
        output.mkdir()
        config = output / ".config"
        config.write_text('BR2_PACKAGE_PSPLASH_IMAGE="generic.png"\n')
        _configure_custom_splash(output, prepared)
        self.assertIn(str((prepared.directory / "rootfs/usr/share/romboot/splash.png").resolve()), config.read_text())


class ImageVerificationTests(TemporaryDirectoryTest):
    def test_valid_three_partition_image(self):
        image = self.temp / "card.img"
        _write_test_image(image)
        partitions = verify_raw_image(image)
        self.assertEqual([item.type_code for item in partitions], [0x0C, 0x83, 0x83])

    def test_invalid_mbr_is_rejected(self):
        image = self.temp / "bad.img"
        image.write_bytes(bytes(4096))
        with self.assertRaises(RomBootError):
            verify_raw_image(image)


def _platform(bios=()):
    return Platform(
        id="nes",
        name="NES",
        aliases=("fc",),
        extensions=(".nes",),
        emulator="retroarch",
        core="fceumm",
        target_support=("rpi4",),
        bios=bios,
        settings={
            "emulator_path": "/usr/bin/retroarch",
            "core_path": "/usr/lib/libretro/fceumm_libretro.so",
            "retroarch_config": "/etc/retroarch.cfg",
        },
    )


def _write_test_image(path: Path):
    sectors = 40
    payload = bytearray(sectors * 512)
    entries = [(0x0C, 1, 10), (0x83, 11, 10), (0x83, 21, 10)]
    for index, (type_code, start, count) in enumerate(entries):
        offset = 446 + index * 16
        payload[offset + 4] = type_code
        struct.pack_into("<II", payload, offset + 8, start, count)
    payload[510:512] = b"\x55\xaa"
    payload[1 * 512 + 82 : 1 * 512 + 90] = b"FAT32   "
    payload[11 * 512 : 11 * 512 + 4] = b"hsqs"
    payload[21 * 512 + 1024 + 56 : 21 * 512 + 1024 + 58] = b"\x53\xef"
    path.write_bytes(payload)


if __name__ == "__main__":
    unittest.main()
