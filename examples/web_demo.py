#!/usr/bin/env python
"""Serve the demos as local web pages (standard library only).

    python examples/web_demo.py          # then open http://localhost:8000

/            re-runs examples/demo.py and shows one card per milestone
/msme        browses the synthetic MSME underwriting dataset (see msme_explorer.py)
"""

from __future__ import annotations

import html
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

import msme_explorer

DEMO = Path(__file__).resolve().parent / "demo.py"
PORT = int(os.environ.get("PORT", "8000"))
RULE = "=" * 70

STYLE = """
  :root { --bg:#f3f9f5; --card:#ffffff; --fg:#14281d; --muted:#5d7466; --accent:#15803d; --accent-2:#22a05a;
          --accent-soft:#e3f4e9; --border:#d6eadc; --head:#0f6b33; --head-2:#15803d; --on-head:#ffffff;
          --ok:#166534; --ok-bg:#dcf5e4; --warn:#8a5a00; --warn-bg:#fff4d6; --bad:#b42318; --bad-bg:#fde8e6;
          --info:#0f6e6e; --info-bg:#dff3f2; --track:#edf5ef; --shadow:0 1px 2px rgba(16,64,36,.06), 0 4px 14px rgba(16,64,36,.06); }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0d1a12; --card:#13241a; --fg:#e4f2e8; --muted:#94b3a0; --accent:#4ade80; --accent-2:#34c46d;
            --accent-soft:#183a26; --border:#24412f; --head:#0b3d20; --head-2:#11542c; --on-head:#ffffff;
            --ok:#86efac; --ok-bg:#163a24; --warn:#f3cc74; --warn-bg:#3a2f12; --bad:#ff958a; --bad-bg:#3d1b18;
            --info:#7ddad6; --info-bg:#123534; --track:#1a3123; --shadow:none; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 "Segoe UI", system-ui, -apple-system, sans-serif; }
  main { max-width:1180px; margin:0 auto; padding:0 16px 56px; }

  /* Green top bar */
  .topbar { margin:0 -16px 28px; background:linear-gradient(120deg, var(--head), var(--head-2)); color:var(--on-head);
            box-shadow:0 2px 10px rgba(15,107,51,.25); }
  .topbar-in { max-width:1180px; margin:0 auto; padding:12px 16px; display:flex; flex-wrap:wrap; gap:12px 24px; align-items:center; justify-content:space-between; }
  .brand { display:flex; align-items:center; gap:10px; color:var(--on-head); text-decoration:none; font-weight:600; font-size:17px; }
  .brand small { display:block; font-weight:400; font-size:12px; opacity:.85; }
  .logo { display:grid; place-items:center; width:36px; height:36px; border-radius:10px; background:#fff; color:var(--head); font-weight:700; font-size:14px; }
  nav { display:flex; flex-wrap:wrap; gap:6px; }
  nav a { padding:7px 14px; border-radius:999px; color:var(--on-head); opacity:.9; text-decoration:none; font-size:14px; transition:background .15s; }
  nav a:hover { background:rgba(255,255,255,.15); opacity:1; }
  nav a.on { background:#fff; color:var(--head); opacity:1; font-weight:600; }

  h1 { margin:0 0 4px; font-size:28px; letter-spacing:-.01em; }
  .sub { color:var(--muted); margin-bottom:22px; }
  .sub2 { color:var(--muted); font-size:12px; }
  a { color:var(--accent); text-decoration-thickness:1px; text-underline-offset:2px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px 22px; margin-bottom:18px; min-width:0; box-shadow:var(--shadow); }
  .card h2 { margin:0 0 12px; font-size:16px; color:var(--fg); display:flex; align-items:center; gap:8px; }
  .card h2::before { content:""; width:4px; height:18px; border-radius:4px; background:var(--accent-2); }
  pre { margin:0; white-space:pre-wrap; word-break:break-word; font:13px/1.6 ui-monospace, Consolas, monospace; }
  code { font:12px ui-monospace, Consolas, monospace; background:var(--accent-soft); color:var(--fg); padding:2px 6px; border-radius:5px; }
  details { color:var(--muted); } summary { cursor:pointer; color:var(--accent); font-weight:500; }
  .err { border-color:var(--bad); }
  a.btn, .filters button { display:inline-block; padding:8px 18px; border:0; border-radius:999px; background:var(--accent); color:#fff;
           text-decoration:none; font:inherit; font-weight:600; cursor:pointer; box-shadow:0 2px 6px rgba(21,128,61,.25); transition:background .15s; }
  a.btn { margin-bottom:22px; }
  a.btn:hover, .filters button:hover { background:var(--head); }

  .kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:14px; margin-bottom:18px; }
  .kpi { background:var(--card); border:1px solid var(--border); border-top:4px solid var(--accent-2); border-radius:14px; padding:14px 16px; box-shadow:var(--shadow); }
  .kpi .k { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  .kpi .v { font-size:26px; font-weight:700; color:var(--accent); margin:2px 0; }
  .kpi .s { color:var(--muted); font-size:12px; }
  .bar { display:grid; grid-template-columns:minmax(120px, 300px) 1fr 40px; gap:12px; align-items:center; margin:6px 0; }
  .bar .track { background:var(--track); border-radius:999px; height:12px; }
  .bar .fill { display:block; height:12px; border-radius:999px; background:linear-gradient(90deg, var(--accent-2), var(--accent)); }
  .bar .num { text-align:right; font-variant-numeric:tabular-nums; font-weight:600; } .bar .lbl { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

  .tablewrap { overflow-x:auto; border:1px solid var(--border); border-radius:10px; }
  table { border-collapse:collapse; width:100%; font-size:13.5px; }
  th, td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--border); vertical-align:top; }
  tbody tr:last-child td { border-bottom:0; }
  th { background:var(--accent-soft); color:var(--fg); font-weight:600; white-space:nowrap; font-size:12.5px; }
  tbody tr:nth-child(even) { background:color-mix(in srgb, var(--track) 45%, transparent); }
  tbody tr:hover { background:var(--accent-soft); }
  table.num td:not(:first-child), table.num th:not(:first-child) { text-align:right; font-variant-numeric:tabular-nums; }
  .pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; white-space:nowrap; background:var(--track); }
  .pill.ok { background:var(--ok-bg); color:var(--ok); } .pill.warn { background:var(--warn-bg); color:var(--warn); }
  .pill.bad { background:var(--bad-bg); color:var(--bad); } .pill.info { background:var(--info-bg); color:var(--info); }
  .pill.muted { color:var(--muted); }

  .filters { display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin-bottom:14px; padding:12px; background:var(--accent-soft); border-radius:12px; }
  .filters label { display:flex; flex-direction:column; font-size:12px; font-weight:600; color:var(--muted); gap:4px; }
  .filters select, .filters input { font:inherit; padding:7px 10px; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--fg); min-width:150px; }
  .filters select:focus, .filters input:focus { outline:2px solid var(--accent-2); outline-offset:1px; }
  .filters > a { align-self:center; }
  .pager { margin-top:12px; color:var(--muted); font-size:13px; }
  .pager a { margin-left:8px; font-weight:600; }

  .kv { display:grid; grid-template-columns:minmax(120px, 220px) 1fr; gap:8px 16px; margin:10px 0 0; }
  .kv dt { color:var(--muted); } .kv dd { margin:0; min-width:0; overflow-wrap:anywhere; }
  .grid2 { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:0 18px; }
  .decision { border-left:5px solid var(--accent-2); }
  .decision .row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; } .arrow { color:var(--muted); }
  .notes { list-style:none; padding:0; margin:0; }
  .notes li { padding:10px 0 10px 16px; border-left:2px solid var(--border); position:relative; margin-left:6px; }
  .notes li::before { content:""; position:absolute; left:-6px; top:15px; width:10px; height:10px; border-radius:50%; background:var(--accent-2); }
  .facts { margin-top:6px; display:flex; flex-wrap:wrap; gap:4px; }
  .back { display:inline-block; margin-bottom:12px; font-weight:600; text-decoration:none; }
  .doclist { columns:2 260px; padding-left:18px; } .doclist li { margin:4px 0; } .doclist a.on { font-weight:700; }
  .doc blockquote { margin:0 0 14px; padding:10px 14px; border-left:4px solid var(--accent-2); background:var(--accent-soft); border-radius:6px; }
  @media (max-width:600px) { .kv { grid-template-columns:1fr; } .kv dt { margin-top:6px; } .bar { grid-template-columns:1fr 1fr 32px; }
                             .filters select, .filters input { min-width:0; width:100%; } .filters label { flex:1 1 140px; } }
"""


