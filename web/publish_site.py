"""Build the public project site from what is already in outputs/ (nothing is generated or uploaded).

    python -m web.publish_site                         # -> site/
    python -m web.publish_site --author "Your Name" --repo https://github.com/you/repo --url https://your.vercel.app

Sources: outputs/exports (films), outputs/keyframes, storyboard.json, the project's markdown docs,
JOURNAL.md and runs.jsonl (aggregated only). The output is plain HTML/CSS/JS + MP4/JPG that any static
host (Vercel, Netlify, GitHub Pages) can serve. The build aborts if anything that looks like an API key
ends up in the site.
"""

import argparse
import collections
import datetime
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent

DOCS = [
    ("README", "README.md", "Overview"),
    ("ARCHITECTURE", "ARCHITECTURE.md", "Architecture"),
    ("DESIGN", "DESIGN.md", "Design & audience"),
    ("EXPERIMENTS", "EXPERIMENTS.md", "Experiments"),
    ("FAILURES", "FAILURES.md", "Failures"),
    ("COSTS", "COSTS.md", "Costs"),
    ("ETHICS", "ETHICS.md", "Ethics & labelling"),
    ("KAGGLE", "kaggle/README.md", "Kaggle guide"),
    ("STORY", None, "Full narration"),
]
DOC_BY_FILE = {Path(f).name.lower(): slug for slug, f, _ in DOCS if f}

SECRET_PATTERNS = [r"AIza[0-9A-Za-z_-]{20,}", r"cfut_[0-9A-Za-z]{10,}", r"KGAT_[0-9a-f]{10,}", r"AQ\.Ab[0-9A-Za-z_-]{20,}", r"Bearer\s+[A-Za-z0-9._-]{20,}"]
LATEX_SYMBOLS = {"$\\to$": "→", "$\\rightarrow$": "→", "$\\times$": "×", "$\\approx$": "≈", "$\\leq$": "≤", "$\\geq$": "≥"}


# --------------------------------------------------------------------------- markdown (small, safe subset)

def _inline(text: str, link_prefix: str) -> str:
    for tex, sym in LATEX_SYMBOLS.items():
        text = text.replace(tex, sym)
    t = html.escape(text, quote=False)
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", stash, t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<em>\1</em>", t)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2)).strip()
        if re.match(r"^https?://", url):
            return f'<a href="{html.escape(url, quote=True)}" rel="noopener">{label}</a>'
        base = Path(url.split("#")[0]).name.lower()
        if base in DOC_BY_FILE:
            return f'<a href="{link_prefix}{DOC_BY_FILE[base]}.html">{label}</a>'
        return label  # unknown relative path: keep the text, drop the dead link

    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, t)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", t)


def md_to_html(md: str, link_prefix: str = "") -> str:
    out, lines, i = [], md.replace("\r\n", "\n").split("\n"), 0
    para: list = []
    lists: list = []  # stack of (indent, tag)

    def flush_para():
        if para:
            out.append("<p>" + _inline(" ".join(para), link_prefix) + "</p>")
            para.clear()

    def close_lists(to_indent=-1):
        while lists and lists[-1][0] > to_indent:
            out.append(f"</li></{lists.pop()[1]}>")

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush_para(); close_lists()
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j]); j += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_para(); close_lists()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2), link_prefix)}</h{n}>")
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            flush_para(); close_lists(); out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            flush_para(); close_lists()

            def cells(row):
                return [c.strip() for c in row.strip().strip("|").split("|")]

            head = cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(cells(lines[i])); i += 1
            out.append('<div class="tablewrap"><table><thead><tr>' + "".join(f"<th>{_inline(c, link_prefix)}</th>" for c in head)
                       + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{_inline(c, link_prefix)}</td>" for c in r) + "</tr>" for r in rows)
                       + "</tbody></table></div>")
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            flush_para()
            indent, tag = len(m.group(1)), ("ol" if m.group(2)[0].isdigit() else "ul")
            if not lists or indent > lists[-1][0]:
                out.append(f"<{tag}><li>")
                lists.append((indent, tag))
            else:
                close_lists(indent)
                if lists and lists[-1][0] == indent:
                    out.append("</li><li>")
                else:
                    out.append(f"<{tag}><li>"); lists.append((indent, tag))
            out.append(_inline(m.group(3), link_prefix))
            i += 1
            continue
        if line.startswith(">"):
            flush_para(); close_lists()
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            alert = re.match(r"^\[!(\w+)\]\s*$", quote[0]) if quote else None
            if alert:
                quote[0] = f"**{alert.group(1).capitalize()}**"
            out.append("<blockquote>" + md_to_html("\n".join(quote), link_prefix) + "</blockquote>")
            continue
        if not line.strip():
            flush_para(); close_lists()
        else:
            if lists:
                out.append(" " + _inline(line.strip(), link_prefix))  # list continuation line
            else:
                para.append(line.strip())
        i += 1
    flush_para(); close_lists()
    return "\n".join(out)


def with_toc(body_html: str) -> tuple:
    """Give every h2 an id and return (html, toc_html)."""
    items = []

    def repl(m):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        slug = re.sub(r"[^a-z0-9]+", "-", html.unescape(text).lower()).strip("-") or f"s{len(items) + 1}"
        items.append((slug, text))
        return f'<h2 id="{slug}">{m.group(1)}</h2>'

    body = re.sub(r"<h2>(.*?)</h2>", repl, body_html)
    toc = ""
    if len(items) >= 3:
        toc = '<aside class="toc" aria-label="On this page"><b>On this page</b>' + "".join(
            f'<a href="#{s}">{t}</a>' for s, t in items) + "</aside>"
    return body, toc


# --------------------------------------------------------------------------- design

