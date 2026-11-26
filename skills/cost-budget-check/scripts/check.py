#!/usr/bin/env python3
"""Check each AI feature's spend against its landing brief's cost budget, and name what drives drift.

Usage:
  python3 scripts/check.py --brief quote-drafter=briefs/quote-drafter.md --brief invoice-chaser=briefs/invoice-chaser.md \\
      --pricing pricing.json --gateway-log gateway.jsonl --usage-csv usage.csv --tasks tasks.csv \\
      --finance run/ai_spend/finance.csv --window 2026-11-01..2026-11-30 --as-of 2026-12-01 --out run

The budget is two lines from each brief: tokens per task and price per token. For each feature the
check computes, in code, from the usage and the pricing table:

  tokens per task   all tokens (input, output, cache read, cache write) / tasks
  price per token   priced cost / all tokens, so cheaper cache reads lower it
  cost per task     priced cost / tasks, against tokens per task x price per token

Each line gets one status word against its budget:
  landed   at or under budget
  watch    over budget by no more than the tolerance (default 10%)
  stalled  over budget by more than the tolerance

Drift is the cost over budget: priced cost minus tasks x budgeted cost per task. It is split by
model as each model's cost minus its share (by tokens) of the budget, so the parts add up to the
whole. The driver is the feature and model with the largest part. Without a task count only price
per token is checked, and the gap is said, never estimated.

Writes OUT/cost_check.json (every figure, with its formula and sources) and OUT/cost_check.md.
Exit code 0, or 2 when --fail-on is set and a feature reaches that status. Errors exit 1.

This script reads files and writes files. It makes no network calls.

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brief as brief_mod  # noqa: E402
import pricing as pricing_mod  # noqa: E402
import readers  # noqa: E402

TOOL = "cost-budget-check"
VERSION = "0.1.0"
RANK = {"landed": 0, "watch": 1, "stalled": 2}
RECONCILE_TOLERANCE = 0.02
Json = dict[str, Any]


def status(actual: float, budget: float, tolerance: float) -> str:
    if actual <= budget:
        return "landed"
    return "watch" if actual <= budget * (1 + tolerance) else "stalled"


def fmt_tokens(v: float) -> str:
    return f"{v:,.0f}"


def fmt_price(v: float) -> str:
    """Three significant figures, written out: $0.00000412, as briefs write it."""
    if v <= 0:
        return "$0"
    decimals = max(2, 2 - math.floor(math.log10(v)))
    return f"${v:.{decimals}f}"


def fmt_money(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


def fmt_pct(v: float) -> str:
    return f"{v * 100:+.1f}%"


def fmt_task_cost(v: float) -> str:
    return f"${v:.4f}"


class Ledger:
    """Every figure the check prints, with an id, its value, how it was computed and from what."""

    def __init__(self) -> None:
        self.rows: list[Json] = []

    def add(self, fid: str, label: str, value: float | int, display: str, formula: str, sources: list[str]) -> str:
        self.rows.append({"id": fid, "label": label, "value": value, "display": display, "formula": formula, "sources": sorted(set(sources))})
        return display


def parse_window(text: str) -> tuple[datetime.date, datetime.date]:
    try:
        a, b = text.split("..")
        start, end = datetime.date.fromisoformat(a), datetime.date.fromisoformat(b)
    except ValueError:
        raise readers.InputError(f'window "{text}" is not YYYY-MM-DD..YYYY-MM-DD.') from None
    if end < start:
        raise readers.InputError(f"window {text} ends before it starts.")
    return start, end


def pairs(items: list[str], what: str) -> dict[str, str]:
    out = {}
    for item in items:
        if "=" not in item:
            raise readers.InputError(f'{what} "{item}" is not NAME=VALUE.')
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def gather(args: argparse.Namespace) -> tuple[list[readers.Record], list[str]]:
    fmap = pairs(args.feature_map, "--feature-map")
    records: list[readers.Record] = []
    notes: list[str] = []
    for p in args.usage_csv:
        r = readers.read_usage_csv(Path(p), fmap)
        records += r.records
        notes += r.notes
    for p in args.gateway_log:
        r = readers.read_gateway(Path(p), fmap)
        records += r.records
        notes += r.notes
    if not records:
        raise readers.InputError("no usage was given. Pass --usage-csv or --gateway-log.")
    return records, notes


def in_window(records: list[readers.Record], window: tuple[datetime.date, datetime.date] | None) -> list[readers.Record]:
    if window is None:
        return records
    undated = sorted({r.file for r in records if r.date is None})
    if undated:
        raise readers.InputError(f"{', '.join(undated)} has rows with no date, so the window cannot be applied.")
    return [r for r in records if window[0] <= r.date <= window[1]]


def guard_double_count(records: list[readers.Record]) -> None:
    kinds: dict[str, set[str]] = defaultdict(set)
    seen: dict[tuple, str] = {}
    for r in records:
        kinds[r.feature].add(r.kind)
        if r.kind == "provider usage CSV":
            key = (r.feature, r.model, r.date)
            if key in seen and seen[key] != r.file:
                raise readers.InputError(f"{r.feature} {r.model} on {r.date} is in both {seen[key]} and {r.file}. That would count it twice.")
            seen[key] = r.file
    both = sorted(f for f, k in kinds.items() if len(k) > 1)
    if both:
        raise readers.InputError(f"{', '.join(both)} appears in both a provider CSV and a gateway log. Use one source per feature so no token counts twice.")


def run(args: argparse.Namespace) -> Json:
    as_of = datetime.date.fromisoformat(args.as_of) if args.as_of else datetime.date.today()
    window = parse_window(args.window) if args.window else None
    budgets = {}
    for name, path in pairs(args.brief, "--brief").items():
        budgets[name] = brief_mod.load(Path(path), name)
    if not budgets:
        raise readers.InputError("no brief was given. Pass --brief FEATURE=PATH for each feature.")
    table = pricing_mod.load(Path(args.pricing))
    records, notes = gather(args)
    records = in_window(records, window)
    guard_double_count(records)
    unpriced = sorted({r.model or "(blank)" for r in records if table.rate_for(r.model) is None})
    if unpriced:
        raise pricing_mod.PricingError(f"{table.file} has no price for {', '.join(unpriced)}. Add a row for each; there is no default rate.")
    task_csv = readers.read_tasks(Path(args.tasks), pairs(args.feature_map, "--feature-map")) if args.tasks else {}

    ledger = Ledger()
    by_feature: dict[str, list[readers.Record]] = defaultdict(list)
    for r in records:
        by_feature[r.feature].append(r)
    features: list[Json] = []
    unbriefed: list[Json] = []
    pricing_src = f"{table.file} ({table.source}, retrieved {table.retrieved})"
    for name in sorted(set(by_feature) | set(budgets)):
        recs = by_feature.get(name, [])
        files = sorted({r.file for r in recs})
        tokens = {t: sum(r.tokens[t] for r in recs) for t in pricing_mod.TOKEN_TYPES}
        total = sum(tokens.values())
        cost = sum(table.rate_for(r.model).cost(r.tokens) for r in recs)
        if name not in budgets:
            ledger.add(f"{name}.cost", f"{name} priced cost (no brief)", cost, fmt_money(cost), "sum of tokens x rate per token type", files + [pricing_src])
            unbriefed.append({"feature": name, "cost": cost, "cost_display": fmt_money(cost), "files": files})
            continue
        b = budgets[name]
        f: Json = {"feature": name, "brief": b.source, "line": b.line, "files": files, "checks": {}, "models": [], "gaps": []}
        if b.line == "fixed code":
            f["gaps"].append("the brief puts this feature in fixed code, so it has no model budget to check.")
            if recs:
                f["gaps"].append(f"yet {len(recs)} usage rows name it. Check the feature tag or the brief.")
            features.append(f)
            continue
        if not recs:
            f["gaps"].append("no usage in the window. Check the feature tag, the window or the export.")
            features.append(f)
            continue
        tasks, task_source = None, None
        if name in task_csv:
            tasks, task_source = task_csv[name]
        else:
            ids = {r.task_id for r in recs if r.task_id}
            if ids and all(r.task_id for r in recs):
                tasks, task_source = len(ids), f"distinct task ids in {', '.join(files)}"
            elif ids:
                f["gaps"].append(f"{sum(1 for r in recs if not r.task_id)} of {len(recs)} requests have no task id, so tasks are not counted.")
        src = files + [pricing_src]
        f["tokens"] = {t: tokens[t] for t in pricing_mod.TOKEN_TYPES}
        f["tokens_display"] = ledger.add(f"{name}.tokens", f"{name} tokens", total, fmt_tokens(total), "input + output + cache read + cache write", files)
        f["cost"] = cost
        f["cost_display"] = ledger.add(f"{name}.cost", f"{name} priced cost", cost, fmt_money(cost), "sum of tokens x rate per token type", src)
        ppt = cost / total if total else 0.0
        f["checks"]["price_per_token"] = {
            "budget": b.price_per_token,
            "budget_display": ledger.add(f"{name}.budget.price_per_token", f"{name} budget price per token", b.price_per_token, fmt_price(b.price_per_token), "stated in the brief", [b.source]),
            "actual": ppt,
            "actual_display": ledger.add(f"{name}.price_per_token", f"{name} price per token", ppt, fmt_price(ppt), "priced cost / tokens", src),
            "over": ppt / b.price_per_token - 1,
            "status": status(ppt, b.price_per_token, args.tolerance),
        }
        f["checks"]["price_per_token"]["over_display"] = ledger.add(
            f"{name}.price_per_token.over", f"{name} price per token against budget", f["checks"]["price_per_token"]["over"], fmt_pct(f["checks"]["price_per_token"]["over"]), "actual / budget - 1", src + [b.source]
        )
        if tasks:
            f["tasks"] = tasks
            f["tasks_source"] = task_source
            f["tasks_display"] = ledger.add(f"{name}.tasks", f"{name} tasks", tasks, f"{tasks:,}", "counted", [task_source])
            tpt = total / tasks
            cpt = cost / tasks
            budget_cpt = b.cost_per_task
            for key, actual, budget, show, formula in (
                ("tokens_per_task", tpt, b.tokens_per_task, fmt_tokens, "tokens / tasks"),
                ("cost_per_task", cpt, budget_cpt, fmt_task_cost, "priced cost / tasks"),
            ):
                bsrc = "stated in the brief" if key == "tokens_per_task" else "tokens per task x price per token, both stated in the brief"
                c = {
                    "budget": budget,
                    "budget_display": ledger.add(f"{name}.budget.{key}", f"{name} budget {key.replace('_', ' ')}", budget, show(budget), bsrc, [b.source]),
                    "actual": actual,
                    "actual_display": ledger.add(f"{name}.{key}", f"{name} {key.replace('_', ' ')}", actual, show(actual), formula, src + [task_source]),
                    "over": actual / budget - 1,
                    "status": status(actual, budget, args.tolerance),
                }
                c["over_display"] = ledger.add(f"{name}.{key}.over", f"{name} {key.replace('_', ' ')} against budget", c["over"], fmt_pct(c["over"]), "actual / budget - 1", src + [task_source, b.source])
                f["checks"][key] = c
            budget_total = tasks * budget_cpt
            drift_basis = "priced cost - tasks x budgeted cost per task"
        else:
            f["gaps"].append("no task count, so tokens per task and cost per task are not checked. Pass --tasks or log a task id per request.")
            budget_total = total * b.price_per_token
            drift_basis = "priced cost - tokens x budgeted price per token (price line only, no task count)"
        drift = cost - budget_total
        f["drift"] = drift
        f["drift_basis"] = drift_basis
        f["drift_display"] = ledger.add(f"{name}.drift", f"{name} cost over budget", drift, fmt_money(drift), drift_basis, src + [b.source] + ([task_source] if task_source else []))
        per_model: dict[str, list[readers.Record]] = defaultdict(list)
        for r in recs:
            per_model[r.model].append(r)
        for model in sorted(per_model):
            mrecs = per_model[model]
            mtok = sum(sum(r.tokens.values()) for r in mrecs)
            mcost = sum(table.rate_for(model).cost(r.tokens) for r in mrecs)
            mdrift = mcost - (mtok / total) * budget_total if total else 0.0
            mid = f"{name}.{model}"
            f["models"].append(
                {
                    "model": model,
                    "tokens": mtok,
                    "tokens_display": ledger.add(f"{mid}.tokens", f"{name} tokens on {model}", mtok, fmt_tokens(mtok), "sum of all token types", files),
                    "share": mtok / total if total else 0.0,
                    "share_display": ledger.add(f"{mid}.share", f"{name} share of tokens on {model}", mtok / total if total else 0.0, f"{mtok / total * 100:.1f}%" if total else "0.0%", "model tokens / feature tokens", files),
                    "cost": mcost,
                    "cost_display": ledger.add(f"{mid}.cost", f"{name} priced cost on {model}", mcost, fmt_money(mcost), "sum of tokens x rate per token type", src),
                    "price_per_token_display": ledger.add(f"{mid}.price_per_token", f"{name} price per token on {model}", mcost / mtok if mtok else 0.0, fmt_price(mcost / mtok if mtok else 0.0), "model cost / model tokens", src),
                    "drift": mdrift,
                    "drift_display": ledger.add(f"{mid}.drift", f"{name} cost over budget on {model}", mdrift, fmt_money(mdrift), "model cost - model token share x budgeted cost", src + [b.source]),
                }
            )
        f["status"] = max((c["status"] for c in f["checks"].values()), key=RANK.get)
        stated = [r.stated_cost for r in recs]
        if all(s is not None for s in stated):
            gap = sum(stated) - cost
            f["stated_cost_gap_display"] = ledger.add(f"{name}.stated_cost_gap", f"{name} export cost minus priced cost", gap, fmt_money(gap), "sum of the export's own cost - priced cost", src)
            if cost and abs(gap) / cost > RECONCILE_TOLERANCE:
                f["gaps"].append(f"the export's own cost differs from the priced cost by {f['stated_cost_gap_display']}. Check the pricing table against the invoice.")
        features.append(f)

    drivers = sorted(
        ({"feature": f["feature"], "model": m["model"], "drift": m["drift"], "drift_display": m["drift_display"]} for f in features for m in f.get("models", []) if m["drift"] > 0),
        key=lambda d: -d["drift"],
    )
    result: Json = {
        "tool": TOOL,
        "version": VERSION,
        "as_of": as_of.isoformat(),
        "window": args.window,
        "tolerance": args.tolerance,
        "pricing": {"file": table.file, "source": table.source, "retrieved": table.retrieved.isoformat(), "currency": table.currency, "illustrative": table.illustrative, "age_days": table.age_days(as_of)},
        "features": features,
        "unbriefed": unbriefed,
        "drivers": drivers,
        "notes": notes,
        "warnings": [],
    }
    if table.stale(as_of):
        result["warnings"].append(f"the pricing table was retrieved {table.age_days(as_of)} days before the as-of date. Check the prices are still current.")
    if table.currency != "USD":
        result["warnings"].append(f"prices are in {table.currency}; figures are shown with $ but are in {table.currency}.")
    if args.finance:
        billed, lines = readers.read_finance(Path(args.finance), args.finance_period)
        priced = sum(f.get("cost", 0.0) for f in features) + sum(u["cost"] for u in unbriefed)
        fsrc = [Path(args.finance).name]
        result["reconcile"] = {
            "billed": billed,
            "billed_display": ledger.add("bill.model_api", "billed model API spend", billed, fmt_money(billed), "sum of Model API actuals: " + "; ".join(lines), fsrc),
            "priced": priced,
            "priced_display": ledger.add("usage.priced", "priced usage, all features", priced, fmt_money(priced), "sum of priced cost across features", [pricing_src]),
            "unattributed": billed - priced,
            "unattributed_display": ledger.add("bill.unattributed", "billed spend not in the usage", billed - priced, fmt_money(billed - priced), "billed - priced usage", fsrc + [pricing_src]),
        }
        if billed and priced > billed * (1 + RECONCILE_TOLERANCE):
            result["warnings"].append("priced usage is above the bill. Check the pricing table and that no usage counts twice.")
        elif billed and (billed - priced) / billed > RECONCILE_TOLERANCE:
            result["warnings"].append(f"{result['reconcile']['unattributed_display']} of the bill is not in the usage given. Some spend has no feature tag or no export.")
    result["ledger"] = ledger.rows
    return result


LABEL = {"tokens_per_task": "Tokens per task", "price_per_token": "Price per token", "cost_per_task": "Cost per task"}


def render(result: Json) -> str:
    p = result["pricing"]
    out = [f"# Cost budget check, {result['window'] or 'all usage given'}", ""]
    out.append(f"As of {result['as_of']}. Tolerance {result['tolerance'] * 100:.0f}% over budget before a line is stalled.")
    out.append(f"Prices: {p['file']}, {p['source'].rstrip('.')}, retrieved {p['retrieved']}.{' Illustrative prices.' if p['illustrative'] else ''}")
    out.append("")
    out.append("| Feature | Line | Budget | Actual | Against budget | Status |")
    out.append("|---|---|---|---|---|---|")
    for f in result["features"]:
        for key in ("tokens_per_task", "price_per_token", "cost_per_task"):
            c = f["checks"].get(key)
            if c:
                out.append(f"| {f['feature']} | {LABEL[key]} | {c['budget_display']} | {c['actual_display']} | {c['over_display']} | {c['status']} |")
        if not f["checks"]:
            out.append(f"| {f['feature']} | none checked | | | | |")
    out.append("")
    if result["drivers"]:
        top = result["drivers"][0]
        out.append(f"**Driver:** {top['feature']} on {top['model']}, {top['drift_display']} over budget.")
        out.append("")
        out.append("| Feature | Model | Share of tokens | Price per token | Priced cost | Over budget |")
        out.append("|---|---|---|---|---|---|")
        for f in result["features"]:
            for m in f.get("models", []):
                out.append(f"| {f['feature']} | {m['model']} | {m['share_display']} | {m['price_per_token_display']} | {m['cost_display']} | {m['drift_display']} |")
        out.append("")
    else:
        out.append("**Driver:** none. No feature and model is over budget.")
        out.append("")
    if "reconcile" in result:
        r = result["reconcile"]
        out.append(f"**Bill:** {r['billed_display']} billed, {r['priced_display']} priced from usage, {r['unattributed_display']} not in the usage given.")
        out.append("")
    for u in result["unbriefed"]:
        out.append(f"- {u['feature']}: {u['cost_display']} priced, with no landing brief, so no budget to check.")
    for f in result["features"]:
        for g in f["gaps"]:
            out.append(f"- {f['feature']}: {g}")
        if f.get("tasks_source"):
            out.append(f"- {f['feature']}: tasks from {f['tasks_source']}.")
    for w in result["warnings"]:
        out.append(f"- Warning: {w}")
    for n in result["notes"]:
        out.append(f"- Read: {n}")
    out.append("")
    out.append("Every figure above is in cost_check.json with its formula and sources. The check shows where spend went against budget, not why.")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check AI feature spend against each landing brief's cost budget.")
    ap.add_argument("--brief", action="append", default=[], help="FEATURE=PATH to a landing brief (repeat per feature)")
    ap.add_argument("--pricing", required=True, help="pricing table JSON with its own source and retrieved date")
    ap.add_argument("--usage-csv", action="append", default=[], help="provider usage CSV (repeat)")
    ap.add_argument("--gateway-log", action="append", default=[], help="AI gateway log, JSON Lines or a JSON array (repeat)")
    ap.add_argument("--tasks", help="CSV of feature, tasks, source")
    ap.add_argument("--finance", help="finance.csv from the Leader Report's from_ai_spend.py, to reconcile against the bill")
    ap.add_argument("--finance-period", help="the finance.csv period label to use, when it holds several")
    ap.add_argument("--feature-map", action="append", default=[], help="RAW=FEATURE, to rename a key, workspace or tag (repeat)")
    ap.add_argument("--window", help="YYYY-MM-DD..YYYY-MM-DD; usage outside it is dropped")
    ap.add_argument("--as-of", help="YYYY-MM-DD; defaults to today")
    ap.add_argument("--tolerance", type=float, default=0.10, help="share over budget still marked watch (default 0.10)")
    ap.add_argument("--fail-on", choices=("watch", "stalled"), help="exit 2 when any feature reaches this status")
    ap.add_argument("--out", default="run")
    args = ap.parse_args(argv)
    if not 0 <= args.tolerance < 1:
        print(f"{TOOL}: --tolerance must be from 0 to under 1.", file=sys.stderr)
        return 1
    try:
        result = run(args)
    except (brief_mod.BriefError, pricing_mod.PricingError, readers.InputError, ValueError) as e:
        print(f"{TOOL}: {e}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "cost_check.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report = render(result)
    (out / "cost_check.md").write_text(report, encoding="utf-8")
    print(report, end="")
    if args.fail_on and any(RANK[f.get("status", "landed")] >= RANK[args.fail_on] for f in result["features"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
