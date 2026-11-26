"""Local web server: a form -> storyboard -> the same pipeline stages -> playable film.

    python -m web.server            # http://127.0.0.1:8000

Standard library only. Binds to localhost so your API keys (read from .env on the server) are never exposed.
Each job runs the normal `python -m pipeline.cli ...` commands inside its own folder under web_jobs/.
"""

import argparse
import json
import mimetypes
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "web_jobs"
STATIC_DIR = Path(__file__).resolve().parent / "static"

VOICES = ["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda", "Zephyr", "Orus"]
MUSIC_STYLES = ["guitar", "ensemble"]
ASPECTS = ["16:9", "9:16"]
MAX_LOG_LINES = 600

# (key, label, weight) - weights add up to 100 and drive the progress bar
STAGES = [
    ("storyboard", "Writing the storyboard", 8),
    ("keyframes", "Generating images", 32),
    ("narration", "Recording Amharic narration", 20),
    ("music", "Composing music", 8),
    ("motion", "Adding camera motion", 12),
    ("assemble", "Assembling the film", 20),
]

JOBS: dict = {}
JOBS_LOCK = threading.Lock()
WORK_QUEUE: "queue.Queue[str]" = queue.Queue()


# --------------------------------------------------------------------------- job model

def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _save(job: dict) -> None:
    d = _job_dir(job["id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "job.json.tmp"
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(d / "job.json")


def _log(job: dict, line: str) -> None:
    line = line.rstrip()
    if not line:
        return
    job["log"].append(line)
    if len(job["log"]) > MAX_LOG_LINES:
        del job["log"][: len(job["log"]) - MAX_LOG_LINES]


def _set_stage(job: dict, key: str) -> None:
    done = 0
    for k, _label, w in STAGES:
        if k == key:
            break
        done += w
    job["stage"] = key
    job["progress"] = done
    job["stage_started"] = time.time()
    _log(job, f"=== {dict((k, l) for k, l, _ in STAGES)[key]} ===")
    _save(job)


def clean_inputs(raw: dict) -> dict:
    """Validate and normalise form input. Raises ValueError with a user-facing message."""
    idea = str(raw.get("idea", "")).strip()
    if len(idea) < 15:
        raise ValueError("Please describe your story idea (at least a sentence).")
    shots = int(raw.get("shots", 8))
    if not 8 <= shots <= 12:
        raise ValueError("Number of shots must be between 8 and 12.")
    voice = raw.get("voice", "Kore")
    music = raw.get("music", "guitar")
    aspects = [a for a in raw.get("aspects", ASPECTS) if a in ASPECTS]
    if voice not in VOICES:
        raise ValueError("Unknown voice.")
    if music not in MUSIC_STYLES:
        raise ValueError("Unknown music style.")
    if not aspects:
        raise ValueError("Choose at least one video format.")
    return {
        "title": str(raw.get("title", "")).strip()[:100],
        "idea": idea[:2000],
        "character": str(raw.get("character", "")).strip()[:600],
        "setting": str(raw.get("setting", "")).strip()[:200],
        "shots": shots,
        "voice": voice,
        "music": music,
        "aspects": aspects,
    }


# --------------------------------------------------------------------------- pipeline execution

def _run(job: dict, args: list, env: dict, retries: int = 1, wait: int = 0) -> None:
    """Run one pipeline CLI command, streaming its output into the job log; retry on failure."""
    cmd = [sys.executable, "-m", "pipeline.cli", *args]
    for attempt in range(1, retries + 1):
        _log(job, "$ " + " ".join(["pipeline.cli", *args]))
        proc = subprocess.Popen(
            cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if not line.startswith("====") and "AI Heritage Short" not in line:
                _log(job, line)
        proc.wait()
        _save(job)
        if proc.returncode == 0:
            return
        if attempt < retries:
            _log(job, f"[retry {attempt}/{retries - 1}] step failed (often an API rate limit); waiting {wait}s...")
            _save(job)
            time.sleep(wait)
    raise RuntimeError(f"Step failed: {' '.join(args[:2])}. See the log for details.")


def run_job(job: dict) -> None:
    from web.storyboard_builder import generate_storyboard

    jd = _job_dir(job["id"])
    out = jd / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    storyboard_path = jd / "storyboard.json"
    inputs = job["inputs"]

    env = dict(os.environ)
    env.update(
        {
            "OUTPUT_DIR": str(out),
            "CACHE_DIR": str(jd / ".cache"),
            "RUNS_LOG_PATH": str(jd / "runs.jsonl"),
            "GEMINI_TTS_VOICE": inputs["voice"],
            "PYTHONIOENCODING": "utf-8",
        }
    )
    sb = ["--storyboard", str(storyboard_path)]

    try:
        job["status"] = "running"
        _set_stage(job, "storyboard")
        storyboard = generate_storyboard(inputs)
        storyboard_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")
        job["film_title"] = storyboard["film_title"]
        _log(job, f"Storyboard ready: {len(storyboard['shots'])} shots, \"{storyboard['film_title']}\"")

        _set_stage(job, "keyframes")
        _run(job, ["keyframes", *sb], env, retries=3, wait=20)

        _set_stage(job, "narration")
        _run(job, ["narration", *sb], env, retries=6, wait=50)

        _set_stage(job, "music")
        _run(job, ["music", "--synth", "--style", inputs["music"], *sb], env)

        _set_stage(job, "motion")
        _run(job, ["shots", "--kenburns", *sb], env)

        _set_stage(job, "assemble")
        _run(job, ["assemble", "--aspect-ratios", *inputs["aspects"], *sb], env)

        exports = out / "exports"
        job["videos"] = {
            a: f"/jobs/{job['id']}/outputs/exports/film_{a.replace(':', 'x')}.mp4"
            for a in inputs["aspects"]
            if (exports / f"film_{a.replace(':', 'x')}.mp4").is_file()
        }
        if not job["videos"]:
            raise RuntimeError("Assembly finished but no video file was produced.")
        job["keyframes"] = [
            f"/jobs/{job['id']}/outputs/keyframes/{p.name}"
            for p in sorted((out / "keyframes").glob("shot_*.png"))
        ]
        job["shots"] = [
            {
                "id": s["shot_id"],
                "amharic": s["narration_amharic"],
                "english": s["english_translation"],
                "scene": s["scene_description"],
            }
            for s in storyboard["shots"]
        ]
        job["progress"] = 100
        job["status"] = "done"
        job["stage"] = "done"
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        job["status"] = "failed"
        job["error"] = str(exc)
        _log(job, f"[ERROR] {exc}")
    finally:
        job["finished"] = time.time()
        _save(job)


def worker() -> None:
    while True:
        job_id = WORK_QUEUE.get()
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if job:
            run_job(job)
        WORK_QUEUE.task_done()


def load_existing_jobs() -> None:
    if not JOBS_DIR.is_dir():
        return
    for p in JOBS_DIR.glob("*/job.json"):
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if job.get("status") in ("queued", "running"):
            job["status"] = "failed"
            job["error"] = "Server restarted while this job was running."
        JOBS[job["id"]] = job


def public_job(job: dict, full: bool = True) -> dict:
    keys = ["id", "status", "stage", "progress", "error", "created", "finished", "film_title", "videos", "inputs"]
    d = {k: job.get(k) for k in keys}
    d["stages"] = [{"key": k, "label": label} for k, label, _ in STAGES]
    if job.get("stage_started") and job.get("status") == "running":
        d["stage_elapsed"] = int(time.time() - job["stage_started"])
    if full:
        d["log"] = job.get("log", [])[-120:]
        d["keyframes"] = job.get("keyframes", [])
        d["shots"] = job.get("shots", [])
    return d


# --------------------------------------------------------------------------- HTTP

JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")
ALLOWED_FILE = re.compile(
    r"^(storyboard\.json|outputs/exports/[\w.-]+\.mp4|outputs/keyframes/[\w.-]+\.png|outputs/assembly/subtitles\.srt)$"
)


class Handler(BaseHTTPRequestHandler):
    server_version = "HeritageWeb/1.0"

    def log_message(self, fmt, *args):  # quieter console
        pass

    # helpers
    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, download_name: str | None = None) -> None:
        if not path.is_file():
            self._json(404, {"error": "Not found"})
            return
        size = path.stat().st_size
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                elif m.group(2):
                    start = max(0, size - int(m.group(2)))
                end = min(end, size - 1)
                if start <= end:
                    code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except ConnectionError:
            # Browser cancelled the stream (seeking, tab change): not an error.
            pass

    # routes
    def do_GET(self):  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            return self._file(STATIC_DIR / "index.html")
        if path == "/api/config":
            return self._json(200, {"voices": VOICES, "music": MUSIC_STYLES, "aspects": ASPECTS})
        if path == "/api/jobs":
            with JOBS_LOCK:
                jobs = sorted(JOBS.values(), key=lambda j: j.get("created", 0), reverse=True)[:20]
                return self._json(200, [public_job(j, full=False) for j in jobs])
        m = re.match(r"^/api/jobs/([0-9a-f]{12})$", path)
        if m:
            with JOBS_LOCK:
                job = JOBS.get(m.group(1))
                return self._json(200, public_job(job)) if job else self._json(404, {"error": "Unknown job"})
        m = re.match(r"^/jobs/([0-9a-f]{12})/(.+)$", path)
        if m and JOB_ID_RE.match(m.group(1)) and ALLOWED_FILE.match(m.group(2)):
            name = Path(m.group(2)).name if "download" in (urlparse(self.path).query or "") else None
            return self._file(_job_dir(m.group(1)) / m.group(2), download_name=name)
        self._json(404, {"error": "Not found"})

    def do_POST(self):  # noqa: N802
        if urlparse(self.path).path != "/api/generate":
            return self._json(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 20000:
                raise ValueError("Request too large.")
            inputs = clean_inputs(json.loads(self.rfile.read(length) or b"{}"))
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json(400, {"error": str(exc)})
        with JOBS_LOCK:
            pending = sum(1 for j in JOBS.values() if j["status"] in ("queued", "running"))
            if pending >= 4:
                return self._json(429, {"error": "Too many films in progress. Please wait for one to finish."})
            job_id = uuid.uuid4().hex[:12]
            job = {
                "id": job_id, "status": "queued", "stage": "queued", "progress": 0, "created": time.time(),
                "inputs": inputs, "log": [], "error": None, "film_title": inputs["title"] or "Your film",
            }
            JOBS[job_id] = job
            _save(job)
        WORK_QUEUE.put(job_id)
        self._json(202, {"id": job_id})


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Heritage Short web UI")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1", help="Keep 127.0.0.1 unless you understand the key exposure risk")
    args = ap.parse_args()
    os.chdir(ROOT)
    JOBS_DIR.mkdir(exist_ok=True)
    load_existing_jobs()
    threading.Thread(target=worker, daemon=True).start()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AI Heritage Short web UI running at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
