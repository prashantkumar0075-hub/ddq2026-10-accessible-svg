"""
DataDev Quest #DDQ2026-10 - Accessible SVG Exports with AI
=========================================================

One script that, for every value of a filter (default: Region):

  1. EXPORT   - downloads the same Tableau view as PNG and as SVG (REST API 3.29+)
  2. DESCRIBE - sends the PNG to Claude and gets back JSON: {"alt", "summary"}
  3. REVIEW   - saves the AI draft to a JSON file so a PERSON can check / fix it
  4. SHIP     - writes the text into the SVG (<title>, <desc>, role, aria-labelledby,
                lang) WITHOUT touching a single byte of the drawing

Sub-commands
------------
  run      Full pipeline against Tableau Cloud/Server (export -> describe -> review -> ship)
  local    Same pipeline but from PNG/SVG files you already have (no Tableau needed)
  inject   Only step 4: put text you wrote yourself into an SVG

Examples
--------
  python ddq_accessible_svg.py run --view "Overview" --regions West East Central South
  python ddq_accessible_svg.py local --png sample.png --svg sample.svg --langs en es
  python ddq_accessible_svg.py inject --svg in.svg --alt "..." --summary "..." -o out.svg
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional .env support (TABLEAU_* and ANTHROPIC_API_KEY live there)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
API_VERSION = "3.29"  # first REST API version with ?format=SVG on Query View Image


# ===========================================================================
# STEP 1 - EXPORT (Tableau REST API via TSC + plain requests for SVG)
# ===========================================================================
def tableau_sign_in():
    """Sign in with a Personal Access Token and return a signed-in TSC.Server."""
    import tableauserverclient as TSC

    server = TSC.Server(os.environ["TABLEAU_SERVER_URL"], use_server_version=True)
    auth = TSC.PersonalAccessTokenAuth(
        os.environ["TABLEAU_PAT_NAME"],
        os.environ["TABLEAU_PAT_SECRET"],
        site_id=os.getenv("TABLEAU_SITE", ""),  # the site *content URL*, "" = Default
    )
    server.auth.sign_in(auth)

    # SVG needs REST API 3.29 (Tableau 2026.2). Warn early if the server is older.
    if tuple(map(int, server.version.split("."))) < (3, 29):
        print(f"WARNING: server speaks REST API {server.version}; SVG export needs 3.29+.")
    return server


def find_view(server, view_name: str, workbook_name: str | None = None):
    """Find a view by name (and optionally by workbook name)."""
    import tableauserverclient as TSC

    opts = TSC.RequestOptions()
    opts.filter.add(TSC.Filter(TSC.RequestOptions.Field.Name, TSC.RequestOptions.Operator.Equals, view_name))
    views, _ = server.views.get(opts)
    if workbook_name:
        views =[v for v in views if server.workbooks.get_by_id(v.workbook_id).name == workbook_name]
    if not views:
        sys.exit(f"View '{view_name}' not found on this site.")
    return views[0]


def export_view(server, view, out_dir: Path, filter_field: str | None, value: str | None) -> tuple[Path, Path]:
    """
    Download the view as PNG and SVG, optionally filtered with ?vf_<field>=<value>.

    GET /api/3.29/sites/{site}/views/{view}/image                      -> PNG
    GET /api/3.29/sites/{site}/views/{view}/image?format=SVG&vf_Region -> SVG
    """
    import requests

    tag = slug(value) if value else "all"
    png_path, svg_path = out_dir / f"{tag}.png", out_dir / f"{tag}.svg"

    url = f"{server.server_address.rstrip('/')}/api/{API_VERSION}/sites/{server.site_id}/views/{view.id}/image"
    headers = {"X-Tableau-Auth": server.auth_token}
    base_params = {"resolution": "high"}
    if filter_field and value:
        base_params[f"vf_{filter_field}"] = value  # view filter -> different numbers per Region

    for fmt, path in (("PNG", png_path), ("SVG", svg_path)):
        params = dict(base_params)
        if fmt == "SVG":
            params["format"] = "SVG"
        r = requests.get(url, headers=headers, params=params, timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
        print(f"  exported {fmt}: {path}  ({len(r.content):,} bytes)")

    # Peek at what Tableau itself wrote in <title>/<desc> (spoiler: a placeholder)
    head = svg_path.read_text(encoding="utf-8", errors="replace")[:2000]
    t = re.search(r"<title[^>]*>(.*?)</title>", head, re.S)
    d = re.search(r"<desc[^>]*>(.*?)</desc>", head, re.S)
    print(f"  Tableau's own <title>: {t.group(1).strip() if t else '(none)'!r}  <desc>: {d.group(1).strip() if d else '(none)'!r}")
    return png_path, svg_path


# ===========================================================================
# STEP 2 - DESCRIBE (Claude vision -> structured JSON)
# ===========================================================================
PROMPT = """You are writing accessibility text for a Tableau dashboard image.
{context}
Write, for each language code in {langs}:
- "alt": alt text, UNDER 150 characters, saying what the chart shows and the single most important takeaway.
- "summary": exactly three sentences: what the dashboard is, the key numbers (only numbers you can actually read in the image), and the main insight.
Do not invent numbers. If a value is unreadable, describe it qualitatively."""


def describe_png(png_path: Path, langs: list[str], context: str = "") -> dict:
    """Send the PNG to Claude and get {lang: {"alt": ..., "summary": ...}} back."""
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY (or an `ant auth login` profile)

    # JSON schema the answer MUST follow (structured outputs => always valid JSON)
    per_lang = {
        "type": "object",
        "properties": {"alt": {"type": "string"}, "summary": {"type": "string"}},
        "required": ["alt", "summary"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {lang: per_lang for lang in langs},
        "required": langs,
        "additionalProperties": False,
    }

    image_b64 = base64.standard_b64encode(png_path.read_bytes()).decode()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                    {"type": "text", "text": PROMPT.format(context=context, langs=", ".join(langs))},
                ],
            }
        ],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined: {response.stop_details}")

    text = next(b.text for b in response.content if b.type == "text")
    result = json.loads(text)

    # Enforce the 150-character rule in code - never trust, always verify.
    for lang, block in result.items():
        if len(block["alt"]) > 150:
            print(f"  NOTE: {lang} alt text is {len(block['alt'])} chars, trimming to 150.")
            block["alt"] = block["alt"][:147].rstrip() + "..."
    return result


# ===========================================================================
# STEP 3 - REVIEW (a person checks the AI draft)
# ===========================================================================
def human_review(drafts_file: Path, auto_yes: bool) -> dict:
    """The AI drafts; a person checks. Pause so the reviewer can edit the JSON."""
    if not auto_yes:
        print("\n" + "=" * 70)
        print(f"REVIEW: open {drafts_file}")
        print("Compare every number with the PNG next to it, fix anything wrong, save.")
        input("Press ENTER when the text is approved (Ctrl+C to abort)... ")
    return json.loads(drafts_file.read_text(encoding="utf-8"))


# ===========================================================================
# STEP 4 - SHIP (edit only the top of the SVG, never the drawing)
# ===========================================================================
SVG_OPEN = re.compile(r"<svg\b[^>]*>", re.I | re.S)
# Tableau puts a placeholder <title> and/or <desc> right after <svg ...>
LEADING_TITLE_DESC = re.compile(r"\A(\s*(<title\b[^>]*>.*?</title>|<title\b[^>]*/>|<desc\b[^>]*>.*?</desc>|<desc\b[^>]*/>))+", re.S | re.I)
A11Y_ATTRS = re.compile(r'\s+(role|aria-labelledby|aria-label|lang|xml:lang)\s*=\s*("[^"]*"|\'[^\']*\')', re.I)


def make_accessible(svg_text: str, alt: str, summary: str, lang: str = "en") -> str:
    """
    Return a copy of svg_text with:
        <svg ... role="img" aria-labelledby="alt summary" lang="en">
        <title id="alt">ALT</title>
        <desc id="summary">SUMMARY</desc>
    Everything after Tableau's original <title>/<desc> stays byte-for-byte identical.
    """
    m = SVG_OPEN.search(svg_text)
    if not m:
        raise ValueError("No <svg> root tag found")

    # Pick ids that don't clash with anything already inside the drawing
    alt_id, desc_id = "alt", "summary"
    if re.search(r'\bid\s*=\s*["\'](alt|summary)["\']', svg_text):
        alt_id, desc_id = "ddq-a11y-alt", "ddq-a11y-summary"

    # 1) Rewrite only the opening <svg> tag: drop old a11y attrs, add ours
    open_tag = m.group(0)
    closing = "/>" if open_tag.endswith("/>") else ">"
    inner = A11Y_ATTRS.sub("", open_tag[: -len(closing)])
    new_open = f'{inner} role="img" aria-labelledby="{alt_id} {desc_id}" lang="{lang}"{closing}'

    # 2) Remove Tableau's placeholder <title>/<desc> (only if they lead the content)
    rest = svg_text[m.end():]
    rest = LEADING_TITLE_DESC.sub("", rest, count=1)

    # 3) Insert ours - escaped, so quotes / & / < in the AI text can't break the XML
    a11y = (
        f'\n<title id="{alt_id}">{html.escape(alt, quote=False)}</title>'
        f'\n<desc id="{desc_id}">{html.escape(summary, quote=False)}</desc>'
    )
    result = svg_text[: m.start()] + new_open + a11y + rest

    verify_drawing_untouched(svg_text, result)
    return result


def verify_drawing_untouched(before: str, after: str) -> None:
    """Safety net: XML still parses, and every drawing element is still there."""
    def drawing_tags(text: str) -> list[str]:
        root = ET.fromstring(text.encode("utf-8"))
        return [el.tag for el in root.iter() if not el.tag.endswith(("}title", "}desc")) and el.tag not in ("title", "desc")]

    try:
        b, a = drawing_tags(before), drawing_tags(after)
    except ET.ParseError as e:
        raise ValueError(f"SVG is not valid XML after editing: {e}") from e
    if b != a:
        raise ValueError(f"Drawing changed! {len(b)} elements before, {len(a)} after.")


# ===========================================================================
# Helpers: gallery page, slugs, per-region pipeline
# ===========================================================================
def read_svg(path) -> str:
    """Read text exactly as stored (newline="" keeps original line endings)."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write_svg(path, text: str) -> None:
    """Write text exactly as given - no CRLF conversion on Windows."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "item"


def process_one(png: Path, svg: Path, out_dir: Path, label: str, langs: list[str], auto_yes: bool, context: str) -> dict:
    """describe -> review -> ship for one exported pair."""
    print(f"\n[{label}] asking {MODEL} to describe {png.name} ...")
    drafts = describe_png(png, langs, context)
    drafts_file = out_dir / f"{slug(label)}.descriptions.json"
    drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(drafts, ensure_ascii=False, indent=2))

    approved = human_review(drafts_file, auto_yes)
    primary = langs[0]
    accessible = make_accessible(
        read_svg(svg), approved[primary]["alt"], approved[primary]["summary"], primary
    )
    out_svg = out_dir / f"{slug(label)}.accessible.svg"
    write_svg(out_svg, accessible)
    print(f"  shipped: {out_svg}")
    return {"label": label, "svg": out_svg.name, "png": png.name, "text": approved}


def write_gallery(out_dir: Path, items: list[dict], langs: list[str]) -> Path:
    """An index.html that shows every accessible SVG inline, with a language switch."""
    buttons = "".join(f'<button onclick="setLang(\'{l}\')">{l.upper()}</button>' for l in langs)
    cards = []
    for it in items:
        svg_inline = read_svg(out_dir / it["svg"])
        svg_inline = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>", "", svg_inline)
        texts = html.escape(json.dumps(it["text"], ensure_ascii=False), quote=True)
        cards.append(
            f'<section class="card" data-text="{texts}"><h2>{html.escape(it["label"])}</h2>'
            f'<div class="svg">{svg_inline}</div><p class="sum"></p></section>'
        )
    page = f"""<!doctype html><html lang="{langs[0]}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Accessible SVG Exports</title>
