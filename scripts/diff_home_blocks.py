"""Diff home.html vs home_dashboard.html block-by-block."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform"


def extract_content(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"\{% block content %\}\s*(.*?)\s*\{% endblock", text, re.S)
    return m.group(1) if m else ""


def split_blocks(html: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"<!--\s*/?\s*(.+?)\s*-->", re.S)
    parts = []
    last = 0
    names = []
    for m in pattern.finditer(html):
        chunk = html[last : m.start()].strip()
        if chunk:
            parts.append((names[-1] if names else "start", chunk))
        names.append(m.group(1).strip())
        last = m.end()
    tail = html[last:].strip()
    if tail:
        parts.append((names[-1] if names else "end", tail))
    # pair opening comments with following content until next opening
    blocks = []
    i = 0
    comments = re.findall(r"<!--\s*/?\s*(.+?)\s*-->", html)
    segments = re.split(r"(<!--\s*/?[^>]+-->)", html)
    current_name = "preamble"
    buf = []
    for seg in segments:
        cm = re.match(r"<!--\s*/?\s*(.+?)\s*-->", seg.strip()) if seg.strip() else None
        if cm:
            if buf:
                blocks.append((current_name, "".join(buf).strip()))
                buf = []
            name = cm.group(1).strip()
            if not name.startswith("/"):
                current_name = name
        else:
            buf.append(seg)
    if buf:
        blocks.append((current_name, "".join(buf).strip()))
    return blocks


def normalize(html: str) -> str:
    html = re.sub(r"\{\{[^}]+\}\}", "VAR", html)
    html = re.sub(r"\{\%[^%]+\%\}", "", html)
    html = re.sub(r"[\u0400-\u04FF]+", "TXT", html)
    html = re.sub(r"\s+", " ", html).strip()
    return html


dash = extract_content(ROOT / "home_dashboard.html")
home = extract_content(ROOT / "home.html")

db = split_blocks(dash)
hb = split_blocks(home)

print(f"dashboard blocks: {len(db)}, home blocks: {len(hb)}")
for i, ((dn, dc), (hn, hc)) in enumerate(zip(db, hb)):
    same = normalize(dc) == normalize(hc)
    mark = "OK" if same else "DIFF"
    print(f"[{i:02d}] {mark} | dash: {dn[:45]} | home: {hn[:45]}")
    if not same:
        nd, nh = normalize(dc), normalize(hc)
        if len(nd) != len(nh):
            print(f"      len {len(nd)} vs {len(nh)}")
        # first char diff
        for j, (a, b) in enumerate(zip(nd, nh)):
            if a != b:
                print(f"      at {j}: ...{nd[max(0,j-30):j+50]}...")
                print(f"           ...{nh[max(0,j-30):j+50]}...")
                break

if len(db) != len(hb):
  print("BLOCK COUNT MISMATCH")
  for x in db[len(hb):]:
    print("  extra dash:", x[0])
  for x in hb[len(db):]:
    print("  extra home:", x[0])