CSS = """
:root{--bg:#fbf8f2;--bg2:#f3ece0;--panel:#ffffff;--panel2:#f5eee3;--line:#e5dac8;--text:#241b13;--muted:#6b5b48;
--accent:#b4531c;--accent2:#8f3f12;--green:#2d7a43;--red:#b53a2a;--gold:#8a6100;--blue:#2c64a6;--ink:#ffffff;
--shadow:0 20px 44px -24px rgba(60,40,20,.35);--serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--ethiopic:"Noto Sans Ethiopic",Nyala,"Abyssinica SIL",var(--sans)}
:root[data-theme=dark]{--bg:#0f0b08;--bg2:#15100c;--panel:#1b1510;--panel2:#251c15;--line:#352a20;--text:#f3e9db;--muted:#b0a08b;
--accent:#e7ac58;--accent2:#f2bf76;--green:#4b9b5f;--red:#d9573f;--gold:#f0c24b;--blue:#6f9fd8;--ink:#1b1007;--shadow:0 30px 80px -28px rgba(0,0,0,.75)}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:128px;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16.5px/1.7 var(--sans);overflow-x:hidden}
::selection{background:var(--accent);color:var(--ink)}
a{color:var(--accent);text-underline-offset:3px}a:hover{color:var(--accent2)}
img{max-width:100%}
.skip{position:absolute;left:-999px}.skip:focus{left:12px;top:12px;background:var(--accent);color:var(--ink);padding:8px 12px;border-radius:10px;z-index:99}
.wrap{max-width:1120px;margin:0 auto;padding:0 22px}
#progress{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:60}

/* header */
.top{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--bg) 82%,transparent);backdrop-filter:saturate(1.4) blur(14px);-webkit-backdrop-filter:saturate(1.4) blur(14px);border-bottom:1px solid var(--line)}
.flag{height:3px;display:grid;grid-template-columns:repeat(3,1fr)}.flag i:nth-child(1){background:#2f9e44}.flag i:nth-child(2){background:#f2c500}.flag i:nth-child(3){background:#da1212}
.bar{display:flex;align-items:center;gap:14px;padding:11px 0}
.brand{display:flex;align-items:center;gap:12px;text-decoration:none;color:var(--text)}
.mark{width:38px;height:38px;border-radius:11px;background:var(--accent);display:grid;place-items:center}
.mark svg{width:22px;height:22px;fill:var(--ink)}
.brand small{display:block;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:700;line-height:1.1}
.brand b{display:block;font:700 19px/1.15 var(--serif);letter-spacing:0;text-transform:none}
.spacer{flex:1}
.theme{font:600 13px var(--sans);cursor:pointer;background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:99px;padding:7px 14px;transition:.2s}
.theme:hover{border-color:var(--accent);transform:translateY(-1px)}
.navwrap{display:flex;align-items:center;gap:2px;margin-left:22px}
.nl{font:600 14px var(--sans);display:inline-flex;align-items:center;gap:6px;white-space:nowrap;text-decoration:none;color:var(--muted);background:none;border:0;cursor:pointer;padding:8px 13px;border-radius:10px;transition:.18s}
.nl:hover,.dd.open>.dd-btn{color:var(--text);background:var(--panel2)}
.nl.on{color:var(--accent)}.nl.on:not(.dd-btn){background:color-mix(in srgb,var(--accent) 14%,transparent)}
.dd{position:relative}
.dd-btn svg{width:12px;height:12px;transition:transform .2s}.dd.open .dd-btn svg{transform:rotate(180deg)}
.dd-menu{display:none;position:absolute;left:0;top:calc(100% + 10px);min-width:280px;padding:8px;background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);z-index:70}
.dd.open .dd-menu{display:grid;gap:2px;animation:ddin .16s ease}
@keyframes ddin{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
.dd-menu a{display:block;text-decoration:none;color:var(--text);padding:9px 12px;border-radius:10px;font-size:14.5px;line-height:1.3}
.dd-menu a small{display:block;color:var(--muted);font-size:12.5px;margin-top:2px}
.dd-menu a:hover,.dd-menu a.on,.dd-menu a[aria-current=page]{background:var(--panel2);color:var(--accent)}
.burger{display:none;width:42px;height:38px;border-radius:10px;border:1px solid var(--line);background:var(--panel2);color:var(--text);cursor:pointer;place-items:center}
.burger svg{width:20px;height:20px}
@media(max-width:900px){
  .burger{display:grid}
  .navwrap{display:none;position:absolute;left:0;right:0;top:100%;margin:0;padding:10px 16px 18px;flex-direction:column;align-items:stretch;gap:2px;background:var(--bg);border-bottom:1px solid var(--line);max-height:calc(100vh - 70px);overflow:auto}
  .top.menu .navwrap{display:flex}
  .dd-menu{position:static;box-shadow:none;border:0;background:transparent;padding:0 0 6px 12px;min-width:0;animation:none}
}

/* hero */
.hero{position:relative;background:var(--bg2);border-bottom:1px solid var(--line)}
.hero .in{padding:76px 22px 40px;display:grid;gap:36px;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);align-items:center}
@media(max-width:900px){.hero .in{grid-template-columns:1fr;padding-top:48px}}
.eyebrow{display:inline-flex;align-items:center;gap:10px;color:var(--accent);font-weight:800;letter-spacing:.16em;font-size:12px;text-transform:uppercase}
.eyebrow:before{content:"";width:28px;height:2px;background:var(--accent);border-radius:2px}
h1.title{font:700 clamp(36px,6.4vw,72px)/1.04 var(--serif);margin:14px 0 8px;letter-spacing:-.01em}
h1.title .am{font-family:var(--ethiopic);display:block;font-weight:800}
h1.title .en{display:block;font-size:.5em;color:var(--accent);font-style:italic;margin-top:6px}
.lede{color:var(--muted);font-size:18px;max-width:60ch;margin:0 0 20px}
.cta{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0 4px}
.btn{display:inline-flex;align-items:center;gap:8px;text-decoration:none;font-weight:700;font-size:15px;padding:12px 20px;border-radius:12px;background:var(--accent);color:var(--ink);border:0;cursor:pointer;box-shadow:0 8px 20px -10px var(--accent);transition:.2s}
.btn:hover{transform:translateY(-2px);color:var(--ink);background:var(--accent2);box-shadow:0 12px 24px -10px var(--accent)}
.btn.ghost{background:transparent;color:var(--text);border:1px solid var(--line);box-shadow:none}.btn.ghost:hover{border-color:var(--accent);color:var(--accent);background:var(--panel2)}
.btn.sm{padding:8px 14px;font-size:13.5px;border-radius:10px}
.stats{display:flex;gap:26px;flex-wrap:wrap;margin-top:26px}.stats div b{display:block;font:700 30px/1 var(--serif);color:var(--text)}.stats div span{font-size:12.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.09em}
.heroart{position:relative}
.heroart img{width:100%;aspect-ratio:4/5;object-fit:cover;border-radius:22px;box-shadow:var(--shadow);border:1px solid var(--line);display:block}
.heroart:before{content:"";position:absolute;inset:14px -14px -14px 14px;border:2px solid var(--accent);opacity:.5;border-radius:22px;z-index:-1}
.heroart .tag{position:absolute;left:14px;bottom:14px;background:color-mix(in srgb,var(--bg) 80%,transparent);backdrop-filter:blur(8px);border:1px solid var(--line);padding:6px 12px;border-radius:99px;font-size:12.5px}

/* sections */
section{padding:72px 0 8px}
.sh{display:flex;gap:18px;align-items:flex-end;margin-bottom:22px}
.sh .num{font:800 54px/1 var(--serif);color:transparent;-webkit-text-stroke:1.5px var(--accent);opacity:.8}
.sh h2{font:700 clamp(28px,4vw,40px)/1.1 var(--serif);margin:2px 0 0}
.sub{color:var(--muted);max-width:68ch;margin:0 0 22px;font-size:17px}

/* player */
.tabs{display:inline-flex;gap:4px;padding:4px;background:var(--panel);border:1px solid var(--line);border-radius:99px;margin:0 0 16px}
.tab{font:600 14px var(--sans);cursor:pointer;background:transparent;color:var(--muted);border:0;padding:8px 18px;border-radius:99px;transition:.2s}
.tab[aria-pressed=true]{background:var(--accent);color:var(--ink)}
.stage{position:relative;background:#000;border-radius:20px;overflow:hidden;display:grid;place-items:center;border:1px solid var(--line);box-shadow:var(--shadow)}
video{display:block;width:100%;max-height:80vh;background:#000}video.vertical{width:auto;height:78vh;max-width:100%}
.dl{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}
.rail{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x proximity;padding:16px 2px 12px;margin-top:6px;scrollbar-width:thin;scrollbar-color:var(--line) transparent}
.ch{flex:0 0 186px;scroll-snap-align:start;text-align:left;font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:8px;cursor:pointer;transition:.25s}
.ch:hover{transform:translateY(-3px);border-color:var(--accent)}
.ch.on{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent),0 16px 30px -16px var(--accent2);background:var(--panel2)}
.ch img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:9px;display:block}
.ch .t{display:flex;justify-content:space-between;font-size:12px;color:var(--accent);font-weight:800;letter-spacing:.06em;margin:8px 2px 2px}
.ch p{margin:0 2px;font-size:12.5px;line-height:1.4;color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 0}.chip{font-size:12.5px;padding:4px 12px;border-radius:99px;border:1px solid var(--line);background:var(--panel);color:var(--muted)}

/* cards, grids */
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px 22px;box-shadow:0 1px 0 rgba(255,255,255,.03) inset}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(270px,1fr))}
.sumcards{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));margin:0 0 20px}
.sumcards div{border:1px solid var(--line);background:var(--panel);border-radius:16px;padding:14px 18px}.sumcards b{display:block;font:700 34px/1 var(--serif)}.sumcards span{font-size:12.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.sumcards .ok b{color:var(--green)}.sumcards .part b{color:var(--gold)}.sumcards .no b{color:var(--red)}
.tablewrap{overflow-x:auto;margin:14px 0;border:1px solid var(--line);border-radius:14px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:14.5px}th,td{padding:11px 14px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
th{background:var(--panel2);font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}tr:last-child td{border-bottom:0}tbody tr:hover td{background:color-mix(in srgb,var(--panel2) 55%,transparent)}
.badge{display:inline-block;font-size:12px;font-weight:800;letter-spacing:.04em;padding:3px 10px;border-radius:99px;white-space:nowrap;border:1px solid currentColor}
.badge.ok{color:var(--green)}.badge.part{color:var(--gold)}.badge.no{color:var(--red)}.badge.cached{color:var(--blue)}
.small{font-size:13px;color:var(--muted)}

/* storyboard */
.char{display:grid;gap:22px;grid-template-columns:minmax(0,300px) 1fr;align-items:center;margin-bottom:26px}
.char img{width:100%;border-radius:14px;cursor:zoom-in;display:block}
.scene{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:26px;align-items:center;margin:22px 0;padding:14px;background:var(--panel);border:1px solid var(--line);border-radius:22px;transition:.3s}
.scene:hover{border-color:color-mix(in srgb,var(--accent) 60%,var(--line));box-shadow:var(--shadow)}
.scene.alt .pic{order:2}
.pic{overflow:hidden;border-radius:14px;position:relative;cursor:zoom-in;border:0;padding:0;background:none;display:block;width:100%}
.pic img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;transition:transform .6s}.pic:hover img{transform:scale(1.05)}
.pic .no{position:absolute;left:12px;top:12px;background:var(--accent);color:var(--ink);font-weight:800;font-size:12px;letter-spacing:.08em;padding:4px 11px;border-radius:99px}
.scene .am{font:700 clamp(19px,2.2vw,25px)/1.5 var(--ethiopic);margin:0 0 8px}
.scene .en{font:italic 17px/1.55 var(--serif);color:var(--muted);margin:0 0 12px}
.meta{font-size:13px;color:var(--muted)}.meta b{color:var(--text)}
details{margin-top:10px;font-size:14px}summary{cursor:pointer;color:var(--accent);font-weight:600}details p{color:var(--muted)}
@media(max-width:760px){.scene,.char{grid-template-columns:1fr}.scene.alt .pic{order:0}}

/* sound */
.player-card{display:flex;gap:16px;align-items:center}
.ico{flex:none;width:52px;height:52px;border-radius:14px;background:var(--accent);display:grid;place-items:center}.ico svg{width:26px;height:26px;fill:var(--ink)}
audio{width:100%;margin-top:10px;accent-color:var(--accent)}

/* pipeline */
.flow{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));counter-reset:s;position:relative}
.step{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px 14px 14px;transition:.25s}
.step:hover{transform:translateY(-4px);border-color:var(--accent)}
.step:before{counter-increment:s;content:counter(s);display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--accent);color:var(--ink);font-weight:800;font-size:13px;margin-bottom:10px}
.step b{display:block;font:700 17px var(--serif)}.step small{display:block;color:var(--muted);line-height:1.45;margin-top:4px}
pre{background:#0b0805;color:#f1e6d8;border:1px solid var(--line);border-radius:14px;padding:16px 18px;overflow:auto;font-size:13.5px;line-height:1.6}
:root[data-theme=light] pre{background:#2b2016;color:#fbf2e4}
code{font-family:ui-monospace,"Cascadia Code",Consolas,monospace;font-size:.9em}
p code,li code,td code{background:var(--panel2);padding:2px 6px;border-radius:6px;border:1px solid var(--line)}
pre code{background:none;border:0;padding:0}

/* telemetry */
.bars{display:grid;gap:12px;margin:16px 0}
.bar-row{display:grid;grid-template-columns:110px 1fr 40px;gap:12px;align-items:center;font-size:14px}
.track{display:flex;height:16px;border-radius:99px;overflow:hidden;background:var(--panel2);border:1px solid var(--line)}
.track i{display:block;height:100%}.s-ok{background:var(--green)}.s-cached{background:var(--blue)}.s-fail{background:var(--red)}.s-other{background:var(--gold)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted)}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}
.stat{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:0 0 18px}
.stat div{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 18px}.stat b{display:block;font:700 34px/1 var(--serif);color:var(--accent)}.stat span{font-size:12.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}

/* downloads */
.files{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.file{display:flex;gap:14px;align-items:flex-start;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 16px;text-decoration:none;color:var(--text);transition:.25s}
.file:hover{transform:translateY(-3px);border-color:var(--accent);color:var(--text)}
.ext{flex:none;width:48px;height:56px;border-radius:10px;background:var(--panel2);border:1px solid var(--line);display:grid;place-items:center;font-weight:800;font-size:11.5px;color:var(--accent);letter-spacing:.04em}
.file b{display:block;font-size:15px;word-break:break-all}.file small{display:block;color:var(--muted);line-height:1.4;margin-top:2px}.file .sz{color:var(--accent);font-weight:700}

/* prose + journal + docs */
.prose{max-width:76ch}.prose h1{font:700 clamp(30px,4vw,44px)/1.15 var(--serif)}.prose h2{font:700 28px/1.2 var(--serif);margin:2em 0 .4em}.prose h3{font:700 20px var(--serif);margin:1.6em 0 .3em}
.prose p,.prose li{color:color-mix(in srgb,var(--text) 90%,var(--muted))}.prose li{margin:.25em 0}.prose hr{border:0;border-top:1px solid var(--line);margin:2em 0}
blockquote{margin:16px 0;padding:8px 18px;border-left:4px solid var(--accent);background:var(--panel);border-radius:0 12px 12px 0}blockquote p{margin:.4em 0}
.journal h2{position:relative;padding-left:28px;font:700 24px/1.25 var(--serif);margin:2em 0 .5em}
.journal h2:before{content:"";position:absolute;left:0;top:.45em;width:14px;height:14px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 5px color-mix(in srgb,var(--accent) 25%,transparent)}
.journal{border-left:2px solid var(--line);padding-left:10px;margin-left:6px}
.docgrid{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:48px;align-items:start}
.toc{position:sticky;top:140px;display:grid;gap:2px;font-size:14px;border-left:2px solid var(--line);padding-left:14px}
.toc b{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin-bottom:6px}.toc a{color:var(--muted);text-decoration:none;padding:3px 0}.toc a:hover{color:var(--accent)}
@media(max-width:960px){.docgrid{grid-template-columns:1fr}.toc{display:none}}
.notice{margin:0 0 26px;padding:14px 18px;border:1px solid var(--line);border-left:4px solid var(--accent);background:var(--panel);border-radius:0 14px 14px 0;font-size:15px}

/* footer */
footer{margin-top:90px;background:var(--bg2);border-top:1px solid var(--line)}
footer .flag{margin-bottom:34px}
footer .cols{display:grid;gap:30px;grid-template-columns:1.4fr 1fr 1fr}
@media(max-width:760px){footer .cols{grid-template-columns:1fr}}
footer h4{margin:0 0 10px;font:700 12px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
footer p,footer li{color:var(--muted);font-size:14px;margin:.3em 0}footer ul{list-style:none;margin:0;padding:0}footer a{text-decoration:none}footer a:hover{text-decoration:underline}
.fine{border-top:1px solid var(--line);margin-top:30px;padding:18px 0 40px;font-size:13px;color:var(--muted)}
.author{display:flex;align-items:center;gap:10px;margin-bottom:12px}.ini{width:36px;height:36px;border-radius:50%;background:var(--accent);color:var(--ink);display:grid;place-items:center;font-weight:800;font-size:13px}

/* lightbox */
dialog#lb{border:0;padding:0;background:transparent;max-width:96vw;max-height:94vh;overflow:visible}
dialog#lb::backdrop{background:rgba(5,3,2,.88);backdrop-filter:blur(6px)}
dialog#lb img{display:block;max-width:96vw;max-height:88vh;border-radius:14px;box-shadow:0 30px 100px rgba(0,0,0,.7)}
dialog#lb p{color:#f3e9db;text-align:center;margin:10px 0 0;font-size:14px}
dialog#lb button{position:absolute;right:-6px;top:-44px;font:600 14px var(--sans);background:var(--accent);color:var(--ink);border:0;border-radius:99px;padding:6px 14px;cursor:pointer}

/* motion */
.js .rv{opacity:0;transform:translateY(22px);transition:opacity .7s ease,transform .7s ease}.js .rv.in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important;animation:none!important}.js .rv{opacity:1;transform:none}}
:focus-visible{outline:3px solid var(--accent);outline-offset:3px;border-radius:6px}
"""