def layout(title: str, body: str) -> bytes:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>"
            f"<body><main>{body}</main></body></html>").encode("utf-8")


def run_demo() -> tuple[int, str, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, str(DEMO)], capture_output=True, text=True, encoding="utf-8", env=env)
    return proc.returncode, proc.stdout, proc.stderr


def to_cards(stdout: str, stderr: str, code: int) -> str:
    # demo.py prints each section as: RULE / title / RULE / body...
    parts = stdout.split(RULE)
    cards = []
    for i in range(1, len(parts) - 1, 2):
        title, body = parts[i].strip(), parts[i + 1].strip()
        body_html = f"<pre>{html.escape(body)}</pre>" if body else ""
        cards.append(f'<section class="card"><h2>{html.escape(title)}</h2>{body_html}</section>')
    if stderr.strip():
        cls = "card err" if code else "card"
        cards.append(
            f'<section class="{cls}"><details{" open" if code else ""}><summary>Agent event log (stderr)</summary>'
            f"<pre>{html.escape(stderr.strip())}</pre></details></section>"
        )
    return "\n".join(cards)


def demo_page() -> tuple[str, str]:
    code, out, err = run_demo()
    body = (msme_explorer.nav("/") + "<h1>Wealth Pilot</h1>"
            f'<div class="sub">Live run of <code>examples/demo.py</code>, offline with the mock LLM. Exit code: {code}</div>'
            '<a class="btn" href="/">Re-run demo</a>' + to_cards(out, err, code))
    return "Wealth Pilot Demo", body


def route(path: str, params: dict[str, str]) -> tuple[str, str] | None:
    if path in ("/", "/index.html"):
        return demo_page()
    if path == "/msme":
        return msme_explorer.overview(params)
    if path == "/msme/queue":
        return msme_explorer.queue()
    if path == "/msme/policies":
        return msme_explorer.policies()
    if path.startswith("/msme/policies/"):
        return msme_explorer.policies(path.rsplit("/", 1)[1])
    if path.startswith("/msme/"):
        return msme_explorer.detail(path.rsplit("/", 1)[1])
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlsplit(self.path)
        page = route(unquote(url.path).rstrip("/") or "/", dict(parse_qsl(url.query)))
        if page is None:
            self.send_error(404)
            return
        body = layout(*page)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Wealth Pilot demo running at http://localhost:{PORT}  (Ctrl+C to stop)")
    print(f"MSME underwriting explorer at  http://localhost:{PORT}/msme")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
