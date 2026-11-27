# Cost budget check, 2026-11-01 to 2026-11-14

*Illustrative: sample prices, not any provider's list price.*

**Quote drafting is $1.89 over its cost budget, and the large model drives the largest part.**

Each project's AI spend against the cost budget in the landing brief, a one-page plan: what good looks like, by when, at what cost. The budget is two lines, AI usage per task and AI price per unit; multiplied, they give cost per task. From 2026-11-01 to 2026-11-14, each task cost $0.0338 against a budget of $0.0270 (+25.0%).

The period before, for the change in each line: 2026-10-18 to 2026-10-31. As of 2026-11-15.

## What to do next

Review the Quote drafting work sent to the large model ($0.96 of the $1.89 over budget) and the rise in AI usage per task and AI price per unit. Then bring cost per task back under budget, or change the budget in the landing brief, and run this check again. Decides: Head of Product, Quoting squad. Due: 2026-11-29.

## Each line against the budget

| Project | Line | Budget | Actual | Against budget | Before | Since then | Status |
|---|---|---|---|---|---|---|---|
| Quote drafting | AI usage per task | 9,000 | 10,300 | +14.4% | 8,400 | +22.6% | over budget |
| Quote drafting | AI price per unit | $0.00000300 | $0.00000328 | +9.3% | $0.00000252 | +30.2% | over budget |
| Quote drafting | Cost per task | $0.0270 | $0.0338 | +25.0% | $0.0211 | +59.6% | over budget |

## Where the money went

**Largest part:** Quote drafting on the large model, $0.96 over budget.

| Project | Model | Share of AI usage | AI price per unit | Spent | Over budget |
|---|---|---|---|---|---|
| Quote drafting | the large model | 10.0% | $0.00000596 | $1.72 | $0.96 |
| Quote drafting | the standard model | 90.0% | $0.00000298 | $7.73 | $0.93 |

Cost over budget is split by model as each model's cost minus its share of the budget by usage, so the parts add up. It shows where the money went, not why.

## Worth knowing

- Prices were retrieved 2026-10-15, in USD. They are illustrative, not any provider's list price.

## For your engineers

- Models: the large model is `vendor-a/xl`; the standard model is `vendor-a/large`.
- Line keys: `tokens_per_task` (tokens: input, output, cache read and cache write), `price_per_token` (priced cost over tokens, so cache reads pull it down) and `cost_per_task`.
- quote-drafting: tasks from distinct task ids in gateway.jsonl.
- Read: gateway.jsonl: 560 requests read as an AI gateway log; input and cache reads are counted apart.
- Prices: pricing.json, Illustrative prices for the Acme sample. Not any provider's list price, retrieved 2026-10-15.
- `--landing` and `--bet` add the `cost` key to `landing/<bet>.json`. `--fail-on over-budget` fails the run, for a CI gate, when a line is over budget.

Every figure above is in the JSON beside this file, with its formula and sources. The check shows where spend went against budget, not why.