JS = """
(function(){
  var root=document.documentElement;root.classList.add('js');
  var btn=document.getElementById('theme');
  function apply(t){root.setAttribute('data-theme',t);if(btn)btn.textContent=t==='dark'?'Light mode':'Dark mode';}
  var saved=null;try{saved=localStorage.getItem('theme');}catch(e){}
  apply(saved||'light');
  if(btn)btn.addEventListener('click',function(){var t=root.getAttribute('data-theme')==='dark'?'light':'dark';apply(t);try{localStorage.setItem('theme',t);}catch(e){}});

  var pg=document.getElementById('progress');
  function prog(){var h=document.documentElement;var m=h.scrollHeight-h.clientHeight;pg.style.width=(m>0?(h.scrollTop/m*100):0)+'%';}
  addEventListener('scroll',prog,{passive:true});prog();

  var rv=document.querySelectorAll('.rv');
  if('IntersectionObserver' in window){
    var ro=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');ro.unobserve(e.target);}});},{rootMargin:'0px 0px -8% 0px'});
    rv.forEach(function(el){ro.observe(el);});
  }else{rv.forEach(function(el){el.classList.add('in');});}

  var v=document.getElementById('v'),dl=document.getElementById('dl'),rail=document.getElementById('rail');
  if(v&&window.FILMS){
    var keys=Object.keys(FILMS),SHOT=window.SHOT_SECONDS||7.5,chs=rail?[].slice.call(rail.querySelectorAll('.ch')):[],cur=-1;
    window.showFilm=function(k){var f=FILMS[k];if(!f)return;var t=v.currentTime,was=!v.paused;v.className=k==='9:16'?'vertical':'';v.src=f.src;v.load();
      v.addEventListener('loadedmetadata',function(){if(t)v.currentTime=t;if(was)v.play();},{once:true});
      document.querySelectorAll('.tab').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.k===k));});
      dl.innerHTML=keys.map(function(x){return '<a class="btn sm'+(x===k?'':' ghost')+'" href="'+FILMS[x].src+'" download>Download '+x+'</a>';}).join('');};
    document.querySelectorAll('.tab').forEach(function(b){b.addEventListener('click',function(){showFilm(b.dataset.k);});});
    showFilm(keys[0]);
    chs.forEach(function(c,i){c.addEventListener('click',function(){v.currentTime=i*SHOT+0.05;v.play();document.getElementById('player').scrollIntoView({behavior:'smooth',block:'center'});});});
    v.addEventListener('timeupdate',function(){
      var i=Math.min(chs.length-1,Math.floor(v.currentTime/SHOT));
      if(i!==cur){cur=i;chs.forEach(function(c,j){c.classList.toggle('on',j===i);});
        if(chs[i]&&rail&&!v.paused){rail.scrollTo({left:chs[i].offsetLeft-rail.clientWidth/2+chs[i].clientWidth/2,behavior:'smooth'});}}
    });
  }

  var lb=document.getElementById('lb');
  if(lb&&lb.showModal){
    var li=lb.querySelector('img'),lp=lb.querySelector('p');
    document.querySelectorAll('[data-lb]').forEach(function(el){el.addEventListener('click',function(){li.src=el.dataset.lb;li.alt=el.dataset.cap||'';lp.textContent=el.dataset.cap||'';lb.showModal();});});
    lb.addEventListener('click',function(e){if(e.target===lb||e.target.tagName==='BUTTON')lb.close();});
  }

  var top=document.querySelector('.top'),burger=document.getElementById('burger'),dds=[].slice.call(document.querySelectorAll('.dd'));
  function closeAll(ex){dds.forEach(function(d){if(d!==ex){d.classList.remove('open');d.querySelector('.dd-btn').setAttribute('aria-expanded','false');}});}
  function closeMenu(){closeAll();if(top)top.classList.remove('menu');if(burger)burger.setAttribute('aria-expanded','false');}
  dds.forEach(function(d){var b=d.querySelector('.dd-btn');b.addEventListener('click',function(e){e.stopPropagation();var o=!d.classList.contains('open');closeAll(d);d.classList.toggle('open',o);b.setAttribute('aria-expanded',String(o));});});
  document.addEventListener('click',function(e){if(!e.target.closest('.dd'))closeAll();});
  document.addEventListener('keydown',function(e){if(e.key==='Escape')closeMenu();});
  if(burger)burger.addEventListener('click',function(){var o=!top.classList.contains('menu');top.classList.toggle('menu',o);burger.setAttribute('aria-expanded',String(o));});
  document.querySelectorAll('.navwrap a').forEach(function(a){a.addEventListener('click',closeMenu);});

  var links=[].slice.call(document.querySelectorAll('.navwrap a[href^="#"]'));
  if(links.length&&'IntersectionObserver' in window){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){var h='#'+e.target.id;
      links.forEach(function(a){a.classList.toggle('on',a.getAttribute('href')===h);});
      dds.forEach(function(d){d.querySelector('.dd-btn').classList.toggle('on',!!d.querySelector('a.on'));});}});},{rootMargin:'-30% 0px -62% 0px'});
    links.forEach(function(a){var s=document.querySelector(a.getAttribute('href'));if(s)io.observe(s);});
  }
})();
"""

