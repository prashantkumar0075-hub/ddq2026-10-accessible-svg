# #DDQ2026-10 (Beginner) — Describe a Tableau View with AI

[`describe_view.py`](describe_view.py) signs in with a Personal Access Token, exports one view as **PNG and SVG** through the REST API (3.29+), and asks an AI that can read images for **alt text (150 characters max) and a three-sentence summary** as JSON.

## Run

Setup is the same as the main project: see [`../README.md`](../README.md#setup) (`.env` with your Tableau and Anthropic values).

```powershell
python beginner\describe_view.py --view "Overview"
```

No API credit? Export only, then paste the printed prompt and the PNG into Claude, ChatGPT or Gemini:

```powershell
python beginner\describe_view.py --view "Overview" --no-ai
```

## Step 1 — Export: pixels vs code

| File | Size | What it is |
|---|---|---|
| [`results/view.png`](results/view.png) | 409,791 bytes | pixels: good for an AI to read |
| [`results/view.svg`](results/view.svg) | 790,717 bytes | code: people can open and edit it |

What Tableau wrote in the SVG for screen readers:

```xml
<title>TEMP_0b618jb0s34uxp169k1f201chl5n</title>
<desc>Rendered by Tableau</desc>
```

A screen reader announces that placeholder, which tells the listener nothing about the dashboard.

## Step 2 — Describe

Prompt (the challenge brief's prompt, plus two rules that keep the AI from inventing numbers):

```
Write alt text under 150 characters and a three-sentence summary of this dashboard.
Use only numbers you can read in the image, copied exactly as shown. Describe what colors mean, not just their names.
Return JSON with the keys "alt" and "summary".
```

Result ([`results/description.json`](results/description.json)):

```json
{
  "alt": "Superstore profitability dashboard, all regions: $2,326,534 sales, $292,297 profit, 12.6% profit ratio across North America.",
  "summary": "This executive dashboard shows Superstore profitability for all regions, orders from 1/3/2023 to 12/30/2026. Sales total $2,326,534 and profit $292,297, a 12.6% profit ratio, with a 15.54% average discount on 38,654 items. Most states and provinces are profitable, but Oregon, Colorado, Arizona, Texas, Illinois, Ohio, Pennsylvania, Tennessee, North Carolina, Florida and Nova Scotia have a negative profit ratio."
}
```

## The AI drafts; a person checks

The script lists every number in the answer so you can tick them off against the dashboard:

| Number | On the dashboard | OK |
|---|---|---|
| $2,326,534 | Sales tile | ✅ |
| $292,297 | Profit tile | ✅ |
| 12.6% | Profit Ratio tile | ✅ |
| 15.54% | Avg. Discount tile | ✅ |
| 38,654 | Quantity tile | ✅ |
| 1/3/2023 – 12/30/2026 | Order Date filter | ✅ |

Cross-check: the four Region exports in the Intermediate solution add up to the same totals ($503,171 + $691,828 + $391,722 + $739,814 = $2,326,535, within $1 of rounding).

**Next level:** the [Intermediate solution](../README.md) writes this text into the SVG (`<title>`, `<desc>`, `role`, `aria-labelledby`, `lang`) for every Region.