<style>body{{font-family:system-ui;margin:16px;background:#fff;color:#111}}.card{{border:1px solid #ccc;border-radius:8px;padding:12px;margin:16px 0}}
.svg svg{{max-width:100%;height:auto}}button{{margin-right:6px}}</style></head><body>
<h1>Accessible SVG Exports</h1><p>Language: {buttons}</p>{''.join(cards)}
<script>
function setLang(l){{document.documentElement.lang=l;document.querySelectorAll('.card').forEach(c=>{{
 const t=JSON.parse(c.dataset.text)[l]; const s=c.querySelector('svg');
 s.setAttribute('lang',l); s.querySelector('title').textContent=t.alt; s.querySelector('desc').textContent=t.summary;
 c.querySelector('.sum').textContent=t.summary;}});}}
setLang('{langs[0]}');
</script></body></html>"""
    path = out_dir / "index.html"
    path.write_text(page, encoding="utf-8")
    return path


# ===========================================================================
# CLI
# ===========================================================================
def main() -> None:
    p = argparse.ArgumentParser(description="DDQ2026-10: accessible Tableau SVG exports with AI")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Export from Tableau, describe, review, ship")
    run.add_argument("--view", required=True, help="View (sheet/dashboard) name")
    run.add_argument("--workbook", help="Workbook name, if the view name is not unique")
    run.add_argument("--filter-field", default="Region")
    run.add_argument("--regions", nargs="*", default=["Central", "East", "South", "West"],
                     help="Filter values; pass none to export the unfiltered view only")

    loc = sub.add_parser("local", help="Use PNG/SVG files you already exported")
    loc.add_argument("--png", required=True)
    loc.add_argument("--svg", required=True)
    loc.add_argument("--label", default="sample")

    # Two-stage mode: export now, write/approve <Region>.descriptions.json with any AI, then ship.
    exp = sub.add_parser("export", help="Only step 1: export PNG + SVG per filter value")
    exp.add_argument("--view", required=True)
    exp.add_argument("--workbook")
    exp.add_argument("--filter-field", default="Region")
    exp.add_argument("--regions", nargs="*", default=["Central", "East", "South", "West"])

    shp = sub.add_parser("ship", help="Only step 4: write approved <label>.descriptions.json into <label>.svg")
    shp.add_argument("--labels", nargs="+", default=["Central", "East", "South", "West"])

    for sp in (run, loc, exp, shp):
        sp.add_argument("--out", default="output")
    for sp in (run, loc, shp):
        sp.add_argument("--langs", nargs="+", default=["en"], help="e.g. en es  (first = language written in the SVG)")
    for sp in (run, loc):
        sp.add_argument("--yes", action="store_true", help="Skip the pause for human review (not recommended)")

    inj = sub.add_parser("inject", help="Only write your own text into an SVG")
    inj.add_argument("--svg", required=True)
    inj.add_argument("--alt", required=True)
    inj.add_argument("--summary", required=True)
    inj.add_argument("--lang", default="en")
    inj.add_argument("-o", "--output", required=True)

    a = p.parse_args()

    if a.cmd == "inject":
        out = make_accessible(read_svg(a.svg), a.alt, a.summary, a.lang)
        write_svg(a.output, out)
        print(f"Wrote {a.output}")
        return

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = []

    if a.cmd == "export":
        server = tableau_sign_in()
        try:
            view = find_view(server, a.view, a.workbook)
            for value in a.regions or [None]:
                print(f"\n=== {a.filter_field} = {value or 'All'} ===")
                export_view(server, view, out_dir, a.filter_field if value else None, value)
        finally:
            server.auth.sign_out()
        print("\nExported. Write/check each <label>.descriptions.json, then run: ship")
        return

    if a.cmd == "ship":
        primary = a.langs[0]
        for label in a.labels:
            approved = json.loads((out_dir / f"{slug(label)}.descriptions.json").read_text(encoding="utf-8"))
            svg_in = out_dir / f"{slug(label)}.svg"
            out_svg = out_dir / f"{slug(label)}.accessible.svg"
            write_svg(out_svg, make_accessible(read_svg(svg_in), approved[primary]["alt"], approved[primary]["summary"], primary))
            print(f"  shipped: {out_svg}")
            items.append({"label": label, "svg": out_svg.name, "png": f"{slug(label)}.png", "text": approved})
    elif a.cmd == "local":
        items.append(process_one(Path(a.png), Path(a.svg), out_dir, a.label, a.langs, a.yes, ""))
    else:
        server = tableau_sign_in()
        try:
            view = find_view(server, a.view, a.workbook)
            print(f"View: {view.name} ({view.id})")
            for value in a.regions or [None]:
                label = value or "All"
                print(f"\n=== {a.filter_field} = {label} ===")
                png, svg = export_view(server, view, out_dir, a.filter_field if value else None, value)
                ctx = f"The dashboard is filtered to {a.filter_field} = {value}." if value else ""
                items.append(process_one(png, svg, out_dir, label, a.langs, a.yes, ctx))
        finally:
            server.auth.sign_out()

    gallery = write_gallery(out_dir, items, a.langs)
    print(f"\nDone. {len(items)} accessible SVG(s). Open {gallery} in a browser.")


if __name__ == "__main__":
    main()
