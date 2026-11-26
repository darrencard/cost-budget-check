# Is your AI feature within budget?

A free Claude skill that checks each AI feature's spend against its landing brief's cost budget, and names the feature and model behind any drift.

**Why it matters:** a feature can pass its evals and still cost twice what was planned. The budget is two lines, tokens per task and price per token, and this check holds the spend to both, in code, with a source for every figure.

**How it works:** it reads your provider usage CSV or AI gateway logs, prices them with a pricing table that carries its own source and date, and marks each line landed, watch or stalled.

## Install: paste one prompt into Claude Code

```text
Install the cost-budget-check skill from https://github.com/darrencard/cost-budget-check by copying skills/cost-budget-check into ~/.claude/skills/, then run its tests with python3 -m unittest discover -s evals. Then check my AI features against their landing briefs' cost budgets for last month: ask me for the briefs, the usage export or gateway logs, the task counts and a pricing table with its source and date, and show me what drives any drift.
```

Or as a plugin:

```bash
claude plugin marketplace add darrencard/cost-budget-check
```

```bash
claude plugin install cost-budget-check@dacard-cost-budget-check
```

## What you get

| Feature | What it does | What it does for you |
|---|---|---|
| Two-line budget | Reads tokens per task and price per token from each landing brief | The budget you set is the one it checks |
| Figures computed in code | Python computes every figure; each has a ledger row with its formula and sources | Any number traces back to its file in seconds |
| Cache reads priced apart | Prices input, output, cache read and cache write at their own rates, and counts cached tokens once | Price per token reflects what caching really saves |
| Drift and its driver | Splits cost over budget by model so the parts add up, and names the largest | You know which feature and model to look at first |
| No guessed prices | Refuses a model the pricing table does not price, and a table with no source or date | No figure rests on a price from memory |
| The bill | Reconciles priced usage against `finance.csv` from the Product & Technology Leader Report | Spend with no feature tag shows up |
| Summary review | `review.py` blocks invented figures, wrong status words, "within budget" when it is not, and saving claims | What you send says no more than the data |

## Inputs

- **Landing briefs:** one per feature, in the format of `skills/cost-budget-check/assets/landing-brief-template.md`.
- **Usage:** a provider usage CSV (one row per day, model and key), AI gateway logs (JSON Lines, OpenAI-compatible usage), or both, one per feature.
- **Tasks:** a task id on each gateway request, or a `feature,tasks,source` CSV.
- **Prices:** `skills/cost-budget-check/assets/pricing-template.json`, filled from your provider's pricing page or contract.

## Run it by hand

```bash
cd skills/cost-budget-check && python3 scripts/check.py --brief quote-drafter=../../evals/fixtures/acme/briefs/quote-drafter.md --brief invoice-chaser=../../evals/fixtures/acme/briefs/invoice-chaser.md --pricing ../../evals/fixtures/acme/pricing.json --gateway-log ../../evals/fixtures/acme/gateway.jsonl --usage-csv ../../evals/fixtures/acme/usage.csv --tasks ../../evals/fixtures/acme/tasks.csv --finance ../../evals/fixtures/acme/finance.csv --feature-map acme-invoice-chaser=invoice-chaser --feature-map acme-search=search-assist --window 2026-11-01..2026-11-30 --as-of 2026-12-01 --out /tmp/cost-check
```

That runs the Acme fixture: an invented invoicing company for trades businesses. Every figure in it is illustrative.

## Tests

```bash
python3 -m unittest discover -s evals -v
```

Requires Python 3.11 or later. Standard library only; nothing to install. The scripts make no network calls.

## Licence

MIT. See [LICENSE](LICENSE).