MARK_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h12v6c0 4-2.4 7-6 7s-6-3-6-7z"/><path d="M17 5h2a3 3 0 0 1 0 6h-2V9h2a1 1 0 0 0 0-2h-2z"/><rect x="4" y="19" width="14" height="2" rx="1"/></svg>'
ICON_MIC = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.9V21h2v-3.1A7 7 0 0 0 19 11z"/></svg>'
ICON_NOTE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3v11.6A3.5 3.5 0 1 0 11 18V8h6V3z"/></svg>'


def shell(title: str, body: str, ctx: dict, depth: int, current_doc: str = "") -> str:
    p = "../" * depth
    base = "" if depth == 0 else f"{p}index.html"   # same-page anchors on the home page, links back from docs

    def nl(i, label):
        return f'<a class="nl" href="{base}#{i}">{html.escape(label)}</a>'

    chev = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'

    def dd(label, items):
        return (f'<div class="dd"><button class="nl dd-btn" type="button" aria-expanded="false" aria-haspopup="true">'
                f'{html.escape(label)}{chev}</button><div class="dd-menu">{items}</div></div>')

    made = [("pipeline", "Pipeline", "Seven stages, from storyboard to film"),
            ("wan", "Motion · Kaggle Wan 2.2", "What was and was not run"),
            ("telemetry", "Telemetry", "Every model call, logged"),
            ("journal", "Journal", "What broke and how it was fixed")]
    made_items = "".join(f'<a href="{base}#{i}">{html.escape(l)}<small>{html.escape(d)}</small></a>' for i, l, d in made)
    doc_items = "".join(
        f'<a href="{p}docs/{s}.html"{" aria-current=page" if s == current_doc else ""}>{html.escape(l)}</a>' for s, _f, l in DOCS)
    main_nav = (nl("film", "Film") + nl("review", "For reviewers") + nl("storyboard", "Storyboard") + nl("sound", "Sound")
                + dd("How it's made", made_items) + nl("downloads", "Downloads") + dd("Documents", doc_items))
    docs_list = "".join(
        f'<li><a href="{p}docs/{s}.html"{" aria-current=page" if s == current_doc else ""}>{html.escape(l)}</a></li>' for s, _f, l in DOCS
    )
    author = ""
    if ctx.get("author"):
        ini = "".join(w[0] for w in ctx["author"].split()[:2]).upper()
        repo = f' · <a href="{html.escape(ctx["repo"], quote=True)}" rel="noopener">Source on GitHub ↗</a>' if ctx.get("repo") else ""
        author = f'<div class="author"><span class="ini">{html.escape(ini)}</span><span>{html.escape(ctx["author"])}{repo}</span></div>'
    elif ctx.get("repo"):
        author = f'<div class="author"><a href="{html.escape(ctx["repo"], quote=True)}" rel="noopener">Source on GitHub ↗</a></div>'
    who = html.escape(ctx["author"]) if ctx.get("author") else ""
    og_image = ""
    if ctx.get("base_url"):
        og_image = (f'<meta property="og:image" content="{ctx["base_url"]}/img/poster.jpg">\n'
                    '<meta name="twitter:card" content="summary_large_image">')
    desc = html.escape(ctx["desc"], quote=True)
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#fbf8f2">
<meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="video.other">
{og_image}
<link rel="icon" href="{p}favicon.svg" type="image/svg+xml">
<style>{CSS}</style>
</head>
<body>
<div id="progress"></div>
<a class="skip" href="#app">Skip to content</a>
<header class="top"><div class="flag"><i></i><i></i><i></i></div><div class="wrap">
  <div class="bar">
    <a class="brand" href="{base}#film"><span class="mark">{MARK_SVG}</span><span><small>Heritage Short</small><b>{html.escape(ctx['short_title'])}</b></span></a>
    <nav class="navwrap" id="nav" aria-label="Main">{main_nav}</nav>
    <span class="spacer"></span>
    <button class="theme" id="theme" type="button" aria-label="Toggle colour theme">Dark mode</button>
    <button class="burger" id="burger" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="nav"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>
  </div>
