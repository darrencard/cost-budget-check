# Changelog

## 0.3.2, 2026-11-27

- The HTML page follows the Landing Loop sample anatomy: the shared header (mark, DACARD, skill, date, version, blue Illustrative tag), the verdict as the heading ("Quote drafting is $1.89 over its cost budget, and the large model drives the largest part."), the budget word, the signature picture, one next step with the brief's decider in brass and a due date, then each line against the budget beside where the money went, in two columns. Model ids, line keys, files, flags, the record key and the evidence ledger fold under "For your engineers".
- The signature picture: each budget line (AI usage per task, AI price per unit, cost per task) as a bar against its budget notch, the part over hatched, an open dot for the period before, and the cost over budget split by model with the largest part in ink. A 720 wide variant for desktop and a 340 wide one for phones; labels are 11px mono, so the old page's small track labels are gone; the aria-label states the verdict. Drawn with svgkit, vendored byte-identical from landing-loop and pinned in `scripts/vendor/VENDORED.json` under `landing-loop`.
- Public copy in plain words, on the page and in the Markdown twin: project, AI usage per task, AI price per unit, cheaper repeat reads, the landing brief defined at first use. Models are named by price: the dearest is "the large model" (`vendor-a/xl` in the sample), and its id prints only for engineers. The record's words and keys are unchanged.
- The Illustrative tag is blue (#74A5DA), not grey.
- `cost_check.json` gains `decides` per feature, from the brief, so the next step names who decides.
- Tests: the picture draws only printed figures, states the verdict in its aria-label, and the page paints no status colour; brass is only who decides; public copy uses the plain words and no model id; the vendored svgkit matches its pin.

## 0.3.1, 2026-11-26

- README: install through the Landing Loop bundle (`/plugin marketplace add darrencard/landing-loop`, then `/plugin install cost-budget-check@landing-loop`), with the paste-in prompt kept for a standalone install.
- README: the repository is public, so the private-until-review notes are gone, and the loop is counted as eleven skills plus the Product & Technology Leader Report.
- README: one trademark line for Claude and Claude Code.
- README: the plugin lines point at the landing-loop marketplace, not this repository's own.
- No change to what the skill computes. The version in the sample record's `tool` field moves with the release.
- The `--demo` fixture is relabelled as a second, smaller fixture: its features are now `visit-notes` and `quote-follow-up`, so it cannot be read as the quote-drafting bet in the sample. Its next step is decided by the Head of Product, Quoting squad.
- The page names each feature by its brief's title ("Quote drafting"), not its slug; the slug stays in the evidence ledger. `cost_check.json` gains a `title` per feature; the `cost` key of the record is unchanged.
- Text selection and the focus ring print in ink, not the template's green.
- Python 3.11 or later. The entry scripts check the version first and stop with a plain message on anything older.
