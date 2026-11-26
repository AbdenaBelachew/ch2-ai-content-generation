"""Build a self-contained static gallery site from a finished film.

    python -m web.publish                 # latest finished film -> site/
    python -m web.publish --job <id>      # a specific film
    python -m web.publish --out public    # another output folder

The result is plain HTML + MP4 + JPG files you can host anywhere (GitHub Pages, Netlify, Cloudflare Pages,
any web server). Nothing is uploaded by this script, and no API keys or .env content are ever copied.
"""

import argparse
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "web_jobs"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:type" content="video.other">
<meta property="og:image" content="__POSTER__">
<style>
  :root { --bg:#14100c; --panel:#1d1712; --panel2:#261e17; --line:#3a2e24; --text:#f1e6d8; --muted:#a89782; --accent:#e0a458; --accent2:#c97b3a; }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f6efe6; --panel:#fffaf3; --panel2:#f0e5d6; --line:#dcc9b2; --text:#2a2017; --muted:#7b6955; --accent:#b86a1c; --accent2:#9c5410; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:16px/1.6 system-ui,"Segoe UI",sans-serif; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 0 16px; }
  header { padding: 40px 0 18px; }
  .eyebrow { color: var(--accent); font-weight: 700; letter-spacing: .12em; font-size: 12px; text-transform: uppercase; }
  h1 { margin: 6px 0 8px; font-size: clamp(28px, 5vw, 44px); line-height: 1.15; }
  .lede { color: var(--muted); margin: 0; max-width: 62ch; }
  .tabs { display:flex; gap:8px; margin: 26px 0 12px; }
  .tab { font:inherit; font-weight:600; cursor:pointer; background:var(--panel2); color:var(--muted); border:1px solid var(--line); padding:6px 16px; border-radius:99px; }
  .tab[aria-pressed=true] { background:var(--accent); color:#1b1007; border-color:var(--accent); }
  .player { background:#000; border-radius:14px; overflow:hidden; display:grid; place-items:center; border:1px solid var(--line); }
  video { display:block; width:100%; max-height:78vh; background:#000; }
  video.vertical { width:auto; height:76vh; max-width:100%; }
  .dl { display:flex; gap:10px; flex-wrap:wrap; margin: 14px 0 0; }
  .dl a { text-decoration:none; font-weight:700; font-size:14px; padding:8px 14px; border-radius:10px; background:var(--accent); color:#1b1007; }
  .dl a.alt { background:var(--panel2); color:var(--text); border:1px solid var(--line); }
  h2 { margin: 46px 0 6px; font-size: 22px; }
  .sub { color: var(--muted); margin: 0 0 16px; }
  .scenes { display:grid; gap:18px; }
  .scene { display:grid; grid-template-columns: minmax(0, 300px) 1fr; gap:16px; background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px; align-items:center; }
  .scene img { width:100%; aspect-ratio:16/9; object-fit:cover; border-radius:10px; display:block; }
  .n { color:var(--accent); font-weight:800; font-size:13px; letter-spacing:.08em; }
  .am { font-size:19px; line-height:1.5; margin:4px 0; }
  .en { color:var(--muted); margin:0; }
  @media (max-width: 640px) { .scene { grid-template-columns: 1fr; } }
  .about { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:18px 20px; }
  .about ul { margin: 8px 0 0; padding-left: 20px; color: var(--muted); }
  .disclosure { margin: 28px 0 8px; padding: 14px 18px; border-left: 4px solid var(--accent); background:var(--panel2); border-radius: 0 10px 10px 0; font-size: 14.5px; }
  footer { color:var(--muted); font-size:13px; padding: 12px 0 48px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="eyebrow">AI Heritage Short</div>
    <h1>__TITLE__</h1>
    <p class="lede">__DESC__</p>
  </header>

  <div class="tabs" id="tabs" role="group" aria-label="Video format">__TABS__</div>
  <div class="player"><video id="v" controls playsinline preload="metadata" poster="__POSTER__"></video></div>
  <div class="dl" id="dl"></div>

  <div class="disclosure"><b>AI disclosure.</b> This film was created with AI tools: the story, images, Amharic narration and music are
  AI-generated. The characters and events are fictional and do not depict any real person.</div>

  <h2>The story, scene by scene</h2>
  <p class="sub">Narration is spoken in Amharic; English captions appear in the film while each line is spoken.</p>
  <div class="scenes">__SCENES__</div>

  <h2>How it was made</h2>
  <div class="about">
    An automated, reproducible pipeline turned a short written idea into this film:
    <ul>
      <li>Storyboard and Amharic script: Google Gemini</li>
      <li>Scene images: FLUX (Cloudflare Workers AI)</li>
      <li>Narration: Gemini text-to-speech</li>
      <li>Music: procedurally synthesised solo guitar</li>
      <li>Camera motion, captions, mix and export: FFmpeg</li>
    </ul>
  </div>
  <footer>Generated __DATE__.</footer>
</div>
<script>
const FILMS = __FILMS__;
const v = document.getElementById("v"), dl = document.getElementById("dl");
function show(key) {
  const f = FILMS[key]; if (!f) return;
  const t = v.currentTime, was = !v.paused;
  v.className = key === "9:16" ? "vertical" : "";
  v.src = f.src; v.load();
  v.addEventListener("loadedmetadata", () => { if (t) v.currentTime = t; if (was) v.play(); }, { once: true });
  document.querySelectorAll(".tab").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.k === key)));
  dl.innerHTML = Object.keys(FILMS).map(k => `<a class="${k === key ? "" : "alt"}" href="${FILMS[k].src}" download>Download ${k}</a>`).join("");
}
document.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => show(b.dataset.k)));
show(Object.keys(FILMS)[0]);
</script>
</body>
</html>
"""


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def latest_done_job() -> Path:
    best = None
    for p in JOBS_DIR.glob("*/job.json"):
        j = json.loads(p.read_text(encoding="utf-8"))
        if j.get("status") == "done" and (best is None or j.get("created", 0) > best[0]):
            best = (j.get("created", 0), p.parent)
    if not best:
        raise SystemExit("No finished film found in web_jobs/. Generate one in the web UI first.")
    return best[1]


def build(job_dir: Path, out: Path) -> Path:
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    storyboard = json.loads((job_dir / "storyboard.json").read_text(encoding="utf-8"))
    exports = job_dir / "outputs" / "exports"
    keyframes = job_dir / "outputs" / "keyframes"

    title = storyboard.get("film_title") or job.get("film_title") or "Untitled"
    desc = storyboard.get("story_description", "")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "film"

    if out.exists():
        shutil.rmtree(out)
    (out / "films").mkdir(parents=True)
    (out / "img").mkdir()

    films = {}
    for aspect, name, size in (("16:9", "film_16x9.mp4", "1280:720"), ("9:16", "film_9x16.mp4", "720:1280")):
        src = exports / name
        if not src.is_file():
            continue
        dst = out / "films" / f"{slug}-{aspect.replace(':', 'x')}.mp4"
        print(f"Encoding {aspect} for the web...")
        _ffmpeg("-i", str(src), "-vf", f"scale={size}", "-c:v", "libx264", "-crf", "25", "-preset", "slow",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst))
        films[aspect] = {"src": f"films/{dst.name}"}
    if not films:
        raise SystemExit("The film has no exported videos.")

    scenes = []
    poster = ""
    for i, shot in enumerate(storyboard["shots"], 1):
        kf = keyframes / f"{shot['shot_id']}.png"
        thumb = f"img/{shot['shot_id']}.jpg"
        if kf.is_file():
            _ffmpeg("-i", str(kf), "-vf", "scale=720:-2", "-q:v", "5", str(out / thumb))
            if not poster:
                _ffmpeg("-i", str(kf), "-vf", "scale=1280:-2", "-q:v", "4", str(out / "img" / "poster.jpg"))
                poster = "img/poster.jpg"
        scenes.append(
            '<div class="scene"><img loading="lazy" src="{t}" alt="{alt}"><div><div class="n">SCENE {n}</div>'
            '<div class="am" lang="am">{am}</div><p class="en">{en}</p></div></div>'.format(
                t=thumb, alt=html.escape(shot["scene_description"]), n=i,
                am=html.escape(shot["narration_amharic"]), en=html.escape(shot["english_translation"]),
            )
        )

    tabs = "".join(
        f'<button class="tab" data-k="{k}" aria-pressed="false">{"Widescreen 16:9" if k == "16:9" else "Vertical 9:16"}</button>'
        for k in films
    )
    date = __import__("datetime").date.today().isoformat()
    page = (
        PAGE.replace("__TITLE__", html.escape(title))
        .replace("__DESC__", html.escape(desc, quote=True))
        .replace("__POSTER__", poster)
        .replace("__TABS__", tabs)
        .replace("__SCENES__", "\n".join(scenes))
        .replace("__FILMS__", json.dumps(films))
        .replace("__DATE__", date)
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a static public gallery from a finished film")
    ap.add_argument("--job", help="Job id in web_jobs/ (default: latest finished film)")
    ap.add_argument("--out", default="site", help="Output folder (default: site)")
    args = ap.parse_args()
    job_dir = JOBS_DIR / args.job if args.job else latest_done_job()
    if not (job_dir / "job.json").is_file():
        sys.exit(f"Job not found: {job_dir}")
    out = build(job_dir, ROOT / args.out)
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"\nSite ready in {out}  ({total / 1e6:.1f} MB)")
    print(f"Preview locally:  python -m http.server 8080 --directory {args.out}   then open http://127.0.0.1:8080")


if __name__ == "__main__":
    main()