</div></header>
<main id="app">
{body}
</main>
<footer>
  <div class="flag"><i></i><i></i><i></i></div>
  <div class="wrap">
    <div class="cols">
      <div>{author}<h4>Made with AI</h4>
      <p>The story, images, Amharic narration and music are AI-generated. The characters and events are fictional and depict no real person. The Amharic text is machine-written and has not been reviewed by a native speaker.</p></div>
      <div><h4>Built with</h4><ul><li>Gemini: storyboard &amp; speech</li><li>FLUX.1 schnell: images</li><li>Synthesised guitar score</li><li>FFmpeg: motion, captions, mix</li></ul></div>
      <div><h4>Documents</h4><ul>{docs_list}</ul></div>
    </div>
    <div class="fine">Independent challenge submission. © {ctx['year']} {who}</div>
  </div>
</footer>
<dialog id="lb"><button type="button">Close</button><img alt=""><p></p></dialog>
<script>{ctx.get('films_js', '')}</script>
<script>{JS}</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- data

def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def probe(path: Path) -> dict:
    r = run("ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration", "-of", "json", str(path))
    info = {"duration": 0.0, "w": 0, "h": 0, "audio": False}
    try:
        for s in json.loads(r.stdout)["streams"]:
            if s["codec_type"] == "video":
                info.update(w=int(s["width"]), h=int(s["height"]), duration=float(s["duration"]))
            if s["codec_type"] == "audio":
                info["audio"] = True
    except Exception:  # noqa: BLE001
        pass
    return info


def encode(src: Path, dst: Path, size: str) -> None:
    # Standard (limited) colour range, BT.709 and High profile: plays everywhere, including Safari and phones.
    r = run("ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={size}:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-crf", "23", "-preset", "slow", "-profile:v", "high", "-level", "4.1",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(dst))
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg failed encoding {src.name}: {r.stderr[-300:]}")


def jpg(src: Path, dst: Path, width: int, q: int = 5) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = run("ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-q:v", str(q), str(dst))
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg failed on {src.name}: {r.stderr[-300:]}")


def telemetry() -> dict:
    path = ROOT / "runs.jsonl"
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    counts = collections.Counter((r.get("stage", "?"), r.get("provider", "?"), r.get("status", "?")) for r in rows)
    by_status = collections.Counter(r.get("status", "?") for r in rows)
    by_stage = collections.defaultdict(collections.Counter)
    for r in rows:
        by_stage[r.get("stage", "?")][r.get("status", "?")] += 1
    return {"rows": rows, "counts": counts, "by_status": by_status, "by_stage": by_stage}


def badge(s: str) -> str:
    cls = {"SUCCESS": "ok", "CACHED": "cached", "FAILED": "no"}.get(s, "part")
    return f'<span class="badge {cls}">{html.escape(s)}</span>'


def fmt_time(sec: float) -> str:
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


# --------------------------------------------------------------------------- sections

def sec_head(num: str, eyebrow: str, title: str) -> str:
    return f'<div class="sh rv"><span class="num">{num}</span><div><div class="eyebrow">{html.escape(eyebrow)}</div><h2>{html.escape(title)}</h2></div></div>'


