"""Interactive, guided terminal UI for RomBoot.

Standard-library only (no third-party dependencies) so it runs on any stock
Python 3.9+. It is a thin, guided front-end over the same functions the
``romboot`` subcommands use: nothing here bypasses the security, staging or
flash safeguards -- it only makes them easier to reach in one place.

The screens are driven through an injectable reader/writer pair so the whole
flow can be exercised by unit tests without a real terminal.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .builder import prepare_build, select_platform
from .errors import RomBootError
from .image import run_buildroot, verify_artifact, verify_raw_image
from .manifest import verify_staging
from .registry import PlatformRegistry

Check = Tuple[str, bool, str, bool]  # name, ok, detail, essential


def host_checks(registry: PlatformRegistry, buildroot: Optional[Path]) -> List[Check]:
    """Return host-prerequisite checks shared by ``doctor`` and the wizard."""

    checks: List[Check] = [
        ("Python", sys.version_info >= (3, 9), sys.version.split()[0], True),
        (
            "platform registry",
            bool(registry.all()),
            "{} platforms".format(len(registry.all())),
            True,
        ),
    ]
    for command, essential in (("make", True), ("zstd", False)):
        location = shutil.which(command)
        checks.append((command, bool(location) or not essential, location or "not found", essential))
    checks.append(
        (
            "Buildroot source",
            buildroot is not None and (buildroot / "Makefile").is_file(),
            str(buildroot) if buildroot else "set BUILDROOT_DIR or pass --buildroot-dir",
            False,
        )
    )
    return checks


class _Quit(Exception):
    """Raised to unwind out of the wizard (explicit quit or end of input)."""


class _Console:
    """Minimal, testable text UI: line output plus prompted input."""

    def __init__(
        self,
        reader: Callable[[], str],
        writer: Callable[[str], object],
        flush: Callable[[], object],
        color: bool,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._flush = flush
        self.color = color

    # -- output ---------------------------------------------------------
    def emit(self, text: str = "") -> None:
        self._writer(text)
        self._flush()

    def line(self, text: str = "") -> None:
        self._writer(text + "\n")

    def rule(self) -> None:
        self.line(self.dim("  " + "─" * 58))

    def info(self, text: str) -> None:
        self.line("  " + text)

    def ok(self, text: str) -> None:
        self.line("  " + self.green("✓ ") + text)

    def warn(self, text: str) -> None:
        self.line("  " + self.yellow("! ") + text)

    def err(self, text: str) -> None:
        self.line("  " + self.red("✗ ") + text)

    # -- colour ---------------------------------------------------------
    def _wrap(self, code: str, text: str) -> str:
        return "\x1b[{}m{}\x1b[0m".format(code, text) if self.color else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def mark(self, ok: bool, essential: bool) -> str:
        token = ("ok" if ok else ("MISS" if essential else "warn")).ljust(5)
        if ok:
            return self.green(token)
        return self.red(token) if essential else self.yellow(token)

    # -- input ----------------------------------------------------------
    def ask(self, prompt: str, default: Optional[str] = None) -> str:
        suffix = " [{}]".format(default) if default else ""
        self.emit("  " + prompt + suffix + " " + self.cyan("> "))
        try:
            raw = self._reader()
        except (EOFError, StopIteration):
            raise _Quit()
        if raw is None:
            raise _Quit()
        value = raw.rstrip("\r\n")
        if not value and default is not None:
            return default
        return value

    def pause(self, message: str = "Press Enter to return to the menu…") -> None:
        self.emit("  " + self.dim(message))
        try:
            self._reader()
        except (EOFError, StopIteration):
            raise _Quit()

    def confirm(self, prompt: str, default: bool = False) -> bool:
        answer = self.ask(prompt + (" (Y/n)" if default else " (y/N)")).strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes")

    def ask_existing(self, prompt: str, kind: str = "any") -> Optional[Path]:
        """Prompt for a path that must exist; blank cancels (returns None).

        Tolerant of how terminals hand a path over: a stray trailing space,
        surrounding quotes, and macOS drag-and-drop backslash escapes
        (``\\ `` for a space, ``\\(`` for a paren) are all accepted.
        """

        while True:
            raw = self.ask(prompt + " (blank to cancel)")
            text = raw.strip()
            if not text:
                return None
            forms = [text]
            if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
                forms.append(text[1:-1])
            unescaped = text
            for token in (" ", "(", ")", "'", "&"):
                unescaped = unescaped.replace("\\" + token, token)
            forms.append(unescaped)
            candidates = [Path(form).expanduser() for form in forms]
            path = next((item for item in candidates if item.exists()), None)
            if path is None:
                self.warn("No such path: {}".format(candidates[0]))
                continue
            if kind == "file" and not path.is_file():
                self.warn("Not a file: {}".format(path))
                continue
            if kind == "dir" and not path.is_dir():
                self.warn("Not a directory: {}".format(path))
                continue
            return path

    def choose(self, prompt: str, choices: List[Tuple[str, str]], default_index: int = 0) -> str:
        for index, (_value, label) in enumerate(choices):
            marker = self.dim("  (default)") if index == default_index else ""
            self.line("     {}) {}{}".format(index + 1, label, marker))
        while True:
            raw = self.ask(prompt, default=str(default_index + 1))
            if raw.isdigit() and 1 <= int(raw) <= len(choices):
                return choices[int(raw) - 1][0]
            self.warn("Enter a number between 1 and {}.".format(len(choices)))


class _Context:
    def __init__(self, registry, console, buildroot, output_dir, jobs, project_root, env):
        self.registry = registry
        self.con = console
        self.buildroot = buildroot
        self.output_dir = output_dir
        self.jobs = jobs
        self.project_root = project_root
        self.env = env


def run_wizard(
    registry: PlatformRegistry,
    *,
    reader: Optional[Callable[[], str]] = None,
    writer: Optional[Callable[[str], object]] = None,
    buildroot: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    jobs: Optional[int] = None,
    project_root: Optional[Path] = None,
    env: Optional[dict] = None,
) -> int:
    """Run the interactive menu. Returns a process exit code."""

    env = env if env is not None else os.environ
    if reader is None:
        reader = input
    if writer is None:
        writer = sys.stdout.write
        flush = sys.stdout.flush
        color = _color_enabled(env)
    else:
        flush = lambda: None  # noqa: E731 - trivial no-op for injected writers
        color = False
    console = _Console(reader, writer, flush, color)

    if buildroot is None:
        raw = env.get("BUILDROOT_DIR")
        buildroot = Path(raw).expanduser() if raw else None
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    context = _Context(registry, console, buildroot, output_dir, jobs, project_root, env)
    try:
        _home_loop(context)
    except _Quit:
        console.line()
        console.info("Bye.")
    return 0


def _color_enabled(env: dict) -> bool:
    if env.get("NO_COLOR"):
        return False
    if env.get("TERM") == "dumb":
        return False
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


def _home_loop(ctx: "_Context") -> None:
    con = ctx.con
    actions = {
        "1": _screen_build,
        "2": _screen_inspect,
        "3": _screen_verify,
        "4": _screen_flash,
        "5": _screen_platforms,
        "6": _screen_doctor,
    }
    while True:
        _render_home(ctx)
        choice = con.ask("Choose", default="1").strip().lower()
        if choice in ("q", "quit", "exit"):
            raise _Quit()
        action = actions.get(choice)
        if action is None:
            con.warn("Pick a number 1-6, or q to quit.")
            continue
        try:
            action(ctx)
        except _Quit:
            raise
        except RomBootError as exc:
            con.err(str(exc))
        con.line()
        con.pause()


def _render_home(ctx: "_Context") -> None:
    con = ctx.con
    con.line()
    con.line("  " + con.bold("RomBoot") + con.dim("  —  build a one-game console image"))
    con.rule()
    checks = host_checks(ctx.registry, ctx.buildroot)
    parts = ["{} {}".format(name.split()[0], con.mark(ok, essential).strip()) for name, ok, _d, essential in checks]
    con.line("  " + con.dim("host: ") + "  ".join(parts))
    con.line()
    con.line("   {}) Build an appliance image   {}".format(con.bold("1"), con.dim("(pick console + ROM)")))
    con.line("   {}) Inspect a ROM".format(con.bold("2")))
    con.line("   {}) Verify an image".format(con.bold("3")))
    con.line("   {}) Flash an image to SD   {}".format(con.bold("4"), con.red("(destructive)")))
    con.line("   {}) List consoles & targets".format(con.bold("5")))
    con.line("   {}) Host check (doctor)".format(con.bold("6")))
    con.line("   {}) Quit".format(con.bold("q")))
    con.line()


def _header(con: "_Console", title: str) -> None:
    con.line()
    con.line("  " + con.bold(title))
    con.rule()


def _screen_platforms(ctx: "_Context") -> None:
    con = ctx.con
    _header(con, "Consoles & targets")
    con.line("  " + con.dim("{:<10} {:<18} {:<18} {}".format("ID", "STATUS", "TARGETS", "NAME")))
    for platform in ctx.registry.all():
        con.line(
            "  {:<10} {:<18} {:<18} {}".format(
                platform.id,
                platform.status,
                ",".join(platform.target_support) or "-",
                platform.name,
            )
        )
    con.line()
    con.info(con.dim("BIOS-free consoles need no extra files. 'registry-proof-only' entries are not buildable yet."))


def _screen_doctor(ctx: "_Context") -> None:
    con = ctx.con
    _header(con, "Host check")
    for name, ok, detail, essential in host_checks(ctx.registry, ctx.buildroot):
        con.line("  {:<20} {}  {}".format(name, con.mark(ok, essential), detail))
    con.line()
    con.info(con.dim("A clean check does not prove physical Raspberry Pi compatibility."))


def _resolve_platform(ctx: "_Context", rom: Path):
    """Auto-detect the console from the ROM, or let the user pick one."""

    con = ctx.con
    try:
        return select_platform(ctx.registry, rom, None)
    except RomBootError as exc:
        con.warn(str(exc))
        choices = [(p.id, "{:<10} {}".format(p.id, p.name)) for p in ctx.registry.all()]
        con.info("Choose the console manually:")
        chosen = con.choose("Console", choices)
        return select_platform(ctx.registry, rom, chosen)


def _screen_inspect(ctx: "_Context") -> None:
    con = ctx.con
    _header(con, "Inspect a ROM")
    rom = con.ask_existing("ROM file", "file")
    if rom is None:
        return
    platform, info = _resolve_platform(ctx, rom)
    con.ok("Detected: {} ({})".format(platform.name, platform.id))
    required_bios = ", ".join(item.id for item in platform.bios if item.required) or "none (BIOS-free)"
    fields = [
        ("platform", platform.id),
        ("core", platform.core),
        ("status", platform.status),
        ("file", info.display_name),
        ("archive member", info.member or "-"),
        ("size", "{} bytes".format(info.size)),
        ("sha256", info.sha256),
        ("required BIOS", required_bios),
    ]
    for key, value in fields:
        con.line("  {:<16} {}".format(key, value))


def _screen_verify(ctx: "_Context") -> None:
    con = ctx.con
    _header(con, "Verify an image or staging tree")
    path = con.ask_existing("Path to image / artifact / staging directory", "any")
    if path is None:
        return
    if path.is_dir():
        failures = verify_staging(path)
        if failures:
            con.err("Staging verification failed: " + "; ".join(failures))
        else:
            con.ok("Staging verification: ok")
        return
    kind = con.choose(
        "What kind of file is this?",
        [
            ("raw", "raw SD-card image (.img)"),
            ("artifact", "packaged RomBoot artifact (built with sidecars)"),
        ],
    )
    if kind == "raw":
        partitions = verify_raw_image(path)
        con.ok("Raw image verification: ok ({} partitions)".format(len(partitions)))
    else:
        verify_artifact(path)
        con.ok("Artifact verification: ok")


def _safe_stem(stem: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in stem)[:48]


def _unique_workspace(base: Path) -> Path:
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = base.parent / "{}-{}".format(base.name, index)
        if not candidate.exists():
            return candidate
        index += 1


def _screen_build(ctx: "_Context") -> None:
    con = ctx.con
    _header(con, "Build an appliance image")
    rom = con.ask_existing("ROM file", "file")
    if rom is None:
        return
    platform, info = _resolve_platform(ctx, rom)
    con.ok("Console: {} ({}, core {})".format(platform.name, platform.id, platform.core))
    if not platform.target_support:
        con.err("Platform {} has no supported targets yet.".format(platform.id))
        return

    target = con.choose("Target board", [(t, t) for t in platform.target_support])
    save_mode = con.choose(
        "Save behaviour",
        [
            ("persistent", "persistent  — writes battery saves to the data partition"),
            ("ephemeral", "ephemeral   — saves kept only until power-off"),
            ("disabled", "disabled    — no saving at all"),
        ],
    )
    splash: Optional[Path] = None
    if con.confirm("Add a custom boot splash PNG?", default=False):
        splash = con.ask_existing("Splash PNG", "file")

    default_workspace = ctx.project_root / "build" / (_safe_stem(rom.stem) + "-" + target)
    workspace = _unique_workspace(default_workspace)

    con.line()
    con.line("  " + con.bold("Summary"))
    con.line("  {:<10} {} ({})".format("console", platform.name, platform.id))
    con.line("  {:<10} {}".format("rom", info.display_name))
    con.line("  {:<10} {}".format("target", target))
    con.line("  {:<10} {}".format("saves", save_mode))
    con.line("  {:<10} {}".format("splash", str(splash) if splash else "default"))
    con.line("  {:<10} {}".format("workspace", workspace))
    con.line()
    if not con.confirm("Prepare the staging tree now?", default=True):
        con.info("Cancelled; nothing was written.")
        return

    prepared = prepare_build(
        registry=ctx.registry,
        rom_path=rom,
        target=target,
        workspace=workspace,
        requested_platform=platform.id,
        splash=splash,
        save_mode=save_mode,
    )
    con.ok("Prepared {} at {}".format(prepared.platform.id, prepared.directory))
    failures = verify_staging(prepared.directory)
    if failures:
        con.err("Staging verification failed: " + "; ".join(failures))
        return
    con.ok("Staging verification passed.")
    _offer_compile(ctx, prepared, target)


def _offer_compile(ctx: "_Context", prepared, target: str) -> None:
    con = ctx.con
    ready = ctx.buildroot is not None and (ctx.buildroot / "Makefile").is_file()
    if not ready:
        con.line()
        con.info("Staging is ready. Compiling the bootable SD image needs a Linux Buildroot checkout,")
        con.info("which this host does not have configured. Run the compile in your Buildroot/Docker")
        con.info("environment, for example:")
        con.line(
            "    "
            + con.cyan(
                "romboot build --rom <rom> --platform {} --target {} \\".format(
                    prepared.platform.id, target
                )
            )
        )
        con.line("    " + con.cyan("      --buildroot-dir <buildroot> --output <dir>"))
        con.info("or set BUILDROOT_DIR (or pass --buildroot-dir to `romboot ui`) and relaunch.")
        return

    if not con.confirm("Compile the bootable SD image now? This can take 20-60 minutes.", default=False):
        con.info("Skipped. Staging left at {}".format(prepared.directory))
        return

    output = ctx.output_dir
    if output is None:
        output = Path(
            con.ask("Output directory for the image", default=str(ctx.project_root / "artifacts"))
        ).expanduser()
    jobs = ctx.jobs or max(1, os.cpu_count() or 1)
    con.info("Building with {} job(s). This is long; Buildroot output follows.".format(jobs))
    built = run_buildroot(prepared, ctx.buildroot, ctx.project_root / "buildroot", output, jobs=jobs)
    con.ok("Image:    {}".format(built.path))
    con.ok("SHA-256:  {}".format(built.sha256))
    con.ok("Manifest: {}".format(built.manifest))
    con.info("Next: return to the menu and choose 'Flash an image to SD'.")


def _screen_flash(ctx: "_Context") -> None:
    con = ctx.con
    _header(con, con.red(con.bold("Flash an image to SD  —  DESTRUCTIVE")))
    con.warn("This ERASES the entire target device. Verify the device path before continuing.")
    from .flash import flash_image, inspect_device

    image = con.ask_existing("Image file to flash", "file")
    if image is None:
        return
    device_raw = con.ask("Target device under /dev (e.g. /dev/disk4 or /dev/sdX), blank to cancel")
    if not device_raw:
        return
    device_path = Path(device_raw)
    try:
        device = inspect_device(device_path, image)
    except RomBootError as exc:
        con.err(str(exc))
        lowered = str(exc).lower()
        if "manifest" in lowered or "sidecar" in lowered or "artifact" in lowered or "sha256" in lowered:
            con.info("Raw images without RomBoot manifest sidecars can't be flashed here. Use")
            con.info("Raspberry Pi Imager (custom image), or: sudo dd if=<image> of={} bs=4m".format(device_path))
        return

    con.line("  " + device.summary())
    con.info(con.dim("If writing later fails with a permission error, re-run the UI with sudo."))
    if con.confirm("Do a dry run first (no data written)?", default=True):
        con.ok("Dry run only: nothing was written.")
        if not con.confirm("Proceed to the REAL flash now?", default=False):
            con.info("Stopped. Nothing was written.")
            return
    expected = "ERASE {}".format(device.path)
    typed = con.ask("Type {!r} to erase and write".format(expected))
    if typed != expected:
        con.err("Confirmation did not match; nothing was written.")
        return
    flash_image(image, device)
    con.ok("Image written and first-block verification passed.")
