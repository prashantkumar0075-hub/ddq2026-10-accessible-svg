"""
DataDev Quest #DDQ2026-10 (Beginner) - Describe a Tableau View with AI
=====================================================================

What this script does, step by step:

  Step 0  Sign in to Tableau with a Personal Access Token (PAT) and find a view by name.
  Step 1  EXPORT the same view twice with the REST API:
            GET /api/3.29/sites/{site-id}/views/{view-id}/image             -> PNG (pixels)
            GET /api/3.29/sites/{site-id}/views/{view-id}/image?format=SVG  -> SVG (code)
          Then show what Tableau itself wrote in the SVG's <title> and <desc>.
  Step 2  DESCRIBE: send the PNG to an AI that can read images (Claude here) and get JSON back:
            {"alt": "...under 150 characters...", "summary": "...three sentences..."}
          The AI drafts; a person checks the numbers against the dashboard.

Run:
  python beginner/describe_view.py --view "Overview"
  python beginner/describe_view.py --view "Overview" --no-ai   # export only + print a prompt to paste into any AI chat

Settings come from the .env file in the project root (see .env.example).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

import requests
import tableauserverclient as TSC
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")          # TABLEAU_* values and ANTHROPIC_API_KEY
API_VERSION = "3.29"                # SVG export needs REST API 3.29+ (Tableau 2026.2+)

# The prompt from the challenge brief, plus two rules that stop the AI from inventing numbers.
PROMPT = (
    "Write alt text under 150 characters and a three-sentence summary of this dashboard.\n"
    "Use only numbers you can read in the image, copied exactly as shown. "
    "Describe what colors mean, not just their names.\n"
    'Return JSON with the keys "alt" and "summary".'
)


# ---------------------------------------------------------------------------
# Step 0 - sign in and find the view
# ---------------------------------------------------------------------------
def sign_in() -> TSC.Server:
    """Sign in with a Personal Access Token. Returns a signed-in TSC Server object."""
    server = TSC.Server(os.environ["TABLEAU_SERVER_URL"], use_server_version=True)
    auth = TSC.PersonalAccessTokenAuth(
        token_name=os.environ["TABLEAU_PAT_NAME"],
        personal_access_token=os.environ["TABLEAU_PAT_SECRET"],
        site_id=os.environ.get("TABLEAU_SITE", ""),   # the site name from the URL: /#/site/<this>/
    )
    server.auth.sign_in(auth)
    print(f"Signed in. Server speaks REST API {server.version}.")
    return server


def find_view(server: TSC.Server, name: str) -> TSC.ViewItem:
    """Return the first view whose name matches exactly."""
    options = TSC.RequestOptions()
    options.filter.add(TSC.Filter(TSC.RequestOptions.Field.Name, TSC.RequestOptions.Operator.Equals, name))
    views, _ = server.views.get(options)
    if not views:
        sys.exit(f"No view named '{name}' on this site.")
    print(f"Found view '{views[0].name}' (id {views[0].id}).")
    return views[0]


# ---------------------------------------------------------------------------
# Step 1 - export PNG and SVG
# ---------------------------------------------------------------------------
def export(server: TSC.Server, view: TSC.ViewItem, out_dir: Path) -> tuple[Path, Path]:
    """Download the view as PNG and as SVG. Uses plain requests so it works on any TSC version."""
    url = f"{server.server_address.rstrip('/')}/api/{API_VERSION}/sites/{server.site_id}/views/{view.id}/image"
    headers = {"X-Tableau-Auth": server.auth_token}     # the session token from sign-in

    png = out_dir / "view.png"
    png.write_bytes(requests.get(url, headers=headers, params={"resolution": "high"}, timeout=120).content)

    svg = out_dir / "view.svg"
    r = requests.get(url, headers=headers, params={"format": "SVG", "resolution": "high"}, timeout=120)
    r.raise_for_status()                                # fails here on servers older than 2026.2
    svg.write_bytes(r.content)

    print(f"Exported {png} ({png.stat().st_size:,} bytes of pixels)")
    print(f"Exported {svg} ({svg.stat().st_size:,} bytes of code)")

    # The SVG is text, so we can read what Tableau wrote for screen readers
    head = svg.read_text(encoding="utf-8")[:3000]
    title = re.search(r"<title[^>]*>(.*?)</title>", head, re.S)
    desc = re.search(r"<desc[^>]*>(.*?)</desc>", head, re.S)
    print(f"Tableau's <title>: {title.group(1).strip() if title else '(none)'}")
    print(f"Tableau's <desc>:  {desc.group(1).strip() if desc else '(none)'}")
    print("-> A screen reader would read that placeholder. Step 2 fixes the words.\n")
    return png, svg


# ---------------------------------------------------------------------------
# Step 2 - describe the PNG with AI and get JSON back
# ---------------------------------------------------------------------------
def describe(png: Path) -> dict:
    """Ask Claude for {"alt", "summary"}. Structured outputs guarantee valid JSON."""
    import anthropic

    client = anthropic.Anthropic()                      # reads ANTHROPIC_API_KEY from the environment
    schema = {
        "type": "object",
        "properties": {"alt": {"type": "string"}, "summary": {"type": "string"}},
        "required": ["alt", "summary"],
        "additionalProperties": False,
    }
    response = client.messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-opus-5-5"),
        max_tokens=4000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.standard_b64encode(png.read_bytes()).decode()}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    if response.stop_reason == "refusal":
        sys.exit("The model declined this request.")
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def check(result: dict) -> None:
    """Print the checks a person should do. The AI drafts; a person checks."""
    print(f"alt length: {len(result['alt'])} characters (limit 150) "
          f"{'OK' if len(result['alt']) <= 150 else 'TOO LONG'}")
    numbers = re.findall(r"[$€£]?\d[\d,]*(?:\.\d+)?%?", result["alt"] + " " + result["summary"])
    print("Numbers to check against the dashboard:", ", ".join(dict.fromkeys(numbers)) or "(none)")


def main() -> None:
    parser = argparse.ArgumentParser(description="DDQ2026-10 Beginner: export a view and describe it with AI")
    parser.add_argument("--view", required=True, help='View name, e.g. "Overview"')
    parser.add_argument("--out", default=str(ROOT / "beginner" / "output"))
    parser.add_argument("--no-ai", action="store_true", help="Only export; print the prompt for any AI chat")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    server = sign_in()
    try:
        view = find_view(server, args.view)
        png, _ = export(server, view, out_dir)
    finally:
        server.auth.sign_out()                          # always end the session

    if args.no_ai:
        print(f"Attach {png} to Claude, ChatGPT or Gemini with this prompt:\n\n{PROMPT}")
        return

    result = describe(png)
    (out_dir / "description.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    check(result)


if __name__ == "__main__":
    main()