def build_sections(ctx: dict, sb: dict, films: dict, info: dict, tele: dict, test_count: str) -> str:
    shots = sb["shots"]
    total = sum(float(s["duration"]) for s in shots)
    f169, f916 = info.get("16:9", {}), info.get("9:16", {})
    title_am = sb["film_title"]
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", title_am)
    am_part, en_part = (m.group(1), m.group(2)) if m else (title_am, "")
    title_html = f'<span class="am">{html.escape(am_part)}</span>' + (f'<span class="en">{html.escape(en_part)}</span>' if en_part else "")
    tabs = "".join(f'<button class="tab" data-k="{k}" aria-pressed="false">{"Widescreen 16:9" if k == "16:9" else "Vertical 9:16"}</button>' for k in films)

    rail = "".join(
        f'<button class="ch" type="button" aria-label="Jump to shot {i}"><img loading="lazy" src="img/{s["shot_id"]}.jpg" alt="">'
        f'<div class="t"><span>SHOT {i}</span><span>{fmt_time((i - 1) * float(s["duration"]))}</span></div><p>{html.escape(s["english_translation"])}</p></button>'
        for i, s in enumerate(shots, 1)
    )

    film = f"""
<div class="hero">
  <div class="wrap in">
    <div>
      <div class="eyebrow">AI Heritage Short</div>
      <h1 class="title">{title_html}</h1>
      <p class="lede">{html.escape(sb['story_description'])}</p>
      <div class="cta"><a class="btn" href="#player">&#9654; Watch the film</a><a class="btn ghost" href="#review">For reviewers</a><a class="btn ghost" href="#pipeline">How it was made</a></div>
      <div class="stats"><div><b>{f169.get('duration', 0):.0f}s</b><span>Runtime</span></div><div><b>{len(shots)}</b><span>Shots</span></div><div><b>2</b><span>Formats</span></div><div><b>100%</b><span>AI, disclosed</span></div></div>
    </div>
    <div class="heroart"><img src="img/poster.jpg" alt="Still from the film: an elderly Ethiopian grandmother in a white netela" fetchpriority="high"><span class="tag">AI-generated, fictional character</span></div>
  </div>
</div>
<section id="film" style="padding-top:56px">
  <div class="wrap">
    {sec_head("01", "The film", "Watch")}
    <div class="tabs" role="group" aria-label="Video format">{tabs}</div>
    <div class="stage" id="player"><video id="v" controls playsinline preload="metadata" poster="img/poster.jpg"></video></div>
    <div class="dl" id="dl"></div>
    <div class="rail" id="rail" aria-label="Chapters">{rail}</div>
    <div class="chips"><span class="chip">Amharic narration</span><span class="chip">English captions</span><span class="chip">Solo guitar score</span><span class="chip">AI end card</span><span class="chip">1080p</span></div>
  </div>
</section>"""

    statuses = []

    def row(label, status, detail):
        statuses.append(status)
        cls = {"Met": "ok", "Partly met": "part"}.get(status, "no")
        return f'<tr><td><b>{label}</b></td><td><span class="badge {cls}">{status}</span></td><td>{detail}</td></tr>'

    ok_len = 60 <= f169.get("duration", 0) <= 90
    rows = [
        row("60-90 s film", "Met" if ok_len else "Not met", f"16:9 export is {f169.get('duration', 0):.1f} s; vertical is {f916.get('duration', 0):.1f} s ({len(shots)} shots x 7.5 s plus a 4 s end card)."),
        row("Amharic narration (Ge'ez script)", "Met", f"{sum(1 for s in shots if s['narration_amharic'])} narrated lines, one per shot, spoken by Gemini TTS. See <a href='docs/STORY.html'>Full narration</a>. Not yet reviewed by a native speaker."),
        row("English subtitles", "Met", "Burned in, shown only while each line is spoken (timed from the actual narration clip lengths)."),
        row("Dual aspect ratios", "Met", f"16:9 at {f169.get('w')}x{f169.get('h')} and 9:16 at {f916.get('w')}x{f916.get('h')}. Centre-cropped, never stretched."),
        row("Original soundtrack", "Partly met", "A clean solo guitar score synthesised in code (original, but a digital instrument). The ACE-Step 1.5 notebook is prepared but was not run."),
        row("Moving shots", "Partly met", "Camera motion (push-in, pan, tilt, zoom-out) over FLUX keyframes via FFmpeg. Wan 2.2 generation is prepared but was not run; see the Wan section."),
        row("Consistent character", "Partly met", "A character reference sheet was generated and every shot prompt repeats the character's traits. FLUX schnell takes text only, so the face is similar across shots, not identical."),
        row("Mandatory AI disclosure", "Met", "Visible end card at the end of both films, plus the footer of this site."),
        row("Loudness and ducking", "Met", "Narration lines gain-matched to the same level (within about 0.7 dB), music ducked beneath the voice, final mix normalised to -16 LUFS."),
        row("Reproducible and auditable", "Met", f"One <code>storyboard.json</code> drives everything; content-addressed cache; every model call logged ({len(tele['rows'])} entries, see Telemetry); {test_count}."),
        row("Cost transparency", "Met", "See <a href='docs/COSTS.html'>Costs</a>."),
    ]
    n_ok, n_part, n_no = statuses.count("Met"), statuses.count("Partly met"), statuses.count("Not met")
    review = f"""
<section id="review"><div class="wrap">
  {sec_head("02", "Evidence", "For reviewers")}
  <p class="sub rv">Each requirement, whether it was met, and the evidence. Figures were measured from the delivered files when this site was built.</p>
  <div class="sumcards rv"><div class="ok"><b>{n_ok}</b><span>Met</span></div><div class="part"><b>{n_part}</b><span>Partly met</span></div><div class="no"><b>{n_no}</b><span>Not met</span></div></div>
  <div class="tablewrap rv"><table><thead><tr><th>Requirement</th><th>Status</th><th>Evidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
  <p class="sub rv">What is not claimed: the film does not use generated video (Wan 2.2) or the ACE-Step model, and the Amharic has not been native-reviewed. Both gaps are recorded in <a href="docs/FAILURES.html">Failures</a> and the Journal below.</p>
</div></section>"""

    char = (sb.get("character_references") or [{}])[0]
    char_html = ""
    if (ctx["out"] / "img" / "character.jpg").exists():
        char_html = f"""<div class="card char rv"><img src="img/character.jpg" data-lb="img/lg/character.jpg" data-cap="Character reference sheet" alt="Character reference sheet: three views of the grandmother">
<div><div class="eyebrow">Character</div><h3 style="font:700 26px var(--serif);margin:8px 0">{html.escape(char.get('name', 'Character'))}</h3><p>{html.escape(char.get('description', ''))}</p><p class="small">A fictional AI-generated character. The reference sheet anchors her traits, which every shot prompt repeats.</p></div></div>"""
    cards = []
    for i, s in enumerate(shots, 1):
        cap = html.escape(s["english_translation"], quote=True)
        cards.append(
            f"""<article class="scene rv{' alt' if i % 2 == 0 else ''}"><button class="pic" type="button" data-lb="img/lg/{s['shot_id']}.jpg" data-cap="{cap}" aria-label="Enlarge shot {i}"><img loading="lazy" src="img/{s['shot_id']}.jpg" alt="{html.escape(s['scene_description'], quote=True)}"><span class="no">SHOT {i}</span></button>
<div><p class="am" lang="am">{html.escape(s['narration_amharic'])}</p><p class="en">{html.escape(s['english_translation'])}</p>
<p class="meta"><b>Camera</b> {html.escape(s['camera_movement'])} &nbsp;·&nbsp; <b>{s['duration']} s</b> &nbsp;·&nbsp; {html.escape(s['visual_purpose'])}</p>
<details><summary>Image and motion prompts</summary><p>{html.escape(s['image_prompt'])}</p><p><b>Motion:</b> {html.escape(s['motion_prompt'])}</p></details></div></article>"""
        )
    storyboard = f"""
<section id="storyboard"><div class="wrap">
  {sec_head("03", "Scene by scene", "Storyboard")}
  <p class="sub rv">The single source of truth is <code>storyboard.json</code>: {len(shots)} shots, {total:.1f} s of footage, validated against a JSON Schema before any model is called. Click an image to enlarge it.</p>
  {char_html}
  {''.join(cards)}
</div></section>"""

    sound = f"""
<section id="sound"><div class="wrap">
  {sec_head("04", "Audio", "Sound")}
  <p class="sub rv">The audio behind the film, separately. Narration is one Gemini TTS take per shot, gain-matched so every line is equally loud. The score is a clean solo guitar synthesised in code (a digital instrument, not a recording).</p>
  <div class="grid">
    <div class="card rv"><div class="player-card"><span class="ico">{ICON_MIC}</span><div><b>Amharic narration</b><div class="small">{len(shots)} lines · {total:.0f} s · one per shot</div></div></div><audio controls preload="none" src="assets/narration.mp3"></audio></div>
    <div class="card rv"><div class="player-card"><span class="ico">{ICON_NOTE}</span><div><b>Solo guitar score</b><div class="small">Tizita-style D minor · 68 BPM</div></div></div><audio controls preload="none" src="assets/soundtrack.mp3"></audio></div>
  </div>
</div></section>"""

    flow = [
        ("Storyboard", "JSON Schema + validator", "storyboard.json"),
        ("Script", "Gemini", "Amharic + English check"),
        ("Keyframes", "Cloudflare FLUX.1 schnell", "character sheet + 1 image per shot"),
        ("Narration", "Gemini TTS", "1 clip per shot, loudness-matched"),
        ("Music", "Synth guitar (ACE-Step prepared)", "full-length score"),
        ("Motion", "FFmpeg Ken Burns (Wan 2.2 prepared)", "7.5 s clip per shot"),
        ("Assembly", "FFmpeg", "captions, ducking, loudnorm, end card"),
    ]
    steps = "".join(f"<div class='step rv'><b>{html.escape(a)}</b><small>{html.escape(b)}<br>{html.escape(c)}</small></div>" for a, b, c in flow)
    pipeline = f"""
<section id="pipeline"><div class="wrap">
  {sec_head("05", "How it works", "Pipeline")}
  <p class="sub rv">Seven stages, each a command in one CLI, each cached by content hash so unchanged work is never repeated or paid for twice.</p>
  <div class="flow">{steps}</div>
  <h3 style="font:700 22px var(--serif);margin:34px 0 10px">Run the stages</h3>
<pre class="rv"><code>python -m pipeline.cli validate
python -m pipeline.cli keyframes
python -m pipeline.cli narration
python -m pipeline.cli music --synth
python -m pipeline.cli shots --kenburns
python -m pipeline.cli assemble</code></pre>
  <h3 style="font:700 22px var(--serif);margin:30px 0 10px">Reproduce it</h3>
<pre class="rv"><code>python -m venv .venv &amp;&amp; .venv\\Scripts\\activate     # Windows (use source .venv/bin/activate elsewhere)
pip install -r requirements.txt
copy .env.example .env      # add GEMINI_API_KEY, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN
python -m pipeline.cli film # or run the stages one by one as above</code></pre>
  <p class="sub">Read more: <a href="docs/ARCHITECTURE.html">Architecture</a> · <a href="docs/DESIGN.html">Design &amp; audience</a> · <a href="docs/EXPERIMENTS.html">Experiments</a>.</p>
</div></section>"""

    wan = """
<section id="wan"><div class="wrap">
  """ + sec_head("06", "GPU stage", "Motion · Kaggle Wan 2.2") + """
  <p class="sub rv">The design calls for Wan 2.2 TI2V-5B to turn each keyframe into a moving clip on a free Kaggle GPU. The batch manifest and notebooks are ready; the model was <b>not run</b> for this delivery.</p>
  <div class="grid">
    <div class="card rv"><div class="eyebrow">What you see instead</div><p>Camera moves (push-in, pan, tilt, zoom-out) applied to the still keyframes with FFmpeg, chosen from each shot's <code>camera_movement</code>. Subjects inside the frame do not move.</p></div>
    <div class="card rv"><div class="eyebrow">To use Wan</div><p>Upload <code>keyframes.zip</code> and <code>wan_batch.json</code> as a Kaggle dataset, run the notebook on a T4 x2, put the <code>shot_XX.mp4</code> files in <code>outputs/shots/</code> and run <code>assemble</code>. See the <a href="docs/KAGGLE.html">Kaggle guide</a> and <a href="#downloads">Downloads</a>.</p></div>
  </div>
</div></section>"""

    rows_t = tele["rows"]
    stat = "".join(f"<div><b>{n}</b><span>{html.escape(l)}</span></div>" for n, l in
                   [(len(rows_t), "logged runs"), (tele["by_status"].get("SUCCESS", 0), "generated"), (tele["by_status"].get("CACHED", 0), "from cache"),
                    (tele["by_status"].get("FAILED", 0), "failed, then fixed")])
    bars = []
    for stage, cnt in sorted(tele["by_stage"].items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(cnt.values())
        seg = [("s-ok", cnt.get("SUCCESS", 0)), ("s-cached", cnt.get("CACHED", 0)), ("s-fail", cnt.get("FAILED", 0))]
        other = tot - sum(n for _c, n in seg)
        seg.append(("s-other", other))
        track = "".join(f'<i class="{c}" style="width:{n / tot * 100:.2f}%" title="{n}"></i>' for c, n in seg if n)
        bars.append(f'<div class="bar-row"><span>{html.escape(str(stage))}</span><div class="track">{track}</div><span class="small">{tot}</span></div>')
    agg = "".join(
        f"<tr><td>{html.escape(str(st))}</td><td>{html.escape(str(pr))}</td><td>{badge(str(ss))}</td><td>{n}</td></tr>"
        for (st, pr, ss), n in sorted(tele["counts"].items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), str(kv[0][2])))
    )
    recent = "".join(
        f"<tr><td>{html.escape(str(r.get('timestamp', ''))[:19].replace('T', ' '))}</td><td>{html.escape(str(r.get('stage', '')))}</td><td>{html.escape(str(r.get('provider', '')))}</td><td>{html.escape(str(r.get('model', '')))}</td><td>{badge(str(r.get('status', '')))}</td></tr>"
        for r in rows_t[-10:][::-1]
    )
    tele_html = f"""
<section id="telemetry"><div class="wrap">
  {sec_head("07", "Audit trail", "Telemetry")}
  <p class="sub rv">Every model call appends one line to <code>runs.jsonl</code>. Failures are kept: they include rate limits, a retired model name and invalid-parameter errors that were fixed along the way. Counts include development and offline mock runs. Prompts and file paths are not shown here.</p>
  <div class="stat rv">{stat}</div>
  <div class="card rv"><b>Runs per stage</b>
    <div class="bars">{''.join(bars)}</div>
    <div class="legend"><span><i class="s-ok"></i>Generated</span><span><i class="s-cached"></i>From cache</span><span><i class="s-fail"></i>Failed</span><span><i class="s-other"></i>Other</span></div></div>
  <details class="rv"><summary>Breakdown by stage and provider</summary><div class="tablewrap"><table><thead><tr><th>Stage</th><th>Provider</th><th>Status</th><th>Count</th></tr></thead><tbody>{agg}</tbody></table></div></details>
  <details class="rv"><summary>Most recent runs</summary><div class="tablewrap"><table><thead><tr><th>Time (UTC)</th><th>Stage</th><th>Provider</th><th>Model</th><th>Status</th></tr></thead><tbody>{recent}</tbody></table></div></details>
</div></section>"""

    def size_of(rel: str) -> str:
        sz = (ctx["out"] / rel).stat().st_size
        return f"{sz / 1e6:.1f} MB" if sz >= 1e6 else f"{max(1, sz // 1024)} KB"

    def card(label, rel, ext, note):
        return (f'<a class="file rv" href="{rel}" download><span class="ext">{ext}</span><span><b>{label}</b>'
                f'<small>{note}</small><small class="sz">{size_of(rel)}</small></span></a>')

    downloads = f"""
<section id="downloads"><div class="wrap">
  {sec_head("08", "Take it with you", "Downloads")}
  <p class="sub rv">Everything needed to inspect or reproduce the film. The videos are re-encoded for the web from the 1080p masters.</p>
  <div class="files">
    {card("film-16x9.mp4", "films/film-16x9.mp4", "MP4", "Widescreen 1920x1080 with burned-in English captions and the AI end card")}
    {card("film-9x16.mp4", "films/film-9x16.mp4", "MP4", "Vertical 1080x1920 for phones")}
    {card("captions.srt", "assets/captions.srt", "SRT", "English captions, timed to the spoken lines")}
    {card("narration.mp3", "assets/narration.mp3", "MP3", "Amharic narration track, loudness-matched")}
    {card("soundtrack.mp3", "assets/soundtrack.mp3", "MP3", "Synthesised solo guitar score")}
    {card("storyboard.json", "assets/storyboard.json", "JSON", "The single source of truth for the film")}
    {card("storyboard.schema.json", "assets/storyboard.schema.json", "JSON", "JSON Schema the storyboard is validated against")}
    {card("keyframes.zip", "assets/keyframes.zip", "ZIP", "Full-resolution FLUX keyframes and the character sheet")}
    {card("wan_batch.json", "assets/kaggle/wan_batch.json", "JSON", "Batch manifest for the Wan 2.2 notebook")}
    {card("wan2_ti2v_notebook.ipynb", "assets/kaggle/wan2_ti2v_notebook.ipynb", "IPYNB", "Kaggle notebook: image-to-video with Wan 2.2 TI2V-5B")}
    {card("ace_step_music_notebook.ipynb", "assets/kaggle/ace_step_music_notebook.ipynb", "IPYNB", "Kaggle notebook: ACE-Step 1.5 music")}
  </div>
</div></section>"""

    journal_md = (ROOT / "JOURNAL.md").read_text(encoding="utf-8") if (ROOT / "JOURNAL.md").is_file() else "No journal yet."
    journal = (f'<section id="journal"><div class="wrap">{sec_head("09", "Honest account", "Journal")}'
               f'<div class="prose journal">{md_to_html(journal_md.replace("# Build Journal", "", 1), "docs/")}</div></div></section>')

    return film + review + storyboard + sound + pipeline + wan + tele_html + downloads + journal


