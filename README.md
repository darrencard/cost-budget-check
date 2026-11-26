# Is your AI feature within budget?

A free Claude skill that checks each AI feature's spend against its landing brief's cost budget, and names the feature and model behind any drift.

**Why it matters:** a feature can pass its evals and still cost twice what was planned. The budget is two lines, tokens per task and price per token. This check holds spend to both, in code, with a source for every figure.

**How it works:** it reads your provider usage CSV or AI gateway logs and prices them with a pricing table that carries its own source and date. It marks each line landed, watch or stalled, and shows the change since last period.

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
| Feature        | Line            | Budget      | Actual      | Against budget | Prior       | Since prior | Status  |
| invoice-chaser | Tokens per task | 3,000       | 2,900       | -3.3%          | 2,900       | +0.0%       | landed  |
| invoice-chaser | Price per token | $0.00000120 | $0.00000137 | +14.4%         | $0.00000103 | +32.7%      | stalled |
| invoice-chaser | Cost per task   | $0.0036     | $0.0040     | +10.6%         | $0.0030     | +32.7%      | stalled |
| quote-drafter  | Tokens per task | 12,000      | 13,500      | +12.5%         | 11,500      | +17.4%      | stalled |
| quote-drafter  | Price per token | $0.00000400 | $0.00000328 | -17.9%         | $0.00000357 | -8.0%       | landed  |
| quote-drafter  | Cost per task   | $0.0480     | $0.0443     | -7.6%          | $0.0410     | +8.0%       | landed  |

Driver: invoice-chaser on vendor-a/large, $88.29 over budget.
invoice-chaser: 96.0% of tasks succeeded, so cost per successful task is $0.0041.
Bill: $424.20 billed, $372.94 priced from usage, $51.26 not in the usage given.
```

## What you get

| Feature | What it does | What it does for you |
|---|---|---|
| Two-line budget | Reads tokens per task and price per token from each landing brief | The budget you set is the one it checks |
| Figures computed in code | Python computes every figure; each has a ledger row with its formula and sources | Any number traces back to its file in seconds |
| Cache reads priced apart | Prices input, output, cache read and cache write at their own rates, and counts cached tokens once | Price per token reflects what caching really saves |
| Drift and its driver | Splits cost over budget by model so the parts add up, and names the largest; shows each line's change since the prior window | You know which feature and model to look at first |
| No guessed prices | Refuses a model the pricing table does not price, and a table with no source or date; `--write-pricing-template` lists the models to price | No figure rests on a price from memory |
| The bill | Reconciles priced usage against `finance.csv` from the Product & Technology Leader Report | Spend with no feature tag shows up |
| Summary review | `review.py` blocks invented figures, figures borrowed from another feature, wrong status words, "within budget" when it is not, saving claims and the wrong driver | What you send says no more than the data |
| CI gate | `--fail-on stalled` exits 2 | A scheduled job can flag drift before the invoice does |

## What you need

1. A landing brief per feature with `Tokens per task:` and `Price per token:` lines ([template](skills/cost-budget-check/assets/landing-brief-template.md)).
2. A provider usage CSV or AI gateway logs (JSON Lines), with a feature tag, key or workspace per row.
3. A task count: a task id on each gateway request, or a `feature,tasks,start,end,source` CSV. Add `succeeded` for cost per successful task.
4. Prices from your provider's pricing page or contract. `--write-pricing-template pricing.json` writes the table to fill.

## Tests

```bash
python3 -m unittest discover -s evals -v
```

Requires Python 3.9 or later, so the macOS system Python works. Standard library only; nothing to install. The scripts make no network calls.

## Licence

MIT. See [LICENSE](LICENSE).
