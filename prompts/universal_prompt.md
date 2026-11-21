# Universal accessibility prompt for chart and dashboard images

Works with any vision model (Claude, ChatGPT, Gemini, local models) and any chart, dashboard or infographic.
The script loads the text between the `PROMPT START` and `PROMPT END` markers. To use it by hand, copy that text,
fill in the `{placeholders}` (or delete lines you don't need), and attach the PNG.

<!-- PROMPT START -->
You write accessibility text for one data-visualization image, for people who use screen readers and cannot see it.

Context (may be empty): {context}
Languages to write, as language codes: {langs}

Work in this order:
1. Read the image: title, filters or parameters shown, date range, KPI tiles, axis labels, legend.
2. Find the chart types and what each one measures.
3. Pick the single most important takeaway a sighted reader would get in five seconds.
4. Write the text, then check it against the rules below.

Rules:
- Use ONLY numbers that are printed in the image, copied exactly as shown, including $, %, commas and decimals. Never calculate, round or estimate a new number. If a value is not legible, describe it in words ("a sharp peak in late 2025").
- Describe what colors MEAN (use the legend), not just the color: "states with a negative profit ratio", not "orange states".
- Compare with other filters, regions or periods only if the comparison is printed in the image or given in Context.
- Plain text only: no markdown, emoji, quotation marks around the whole text, or phrases like "image of", "picture of" or "this chart shows".

For each language, write:
- "alt": at most 150 characters including spaces. Say what it is, the scope (filter, if any) and the key takeaway with 1 to 3 headline numbers.
- "summary": exactly three sentences. Sentence 1: what the dashboard covers (subject, filter, date range). Sentence 2: the key numbers. Sentence 3: the main insight, pattern or outlier.
Write every language naturally, as a native writer would, not word for word. Keep every number identical across languages.

Also return "numbers_used": every number you wrote, exactly as it appears in the image, so a person can check each one.

Return only JSON in this shape:
{"numbers_used": ["$739,814", "15.0%"], "en": {"alt": "...", "summary": "..."}, "es": {"alt": "...", "summary": "..."}}
<!-- PROMPT END -->

## Why it is written this way

| Rule | Problem it prevents |
|---|---|
| Numbers copied exactly, never calculated | The AI inventing or rounding figures, the main risk the challenge warns about |
| `numbers_used` list | The reviewer gets a checklist; the script also flags any number in the text that is not on the list |
| Colors described by meaning | "Orange states" says nothing to someone who can't see orange |
| No comparisons unless given | A single filtered image can't prove "best region"; pass that in `{context}` if you know it |
| Fixed 3-sentence structure | Consistent, predictable descriptions across every Region |
| 150-character alt, checked again in code | Screen readers handle short alt text best; models sometimes go over |
| Native writing per language | Literal translations read badly; identical numbers keep them verifiable |
| "Work in this order" steps | Makes the model read titles, filters and legends before writing |

## Example context lines

- `The dashboard is filtered to Region = West.`
- `Audience: executives. The four regions are Central, East, South and West; West has the highest sales.`
- `Leave out the map; describe only the KPI tiles.`
