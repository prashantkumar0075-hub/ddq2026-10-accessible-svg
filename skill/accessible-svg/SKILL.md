---
name: accessible-svg
description: Make a Tableau view's SVG export accessible to screen readers. Use when the user wants alt text / descriptions for a Tableau dashboard image, or one accessible SVG per filter value (e.g. per Region).
---

# Accessible SVG exports from Tableau

## Steps

1. **Get the images.** If Tableau MCP is connected, call `get-view-image` for the view (once per filter value, e.g. `Region=West`) as PNG, and download the SVG with
   `GET /api/3.29/sites/{site}/views/{view}/image?format=SVG&vf_Region=<value>`.
   Otherwise ask the user to upload the PNG and SVG.
2. **Describe the PNG.** Look at the PNG and write, for each requested language:
   - `alt`: under 150 characters, what the chart shows plus the key takeaway
   - `summary`: exactly three sentences, using only numbers you can read in the image
   Return it as JSON: `{"en": {"alt": "...", "summary": "..."}}`.
3. **Show the draft to the user and ask them to check the numbers.** Do not ship until they approve.
4. **Edit the SVG with code, never by rewriting it yourself** (Tableau SVGs are large; rewriting can drop parts of the drawing):
   ```
   python ddq_accessible_svg.py inject --svg <in.svg> --alt "<alt>" --summary "<summary>" --lang en -o <out.svg>
   ```
5. Remind the user: if the SVG is embedded with `<img>`, also set `alt="..."` on the tag.
