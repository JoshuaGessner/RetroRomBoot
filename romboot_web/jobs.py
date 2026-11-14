"""Build-job manager: a single background worker runs one image build at a
time as a subprocess, streaming its output to a log file and to live
subscribers (for Server-Sent Events).  Builds are serialized so a warm,
per-target Buildroot cache is never touched by two builds at once.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .settings import Settings

_DONE = object()  # sentinel pushed to subscribers when a job reaches a terminal state
_TERMINAL = {"succeeded", "failed", "cancelled"}


def _iso(epoch: Optional[float]) -> Optional[str]:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in stem).strip("-")
    return (cleaned or "image")[:48]


@dataclass
class BuildRequest:
    rom_path: Path
    rom_name: str
    target: str
    platform: Optional[str] = None
    save_mode: str = "persistent"
    splash_path: Optional[Path] = None
    bios_paths: List[Path] = field(default_factory=list)


class Job:
    def __init__(self, job_id: str, request: BuildRequest, workspace: Path,
                 output: Path, log_path: Path) -> None:
        self.id = job_id
        self.request = request
        self.workspace = workspace
        self.output = output
        self.log_path = log_path
        self.status = "queued"
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.returncode: Optional[int] = None
        self.error: Optional[str] = None
        self.sha256: Optional[str] = None
        # Bounded in-memory tail for fast SSE replay; the full log lives on disk.
        self.log_lines: deque = deque(maxlen=5000)
        self.subscribers: List["queue.Queue"] = []
        self.cancel_requested = False

    def to_dict(self) -> dict:
        req = self.request
        artifact = None
        if self.status == "succeeded" and self.output.is_file():
            artifact = {
                "name": self.output.name,
                "size": self.output.stat().st_size,
                "sha256": self.sha256,
            }
        return {
            "id": self.id,
            "status": self.status,
            "platform": req.platform,
            "target": req.target,
            "save_mode": req.save_mode,
            "rom_name": req.rom_name,
            "created_at": _iso(self.created_at),
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "returncode": self.returncode,
            "error": self.error,
            "artifact": artifact,
        }


class JobManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jobs: Dict[str, Job] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._procs: Dict[str, subprocess.Popen] = {}
        self._worker = threading.Thread(target=self._run_loop, name="romboot-build", daemon=True)
        self._worker.start()

    # --- public API --------------------------------------------------------
    def submit(self, request: BuildRequest) -> Job:
        job_id = uuid.uuid4().hex
        job_dir = self.settings.jobs_dir / job_id
        workspace = job_dir / "workspace"
        artifact_dir = job_dir / "artifact"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        name = "{}-{}{}".format(_safe_stem(request.rom_name), request.target,
                                self.settings.output_suffix)
        output = artifact_dir / name
        log_path = job_dir / "build.log"
        log_path.touch()
        job = Job(job_id, request, workspace, output, log_path)
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
        self._queue.put(job_id)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> List[dict]:
        with self._lock:
            jobs = [self._jobs[jid] for jid in reversed(self._order) if jid in self._jobs]
        return [job.to_dict() for job in jobs]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in _TERMINAL:
                return False
            job.cancel_requested = True
            proc = self._procs.get(job_id)
        if proc is not None and proc.poll() is None:
            self._terminate_tree(proc)
        elif job.status == "queued":
            # Not started yet; mark cancelled now so the worker skips it.
            self._finish(job, "cancelled", returncode=None, error="cancelled before start")
        return True

    def subscribe(self, job: Job) -> "queue.Queue":
        """Register for live log lines.  Returns a queue plus a replay snapshot
        captured atomically so no line is lost or duplicated."""
        listener: "queue.Queue" = queue.Queue(maxsize=20000)
        with self._lock:
            replay = list(job.log_lines)
            terminal = job.status in _TERMINAL
            if not terminal:
                job.subscribers.append(listener)
        return listener, replay, terminal

    def unsubscribe(self, job: Job, listener: "queue.Queue") -> None:
        with self._lock:
            if listener in job.subscribers:
                job.subscribers.remove(listener)

    # --- worker ------------------------------------------------------------
    def _run_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.get(job_id)
            if job is None or job.cancel_requested or job.status in _TERMINAL:
                continue
            try:
                self._run_job(job)
            except Exception as exc:  # never let the worker thread die
                self._append_log(job, "romboot-web: internal error: {}".format(exc))
                self._finish(job, "failed", returncode=None, error=str(exc))

    def _run_job(self, job: Job) -> None:
        with self._lock:
            job.status = "running"
            job.started_at = time.time()
        spec = self._spec_for(job)
        spec_path = job.workspace.parent / "spec.json"
        spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        command = [sys.executable, "-u", "-m", "romboot_web.build_worker", str(spec_path)]
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self._append_log(job, "romboot-web: starting build ({} -> {})".format(
            spec["platform"] or "auto", spec["target"]))
        proc = subprocess.Popen(
            command,
            cwd=str(self.settings.project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
            start_new_session=True,  # own process group so cancel kills make too
        )
        with self._lock:
            self._procs[job.id] = proc
        assert proc.stdout is not None
        with open(job.log_path, "a", encoding="utf-8") as log_file:
            for line in proc.stdout:
                line = line.rstrip("\n")
                self._append_log(job, line, log_file=log_file)
        returncode = proc.wait()
        with self._lock:
            self._procs.pop(job.id, None)
        if job.cancel_requested:
            self._finish(job, "cancelled", returncode=returncode, error="cancelled")
        elif returncode == 0 and job.output.is_file():
            self._finish(job, "succeeded", returncode=0, error=None,
                         sha256=self._read_sha256(job.output))
        else:
            tail = "\n".join(list(job.log_lines)[-8:])
            self._finish(job, "failed", returncode=returncode,
                         error="build failed (exit {}). Last output:\n{}".format(returncode, tail))
        self._cleanup_staging(job)

    # --- helpers -----------------------------------------------------------
    def _spec_for(self, job: Job) -> dict:
        req = job.request
        s = self.settings
        return {
            "rom": str(req.rom_path),
            "rom_name": req.rom_name,
            "platform": req.platform,
            "target": req.target,
            "save_mode": req.save_mode,
            "splash": str(req.splash_path) if req.splash_path else None,
            "bios": [str(p) for p in req.bios_paths],
            "workspace": str(job.workspace),
            "output": str(job.output),
            "buildroot_dir": str(s.buildroot_dir) if s.buildroot_dir else None,
            "external_tree": str(s.external_tree),
            "build_output": str(s.warm_output_dir(req.target)),
            "dl_dir": str(s.dl_dir),
            "jobs": s.jobs,
        }

    def _append_log(self, job: Job, line: str, log_file=None) -> None:
        with self._lock:
            job.log_lines.append(line)
            listeners = list(job.subscribers)
        if log_file is not None:
            log_file.write(line + "\n")
            log_file.flush()
        for listener in listeners:
            try:
                listener.put_nowait(line)
            except queue.Full:
                pass

    def _finish(self, job: Job, status: str, returncode: Optional[int],
                error: Optional[str], sha256: Optional[str] = None) -> None:
        with self._lock:
            job.status = status
            job.returncode = returncode
            job.error = error
            job.sha256 = sha256
            job.finished_at = time.time()
            listeners = list(job.subscribers)
            job.subscribers.clear()
        for listener in listeners:
            try:
                listener.put_nowait(_DONE)
            except queue.Full:
                pass

    def _cleanup_staging(self, job: Job) -> None:
        # The artifact lives in a separate directory; the staging tree only holds
        # a copy of the ROM, so drop it once the build is over to reclaim space.
        try:
            if job.workspace.exists():
                shutil.rmtree(job.workspace, ignore_errors=True)
        except OSError:
            pass

    def _read_sha256(self, output: Path) -> Optional[str]:
        sidecar = output.with_name(output.name + ".sha256")
        try:
            return sidecar.read_text(encoding="utf-8").split()[0]
        except (OSError, IndexError):
            return None

    def _terminate_tree(self, proc: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
