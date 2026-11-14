"""Standard-library HTTP server exposing RomBoot's build pipeline as a small
JSON API plus a single-page UI.  No third-party dependencies.

Design notes:
  * Uploads are sent as raw request bodies (no multipart parsing needed): the
    browser PUTs the file with an ``X-Filename`` header.
  * Live build logs stream as Server-Sent Events using manual HTTP/1.1 chunked
    encoding, which is reliable across browsers and proxies.
  * Flashing is deliberately absent -- the service hands back a downloadable
    image and the user writes it to an SD card with their own tool.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from romboot import __version__ as romboot_version
from romboot.builder import select_platform
from romboot.errors import RomBootError
from romboot.registry import PlatformRegistry, default_registry_path

from . import __version__ as web_version
from .jobs import BuildRequest, JobManager
from .settings import Settings

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_CHUNK = 1024 * 1024


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "").strip()
    cleaned = "".join(c if (c.isalnum() or c in "-_. ") else "-" for c in base).strip(". -")
    return (cleaned or "upload.bin")[:128]


def _known_targets(registry: PlatformRegistry):
    return {t for platform in registry.all() for t in platform.target_support}


class _Upload:
    __slots__ = ("id", "path", "name", "size", "sha256")

    def __init__(self, upload_id: str, path: Path, name: str, size: int, sha256: str) -> None:
        self.id = upload_id
        self.path = path
        self.name = name
        self.size = size
        self.sha256 = sha256

    def to_dict(self) -> dict:
        return {"upload_id": self.id, "name": self.name, "size": self.size, "sha256": self.sha256}


class RomBootServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, settings: Settings) -> None:
        settings.ensure_dirs()
        self.settings = settings
        self.registry = PlatformRegistry.load(default_registry_path())
        self.jobs = JobManager(settings)
        self.uploads: Dict[str, _Upload] = {}
        self.uploads_lock = threading.Lock()
        super().__init__((settings.host, settings.port), Handler)

    # upload bookkeeping ----------------------------------------------------
    def register_upload(self, upload: _Upload) -> None:
        with self.uploads_lock:
            self.uploads[upload.id] = upload

    def get_upload(self, upload_id: str) -> Optional[_Upload]:
        with self.uploads_lock:
            return self.uploads.get(upload_id)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "RomBoot/" + web_version

    # --- logging (quieter) -------------------------------------------------
    def log_message(self, fmt, *args):  # noqa: N802
        pass

    @property
    def settings(self) -> Settings:
        return self.server.settings  # type: ignore[attr-defined]

    # --- response helpers --------------------------------------------------
    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _authorized(self) -> bool:
        token = self.settings.token
        if not token:
            return True
        header = self.headers.get("X-RomBoot-Token")
        if header == token:
            return True
        query = parse_qs(urlparse(self.path).query)
        return query.get("token", [None])[0] == token

    # --- routing -----------------------------------------------------------
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            return self._serve_static("index.html")
        if not path.startswith("/api/"):
            return self._serve_static(path.lstrip("/"))
        if not self._authorized():
            return self._error(401, "missing or invalid token")
        if path == "/api/platforms":
            return self._api_platforms()
        if path == "/api/doctor":
            return self._api_doctor()
        if path == "/api/builds":
            return self._send_json({"builds": self.server.jobs.list()})  # type: ignore[attr-defined]
        if path.startswith("/api/builds/"):
            return self._route_build_get(path)
        return self._error(404, "not found")

    def do_PUT(self):  # noqa: N802
        if not self._authorized():
            return self._error(401, "missing or invalid token")
        if urlparse(self.path).path == "/api/uploads":
            return self._api_upload()
        return self._error(404, "not found")

    def do_POST(self):  # noqa: N802
        if not self._authorized():
            return self._error(401, "missing or invalid token")
        path = urlparse(self.path).path
        if path == "/api/inspect":
            return self._api_inspect()
        if path == "/api/builds":
            return self._api_build()
        if path.startswith("/api/builds/") and path.endswith("/cancel"):
            return self._api_cancel(path.split("/")[3])
        return self._error(404, "not found")

    def _route_build_get(self, path: str):
        parts = path.split("/")  # ['', 'api', 'builds', '<id>', maybe 'logs'|'artifact']
        job_id = parts[3] if len(parts) > 3 else ""
        job = self.server.jobs.get(job_id)  # type: ignore[attr-defined]
        if job is None:
            return self._error(404, "unknown build")
        if len(parts) == 4:
            return self._send_json(job.to_dict())
        tail = parts[4]
        if tail == "logs":
            query = parse_qs(urlparse(self.path).query)
            if query.get("stream", ["0"])[0] == "1":
                return self._stream_logs(job)
            return self._send_text(job.log_path.read_text(encoding="utf-8", errors="replace"))
        if tail == "artifact":
            return self._download_artifact(job)
        return self._error(404, "not found")

    # --- API handlers ------------------------------------------------------
    def _api_platforms(self):
        registry = self.server.registry  # type: ignore[attr-defined]
        platforms = []
        for platform in registry.all():
            platforms.append({
                "id": platform.id,
                "name": platform.name,
                "status": platform.status,
                "targets": list(platform.target_support),
                "extensions": list(platform.extensions),
                "core": platform.core,
                "bios_required": [b.id for b in platform.bios if b.required],
            })
        return self._send_json({
            "platforms": platforms,
            "targets": sorted(_known_targets(registry)),
        })

    def _api_doctor(self):
        s = self.settings
        registry = self.server.registry  # type: ignore[attr-defined]
        checks = [
            {"name": "romboot", "ok": True, "detail": romboot_version},
            {"name": "web", "ok": True, "detail": web_version},
            {"name": "platforms", "ok": bool(registry.all()),
             "detail": "{} registered".format(len(registry.all()))},
            {"name": "make", "ok": shutil.which("make") is not None,
             "detail": shutil.which("make") or "not found"},
            {"name": "zstd", "ok": shutil.which("zstd") is not None,
             "detail": shutil.which("zstd") or "not found"},
            {"name": "Buildroot source", "ok": s.buildroot_available(),
             "detail": str(s.buildroot_dir) if s.buildroot_dir else "unset"},
        ]
        try:
            usage = shutil.disk_usage(str(s.cache_dir if s.cache_dir.exists() else s.data_dir))
            free_gib = usage.free / (1024 ** 3)
            checks.append({"name": "free disk", "ok": free_gib > 15,
                           "detail": "{:.1f} GiB free".format(free_gib)})
        except OSError:
            pass
        essential_ok = all(c["ok"] for c in checks if c["name"] in ("make", "Buildroot source"))
        return self._send_json({"checks": checks, "ready_to_build": essential_ok})

    def _api_upload(self):
        length = self.headers.get("Content-Length")
        if length is None:
            return self._error(411, "Content-Length required for uploads")
        try:
            total = int(length)
        except ValueError:
            return self._error(400, "invalid Content-Length")
        if total > self.settings.max_upload_bytes:
            return self._error(413, "upload exceeds the configured size limit")
        name = _safe_filename(self.headers.get("X-Filename", "upload.bin"))
        upload_id = uuid.uuid4().hex
        dest_dir = self.settings.uploads_dir / upload_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        digest = hashlib.sha256()
        received = 0
        try:
            with dest.open("wb") as out:
                while received < total:
                    chunk = self.rfile.read(min(_CHUNK, total - received))
                    if not chunk:
                        break
                    received += len(chunk)
                    digest.update(chunk)
                    out.write(chunk)
        except OSError as exc:
            shutil.rmtree(dest_dir, ignore_errors=True)
            return self._error(500, "could not store upload: {}".format(exc))
        if received != total:
            shutil.rmtree(dest_dir, ignore_errors=True)
            return self._error(400, "upload truncated")
        upload = _Upload(upload_id, dest, name, received, digest.hexdigest())
        self.server.register_upload(upload)  # type: ignore[attr-defined]
        return self._send_json(upload.to_dict(), status=201)

    def _api_inspect(self):
        body = self._read_json()
        if body is None:
            return
        upload = self.server.get_upload(str(body.get("upload_id", "")))  # type: ignore[attr-defined]
        if upload is None:
            return self._error(404, "unknown upload_id")
        registry = self.server.registry  # type: ignore[attr-defined]
        try:
            platform, rom = select_platform(registry, upload.path, body.get("platform"))
        except RomBootError as exc:
            return self._error(400, str(exc))
        return self._send_json({
            "platform": platform.id,
            "platform_status": platform.status,
            "name": platform.name,
            "core": platform.core,
            "targets": list(platform.target_support),
            "rom_name": rom.display_name,
            "archive_member": rom.member,
            "size": rom.size,
            "sha256": rom.sha256,
            "required_bios": [b.id for b in platform.bios if b.required],
        })

    def _api_build(self):
        body = self._read_json()
        if body is None:
            return
        server = self.server  # type: ignore[attr-defined]
        upload = server.get_upload(str(body.get("upload_id", "")))
        if upload is None:
            return self._error(404, "unknown upload_id")
        target = str(body.get("target", "")).strip()
        if target not in _known_targets(server.registry):
            return self._error(400, "unknown target: {!r}".format(target))
        save_mode = str(body.get("save_mode", "persistent"))
        if save_mode not in ("persistent", "ephemeral", "disabled"):
            return self._error(400, "invalid save_mode")
        if not self.settings.buildroot_available():
            return self._error(409, "no Buildroot source configured; cannot build here")

        splash_path = None
        splash_id = body.get("splash_upload_id")
        if splash_id:
            splash = server.get_upload(str(splash_id))
            if splash is None:
                return self._error(404, "unknown splash_upload_id")
            splash_path = splash.path
        bios_paths = []
        for bios_id in body.get("bios_upload_ids", []) or []:
            bios = server.get_upload(str(bios_id))
            if bios is None:
                return self._error(404, "unknown bios upload id: {}".format(bios_id))
            bios_paths.append(bios.path)

        request = BuildRequest(
            rom_path=upload.path,
            rom_name=upload.name,
            target=target,
            platform=body.get("platform") or None,
            save_mode=save_mode,
            splash_path=splash_path,
            bios_paths=bios_paths,
        )
        job = server.jobs.submit(request)
        return self._send_json(job.to_dict(), status=201)

    def _api_cancel(self, job_id: str):
        ok = self.server.jobs.cancel(job_id)  # type: ignore[attr-defined]
        if not ok:
            return self._error(409, "build is not cancellable")
        return self._send_json({"status": "cancelling"})

    # --- streaming & downloads --------------------------------------------
    def _stream_logs(self, job):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        listener, replay, terminal = self.server.jobs.subscribe(job)  # type: ignore[attr-defined]
        try:
            for line in replay:
                self._sse(line)
            if terminal:
                self._sse_event("end", job.status)
                return
            while True:
                try:
                    item = listener.get(timeout=15)
                except Exception:
                    self._sse_comment("keepalive")
                    continue
                if not isinstance(item, str):
                    self._sse_event("end", job.status)  # also closes the chunk stream
                    break
                self._sse(item)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.server.jobs.unsubscribe(job, listener)  # type: ignore[attr-defined]

    def _download_artifact(self, job):
        query = parse_qs(urlparse(self.path).query)
        part = query.get("part", ["image"])[0]
        base = job.output
        target = {
            "image": base,
            "sha256": base.with_name(base.name + ".sha256"),
            "manifest": base.with_name(base.name + ".manifest.json"),
        }.get(part)
        if target is None or not target.is_file():
            return self._error(404, "artifact not available")
        size = target.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition",
                         'attachment; filename="{}"'.format(target.name))
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with target.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile, _CHUNK)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # --- static ------------------------------------------------------------
    def _serve_static(self, rel: str):
        rel = rel or "index.html"
        try:
            candidate = (_STATIC_DIR / rel).resolve()
            candidate.relative_to(_STATIC_DIR.resolve())
        except (ValueError, OSError):
            return self._error(403, "forbidden")
        if not candidate.is_file():
            return self._error(404, "not found")
        data = candidate.read_bytes()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css",
            ".js": "text/javascript",
            ".svg": "image/svg+xml",
        }.get(candidate.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_text(self, text: str):
        body = text.encode("utf-8", "replace")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- low-level helpers -------------------------------------------------
    def _read_json(self) -> Optional[dict]:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0 or length > 1_000_000:
            self._error(400, "expected a small JSON body")
            return None
        try:
            data = self.rfile.read(length)
            value = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeError):
            self._error(400, "invalid JSON body")
            return None
        if not isinstance(value, dict):
            self._error(400, "expected a JSON object")
            return None
        return value

    def _write_chunk(self, payload: bytes) -> None:
        self.wfile.write(b"%X\r\n" % len(payload) + payload + b"\r\n")
        self.wfile.flush()

    def _chunk_end(self) -> None:
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _sse(self, line: str) -> None:
        self._write_chunk(("data: " + line + "\n\n").encode("utf-8"))

    def _sse_event(self, event: str, data: str) -> None:
        self._write_chunk(("event: " + event + "\ndata: " + data + "\n\n").encode("utf-8"))
        self._chunk_end()

    def _sse_comment(self, text: str) -> None:
        self._write_chunk((": " + text + "\n\n").encode("utf-8"))


def make_server(settings: Optional[Settings] = None) -> RomBootServer:
    return RomBootServer(settings or Settings.from_env())
