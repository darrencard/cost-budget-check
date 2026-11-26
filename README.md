# Is your AI feature within budget?

A free Claude skill that checks each AI feature's spend against its landing brief's cost budget, and names the feature and model behind any drift.

**Why it matters:** a feature can pass its evals and still cost twice what was planned. The budget is two lines, tokens per task and price per token. This check holds spend to both, in code, with a source for every figure.

**How it works:** it reads live usage (the Anthropic usage report, Vercel AI Gateway, agent run records) or a CSV, and prices it with a pricing table that carries its own source and date. It marks each line within budget or over budget, shows the change since last period, and renders one page for leaders.

**Part of the Landing Loop:** it reads the brief with the Product & Technology Leader Report's own parser and writes the `cost` key of `landing/<bet>.json`, which the report reads.

## Install: paste one prompt into Claude Code

```text
Install the cost-budget-check skill from https://github.com/darrencard/cost-budget-check by copying skills/cost-budget-check into ~/.claude/skills/. Run its demo with python3 scripts/check.py --demo --out /tmp/cost-demo from the skill folder and show me the result. Then check my AI features against their landing briefs' cost budgets for last month against the month before: ask me only for what you cannot find (the briefs, the usage export or gateway logs, the task counts, and a pricing table with its source and date), and tell me what drives any drift.
```

Or as a plugin:

```bash
claude plugin marketplace add darrencard/cost-budget-check
```

```bash
claude plugin install cost-budget-check@dacard-cost-budget-check
```

## What you see

From the bundled sample, `python3 scripts/check.py --demo` (Acme is an invented company; every figure is illustrative):

```text
| Feature        | Line            | Budget      | Actual      | Against budget | Prior       | Since prior | Status        |
| invoice-chaser | Tokens per task | 3,000       | 2,900       | -3.3%          | 2,900       | +0.0%       | within budget |
| invoice-chaser | Price per token | $0.00000120 | $0.00000137 | +14.4%         | $0.00000103 | +32.7%      | over budget   |
| invoice-chaser | Cost per task   | $0.0036     | $0.0040     | +10.6%         | $0.0030     | +32.7%      | over budget   |
| quote-drafter  | Tokens per task | 12,000      | 13,500      | +12.5%         | 11,500      | +17.4%      | over budget   |
| quote-drafter  | Price per token | $0.00000400 | $0.00000328 | -17.9%         | $0.00000357 | -8.0%       | within budget |
| quote-drafter  | Cost per task   | $0.0480     | $0.0443     | -7.6%          | $0.0410     | +8.0%       | within budget |

Driver: invoice-chaser on vendor-a/large, $88.29 over budget.
invoice-chaser: 96.0% of tasks succeeded, so cost per successful task is $0.0041.
Bill: $424.20 billed, $372.94 priced from usage, $51.26 not in the usage given.
```

## Sample

[examples/acme/cost-budget-check.html](examples/acme/cost-budget-check.html) follows Acme's `quote-drafting` bet through the Landing Loop. It uses the canonical brief, copied unchanged into `examples/acme/briefs/`, and two weeks of gateway usage with drift: tokens per task, price per token and cost per task all over budget, driver `vendor-a/xl`. The page has a Markdown twin (`cost-budget-check.md`), and `examples/acme/landing/quote-drafting.json` holds only the `cost` key. Every figure is illustrative.

Regenerate it from the repository root (a test checks this command reproduces the committed files byte for byte):

```bash
python3 skills/cost-budget-check/scripts/check.py --brief quote-drafting=examples/acme/briefs/quote-drafting.md --pricing examples/acme/inputs/pricing.json --gateway-log examples/acme/inputs/gateway.jsonl --window 2026-11-01..2026-11-14 --prior-window 2026-10-18..2026-10-31 --as-of 2026-11-15 --out examples/acme --stem cost-budget-check --landing examples/acme/landing --bet quote-drafting=quote-drafting
```

`evals/make_sample.py` writes the sample's inputs.

## What you get

| Feature | What it does | What it does for you |
|---|---|---|
| Two-line budget | Reads tokens per task and price per token from each landing brief, with the Leader Report's own parser | The budget you set is the one it checks |
| Live data first | Reads the Anthropic usage and cost reports, Vercel AI Gateway usage and agent run records as the APIs return them; CSV as the fallback; no keys stored | No export to build before the first check |
| One page for leaders | A self-contained HTML page in the Leader Report's style, with a Markdown twin | Ready to send, with the evidence ledger inside |
| Landing Loop record | Writes only the `cost` key of `landing/<bet>.json`, every figure with value, unit, source, window and date | The Leader Report and the other loop skills read the same figures |
| Figures computed in code | Python computes every figure; each has a ledger row with its formula and sources | Any number traces back to its file in seconds |
| Cache reads priced apart | Prices input, output, cache read and cache write at their own rates, and counts cached tokens once | Price per token reflects what caching really saves |
| Drift and its driver | Splits cost over budget by model so the parts add up, and names the largest; shows each line's change since the prior window | You know which feature and model to look at first |
| No guessed prices | Refuses a model the pricing table does not price, and a table with no source or date; `--write-pricing-template` lists the models to price | No figure rests on a price from memory |
| The bill | Reconciles priced usage against `finance.csv` from the Product & Technology Leader Report | Spend with no feature tag shows up |
| Summary review | `review.py` blocks invented figures, figures borrowed from another feature, wrong status words (and landed, watch or stalled, which are did-it-land's), "within budget" when it is not, saving claims and the wrong driver | What you send says no more than the data |
| CI gate | `--fail-on over-budget` exits 2 (`--tolerance` lets a small overrun through) | A scheduled job can flag drift before the invoice does |

## What you need

1. A landing brief per feature with `Tokens per task:` and `Price per token:` lines ([template](skills/cost-budget-check/assets/landing-brief-template.md)).
2. Usage: the Anthropic usage report, Vercel AI Gateway usage, agent run records, a provider usage CSV or gateway logs, with a feature tag, key or workspace per row.
3. A task count: a task id on each gateway request, or a `feature,tasks,start,end,source` CSV. Add `succeeded` for cost per successful task.
4. Prices from your provider's pricing page or contract. `--write-pricing-template pricing.json` writes the table to fill.

## Tests

```bash
python3 -m unittest discover -s evals -v
```

Requires Python 3.9 or later, so the macOS system Python works. Standard library only; nothing to install. The scripts make no network calls.

## Licence

MIT. See [LICENSE](LICENSE).
