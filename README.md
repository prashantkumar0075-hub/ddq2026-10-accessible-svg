# #DDQ2026-10 — Accessible SVG Exports with AI

Turns Tableau's SVG export into an image a screen reader can describe — one accessible SVG **per Region**, in one script.

This repo holds both levels of the challenge:
- **Beginner** — export one view as PNG + SVG and describe it with AI: [`beginner/`](beginner/README.md)
- **Intermediate** — write the AI text into the SVG for every Region: this page

| Format | Goes to | Why |
|---|---|---|
| PNG | the AI (Claude) | pixels are easy for a vision model to read |
| SVG | people | it's code, so we can add `<title>`, `<desc>`, `role`, `aria-labelledby`, `lang` |

## Demo video

<!-- Replace VIDEO_ID with your YouTube video id -->
[![Watch the demo](https://img.youtube.com/vi/VIDEO_ID/0.jpg)](https://www.youtube.com/watch?v=VIDEO_ID)

## How it works

1. **Export** — `GET /api/3.29/sites/{site}/views/{view}/image` (PNG) and `...?format=SVG`, each with `&vf_Region=<value>`.
2. **Describe** — the PNG goes to Claude with a JSON schema (structured outputs), so the answer is always `{"alt": "...", "summary": "..."}` per language. Alt text is capped at 150 chars in code.
3. **Review** — the draft is saved to `output/<Region>.descriptions.json`; the script pauses so a person checks the numbers against the PNG.
4. **Ship** — code (not the AI) edits only the top of the SVG:
   ```xml
   <svg ... role="img" aria-labelledby="alt summary" lang="en">
   <title id="alt">ALT TEXT</title>
   <desc id="summary">SUMMARY</desc>
   ```
   Tableau's placeholder title/desc are replaced; the drawing is untouched. A safety check re-parses the SVG and confirms every drawing element is still there.
5. **Gallery** — `output/index.html` shows every SVG inline with a language switch (EN / ES …).

## Setup

Requires Python 3.13+, Tableau Server 2026.2+ / Tableau Cloud (REST API 3.29) for SVG, and an Anthropic API key.

```powershell
git clone https://github.com/<you>/ddq2026-10-accessible-svg
cd ddq2026-10-accessible-svg
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then edit .env
```

Create a Personal Access Token in Tableau: **My Account Settings → Personal Access Tokens**.

## Run

Every Region of a Superstore dashboard, in English and Spanish:

```powershell
python ddq_accessible_svg.py run --view "Overview" --regions Central East South West --langs en es
```

No Tableau site? Use the challenge's sample infographic (PNG + SVG):

```powershell
python ddq_accessible_svg.py local --png sample.png --svg sample.svg --langs es en
```

Only add text you wrote by hand:

```powershell
python ddq_accessible_svg.py inject --svg in.svg --alt "Sales by region..." --summary "Three sentences." -o out.svg
```

Flags: `--filter-field` (default `Region`), `--out` (default `output`), `--yes` (skip the review pause — not recommended).

## Output

```
output/
  West.png  West.svg                  <- raw Tableau exports
  West.descriptions.json              <- AI draft, edited by a human
  West.accessible.svg                 <- the deliverable
  index.html                          <- gallery with language switch
```

> Embedding with `<img src="West.accessible.svg">`? Browsers ignore the inner `<title>`, so also set `alt="..."` on the `<img>`.

## Extra challenge — Claude Skill

`skill/accessible-svg/SKILL.md` packages the prompt and script as a Claude Skill. With Tableau MCP connected, Claude can fetch the images itself, then calls the script's `inject` step. A person still reviews the text before shipping.

## Results (Superstore "Overview" dashboard, Tableau Cloud)

Tableau's own SVG export shipped with `<title>TEMP_0wsolca0sagx8w1f4o2ls1o5v8sr</title>` and `<desc>Rendered by Tableau</desc>`, which mean nothing to a screen reader. After this script:

| Region | Alt text (`<title>`) |
|---|---|
| Central | Central region profitability dashboard: $503,171 sales, $39,865 profit, 7.9% profit ratio, the lowest of the four regions. |
| East | East region profitability dashboard: $691,828 sales, $94,883 profit, 13.7% profit ratio; Ohio and Pennsylvania lose money. |
| South | South region profitability dashboard: $391,722 sales, the lowest of the four regions, $46,749 profit, 11.9% profit ratio. |
| West | West region profitability dashboard: $739,814 sales, $110,799 profit, 15.0% profit ratio, the highest of the four regions. |

Every number was checked against the exported PNG before shipping. Files: [`results/`](results/) — open `results/index.html` for the gallery with the EN/ES switch.

## The universal prompt

[`prompts/universal_prompt.md`](prompts/universal_prompt.md) is one prompt for any chart, dashboard or infographic, in any language, for any vision model (Claude, ChatGPT, Gemini). The script loads it from that file, so you can improve the prompt without touching code. Copy the text between the markers to use it in a chat app.

What makes it reliable:
- **No invented numbers:** numbers are copied exactly from the image, never calculated, and the model returns them in `numbers_used`. The script flags any number in the text that is missing from that list (`CHECK: en: 22% is not in numbers_used`), so the reviewer knows what to check first.
- **Screen-reader friendly:** colors are described by meaning ("negative profit ratio"), not by name ("orange").
- **Same structure every time:** alt text up to 150 characters, plus a 3-sentence summary covering scope, key numbers and insight.
- **Comparisons only when given:** cross-region claims ("highest of the four regions") come only from the `{context}` you pass in.

## Two-stage mode (any AI, or no API credit)

```powershell
python ddq_accessible_svg.py export --view "Overview"     # step 1: PNG + SVG per Region
# write / review output\<Region>.descriptions.json with any AI (Claude, Gemini, ChatGPT...)
python ddq_accessible_svg.py ship --langs en es           # step 4: inject + gallery
```
