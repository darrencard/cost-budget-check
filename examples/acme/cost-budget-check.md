# Cost budget check, 2026-11-01..2026-11-14

Prior window 2026-10-18..2026-10-31, for the change in each line.
As of 2026-11-15.
Prices: pricing.json, Illustrative prices for the Acme sample. Not any provider's list price, retrieved 2026-10-15. Illustrative prices.

| Feature | Line | Budget | Actual | Against budget | Prior | Since prior | Status |
|---|---|---|---|---|---|---|---|
| quote-drafting | Tokens per task | 9,000 | 10,300 | +14.4% | 8,400 | +22.6% | over budget |
| quote-drafting | Price per token | $0.00000300 | $0.00000328 | +9.3% | $0.00000252 | +30.2% | over budget |
| quote-drafting | Cost per task | $0.0270 | $0.0338 | +25.0% | $0.0211 | +59.6% | over budget |

**Driver:** quote-drafting on vendor-a/xl, $0.96 over budget.

| Feature | Model | Share of tokens | Price per token | Priced cost | Over budget |
|---|---|---|---|---|---|
| quote-drafting | vendor-a/large | 90.0% | $0.00000298 | $7.73 | $0.93 |
| quote-drafting | vendor-a/xl | 10.0% | $0.00000596 | $1.72 | $0.96 |

- quote-drafting: tasks from distinct task ids in gateway.jsonl.
- Read: gateway.jsonl: 560 requests read as an AI gateway log; input and cache reads are counted apart.

Every figure above is in the JSON beside this file, with its formula and sources. The check shows where spend went against budget, not why.