def story_markdown(sb: dict) -> str:
    out = ["# Full narration", "", f"**{sb['film_title']}**", "", "Each line is spoken in Amharic over its shot; the English is the on-screen caption.", ""]
    for i, s in enumerate(sb["shots"], 1):
        out += [f"## Shot {i}", "", f"*{s['scene_description']}*", "", s["narration_amharic"], "", f"> {s['english_translation']}", ""]
    return "\n".join(out)


# --------------------------------------------------------------------------- extras + build

FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#14100c"/>'
           '<path d="M20 16h24v10c0 9-5 15-12 15S20 35 20 26z" fill="#e0a458"/><path d="M44 21h5c3 0 5 2 5 5s-2 5-5 5h-5" '
           'fill="none" stroke="#e0a458" stroke-width="4"/><rect x="16" y="46" width="32" height="4" rx="2" fill="#c97b3a"/></svg>')

VERCEL_JSON = {
    "cleanUrls": True,
    "trailingSlash": False,
    "headers": [
        {"source": "/films/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]},
        {"source": "/img/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]},
        {"source": "/assets/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=86400"}]},
        {"source": "/(.*)", "headers": [
            {"key": "X-Content-Type-Options", "value": "nosniff"},
            {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
        ]},
    ],
}


def write_site_extras(out: Path, ctx: dict) -> None:
    """Files a static host expects: favicon, 404, robots, sitemap (with --url) and vercel.json."""
    (out / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    not_found = shell("Page not found - " + ctx["short_title"],
                      '<section><div class="wrap"><div class="sh"><div><div class="eyebrow">404</div><h2>Page not found</h2></div></div>'
                      '<p class="sub">That page does not exist. <a href="/">Back to the film</a>.</p></div></section>',
                      {**ctx, "films_js": ""}, 0)
    # 404 is served from any path depth, so make its links root-relative
    not_found = (not_found.replace('href="#', 'href="/#').replace('href="docs/', 'href="/docs/')
                 .replace('href="favicon.svg"', 'href="/favicon.svg"'))
    (out / "404.html").write_text(not_found, encoding="utf-8")
    base = ctx.get("base_url", "")
    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {base}/sitemap.xml\n" if base else ""), encoding="utf-8")
    if base:
        urls = [f"{base}/"] + [f"{base}/docs/{s}" for s, _f, _l in DOCS]
        (out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (out / "vercel.json").write_text(json.dumps(VERCEL_JSON, indent=2) + "\n", encoding="utf-8")


def build(out: Path, author: str, repo: str, base_url: str = "") -> None:
    exports = ROOT / "outputs" / "exports"
    keyframes = ROOT / "outputs" / "keyframes"
    sb = json.loads((ROOT / "storyboard.json").read_text(encoding="utf-8"))
    for need in (exports / "film_16x9.mp4", exports / "film_9x16.mp4"):
        if not need.is_file():
            raise SystemExit(f"Missing {need}. Build the film first (python -m pipeline.cli assemble).")

    if out.exists():
        # Build into a sibling folder first, so a locked folder (e.g. a running preview server that has a
        # video open) can never leave a half-deleted site behind.
        probe_dir = out.with_name(out.name + ".old")
        try:
            if probe_dir.exists():
                shutil.rmtree(probe_dir)
            out.rename(probe_dir)
        except OSError:
            raise SystemExit(
                f"Cannot replace {out}: something is using it (most likely a preview server serving that folder).\n"
                f"Stop it with Ctrl+C in its terminal and run this again, or build elsewhere with --out <folder>."
            )
        shutil.rmtree(probe_dir, ignore_errors=True)
    for d in ("films", "img", "docs", "assets/kaggle"):
        (out / d).mkdir(parents=True)

    print("Encoding web copies of the films...")
    films, info = {}, {}
    for aspect, name, size, slug in (("16:9", "film_16x9.mp4", "1920:1080", "16x9"), ("9:16", "film_9x16.mp4", "1080:1920", "9x16")):
        encode(exports / name, out / "films" / f"film-{slug}.mp4", size)
        films[aspect] = {"src": f"films/film-{slug}.mp4"}
        info[aspect] = probe(exports / name)

    print("Preparing images...")
    for s in sb["shots"]:
        kf = keyframes / f"{s['shot_id']}.png"
        if not kf.is_file():
            raise SystemExit(f"Missing keyframe {kf}")
        jpg(kf, out / "img" / f"{s['shot_id']}.jpg", 720)
        jpg(kf, out / "img" / "lg" / f"{s['shot_id']}.jpg", 1400)
    jpg(keyframes / "shot_02.png", out / "img" / "poster.jpg", 1280, 4)
    sheet = next(iter(sorted(keyframes.glob("character_sheet_*.png"))), None)
    if sheet:
        jpg(sheet, out / "img" / "character.jpg", 600)
        jpg(sheet, out / "img" / "lg" / "character.jpg", 1400)

    print("Preparing audio and downloads...")
    for src, dst in (("outputs/narration/full_narration.wav", "narration.mp3"), ("outputs/music/soundtrack.wav", "soundtrack.mp3")):
        sp = ROOT / src
        if not sp.is_file():
            raise SystemExit(f"Missing {sp}")
        r = run("ffmpeg", "-y", "-loglevel", "error", "-i", str(sp), "-c:a", "libmp3lame", "-q:a", "4", str(out / "assets" / dst))
        if r.returncode != 0:
            raise SystemExit(f"ffmpeg failed encoding {dst}: {r.stderr[-300:]}")
    shutil.copy(ROOT / "outputs" / "assembly" / "subtitles.srt", out / "assets" / "captions.srt")
    shutil.copy(ROOT / "storyboard.json", out / "assets" / "storyboard.json")
    shutil.copy(ROOT / "schema" / "storyboard.schema.json", out / "assets" / "storyboard.schema.json")
    for name in ("wan_batch.json", "wan2_ti2v_notebook.ipynb", "ace_step_music_notebook.ipynb"):
        shutil.copy(ROOT / "kaggle" / name, out / "assets" / "kaggle" / name)
    with zipfile.ZipFile(out / "assets" / "keyframes.zip", "w", zipfile.ZIP_STORED) as z:
        for png in sorted(keyframes.glob("*.png")):
            z.write(png, png.name)

    t = run(sys.executable, "-m", "pytest", "--collect-only", "-q", "tests")
    m = re.search(r"(\d+) tests? collected", t.stdout)
    test_count = f"{m.group(1)} automated tests" if m else "an automated test suite"

    chapters_js = f"window.SHOT_SECONDS={float(sb['shots'][0]['duration'])};"
    ctx = {
        "author": author, "repo": repo, "year": datetime.date.today().year,
        "short_title": "Taste of Heritage" if "Taste of Heritage" in sb["film_title"] else sb["film_title"],
        "desc": sb["story_description"][:300],
        "films_js": "window.FILMS=" + json.dumps(films) + ";" + chapters_js,
        "out": out, "base_url": base_url.rstrip("/"),
    }
    tele = telemetry()
    body = build_sections(ctx, sb, films, info, tele, test_count)
    (out / "index.html").write_text(shell(sb["film_title"], body, ctx, 0), encoding="utf-8")

    doc_ctx = {**ctx, "films_js": ""}
    for slug, filename, label in DOCS:
        md = story_markdown(sb) if filename is None else (ROOT / filename).read_text(encoding="utf-8")
        note = ""
        if filename is not None and slug != "KAGGLE":
            note = ('<div class="notice"><b>Read this as design intent.</b> This document describes what the project set out to do. '
                    'What the delivered film actually uses (synthesised guitar instead of ACE-Step, FFmpeg camera moves instead of Wan 2.2, '
                    'no native-speaker review of the Amharic) is stated in <a href="../index.html#review">For reviewers</a>.</div>')
        content, toc = with_toc(md_to_html(md, ""))
        page = (f'<section style="padding-top:44px"><div class="wrap"><div class="eyebrow" style="margin-bottom:14px">Document</div>{note}'
                f'<div class="docgrid"><div class="prose">{content}</div>{toc}</div></div></section>')
        (out / "docs" / f"{slug}.html").write_text(shell(f"{label} - {ctx['short_title']}", page, doc_ctx, 1, slug), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    write_site_extras(out, doc_ctx)

    for f in out.rglob("*"):
        if f.is_file() and f.suffix in (".html", ".js", ".json", ".css", ".ipynb", ".srt", ".xml", ".svg", ".txt"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if re.search(pat, text):
                    raise SystemExit(f"Refusing to publish: {f} contains something that looks like a secret ({pat}).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the public project site from outputs/")
    ap.add_argument("--out", default="site")
    ap.add_argument("--author", default="", help="Shown in the footer (optional)")
    ap.add_argument("--repo", default="", help="Link to the source repository (optional)")
    ap.add_argument("--url", default="", help="Final public URL, e.g. https://your-film.vercel.app (enables share image + sitemap)")
    a = ap.parse_args()
    out = ROOT / a.out
    build(out, a.author.strip(), a.repo.strip(), a.url.strip())
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"\nSite ready in {out} ({size / 1e6:.1f} MB)")
    print(f"Preview:  python -m http.server 8090 --directory {a.out}   then open http://127.0.0.1:8090")


if __name__ == "__main__":
    main()
