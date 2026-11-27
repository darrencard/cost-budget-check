#!/usr/bin/env python3
"""Check each AI feature's spend against its landing brief's cost budget, and name what drives drift.

Usage:
  python3 scripts/check.py --brief visit-notes=briefs/visit-notes.md --brief quote-follow-up=briefs/quote-follow-up.md \\
      --pricing pricing.json --gateway-log gateway.jsonl --usage-csv usage.csv --tasks tasks.csv \\
      --finance run/ai_spend/finance.csv --window 2026-11-01..2026-11-30 --as-of 2026-12-01 --out run

The budget is two lines from each brief: tokens per task and price per token. For each feature the
check computes, in code, from the usage and the pricing table:

  tokens per task   all tokens (input, output, cache read, cache write) / tasks
  price per token   priced cost / all tokens, so cheaper cache reads lower it
  cost per task     priced cost / tasks, against tokens per task x price per token

Each line gets one of two words against its budget:
  within budget   at or under budget
  over budget     over budget
landed, watch and stalled are a bet's status, set only by did-it-land, so no budget line uses them.

Drift is the cost over budget: priced cost minus tasks x budgeted cost per task. It is split by
model as each model's cost minus its share (by tokens) of the budget, so the parts add up to the
whole. The driver is the feature and model with the largest part. Without a task count only price
per token is checked, and the gap is said, never estimated.

Writes OUT/cost_check.json (every figure, with its formula and sources), OUT/cost_check.html (the
page for leaders, in the Leader Report's style) and OUT/cost_check.md (its plain-text twin). With
--landing DIR it also writes the cost key of DIR/<bet>.json, the Landing Loop record, and leaves every
other key as it found it.
Exit code 0, or 2 when --fail-on over-budget is set and a line is over budget by more than --tolerance
(default 0). Errors exit 1.

This script reads files and writes files. It makes no network calls.

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):  # noqa: UP036  (checked first, before anything is read or written)
    raise SystemExit("check: needs Python 3.11 or later; try python3.12.")

import argparse
import datetime
import glob
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brief as brief_mod  # noqa: E402  (puts vendor/ on the path)
import from_ai_spend  # noqa: E402  (vendored from the Leader Report, see vendor/VENDORED.md)
import landing  # noqa: E402
import page  # noqa: E402
import pricing as pricing_mod  # noqa: E402
import readers  # noqa: E402

TOOL = "cost-budget-check"
VERSION = "0.3.2"
WITHIN = "within budget"
OVER = "over budget"
RECONCILE_TOLERANCE = 0.02
Json = dict[str, Any]


def status(actual: float, budget: float) -> str:
    """A budget line's word. Never landed, watch or stalled: those are a bet's status, set by did-it-land."""
    return WITHIN if actual <= budget else OVER


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


def pairs_list(items: list[str], what: str) -> list[tuple[str, str]]:
    out = []
    for item in items:
        if "=" not in item:
            raise readers.InputError(f'{what} "{item}" is not FEATURE=VALUE.')
        k, v = item.split("=", 1)
        out.append((k.strip(), v.strip()))
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
    for p in args.anthropic_usage:
        r = readers.read_anthropic_usage(Path(p), fmap)
        records += r.records
        notes += r.notes
    for feature, p in pairs_list(args.vercel_gateway, "--vercel-gateway"):
        r = readers.read_vercel_gateway(Path(p), feature)
        records += r.records
        notes += r.notes
    for feature, pattern in pairs_list(args.run_records, "--run-records"):
        files = sorted(Path(x) for x in glob.glob(pattern, recursive=True) if Path(x).is_file())
        if not files:
            raise readers.InputError(f"--run-records {feature}={pattern} matches no files.")
        r = readers.read_run_records(feature, files, args.run_records_cache_ttl)
        records += r.records
        notes += r.notes
    if not records:
        raise readers.InputError("no usage was given. Pass --anthropic-usage, --vercel-gateway, --run-records, --usage-csv or --gateway-log.")
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
        if r.kind in ("provider usage CSV", "Anthropic usage report"):
            key = (r.feature, r.model, r.date)
            if key in seen and seen[key] != r.file:
                raise readers.InputError(f"{r.feature} {r.model} on {r.date} is in both {seen[key]} and {r.file}. That would count it twice.")
            seen[key] = r.file
    both = sorted(f for f, k in kinds.items() if len(k) > 1)
    if both:
        raise readers.InputError(f"{', '.join(both)} appears in both a provider CSV and a gateway log. Use one source per feature so no token counts twice.")


def task_count(task_csv: dict, name: str, window: str | None, recs: list[readers.Record]) -> tuple[int | None, str | None, str | None, int | None]:
    """(tasks, source, gap, succeeded) for one feature in one window: a dated tasks.csv row, an undated one, then task ids."""
    for key in ((name, window or ""), (name, "")):
        if key in task_csv:
            tasks, source, succeeded = task_csv[key]
            return tasks, source, None, succeeded
    other = sorted(w for (n, w) in task_csv if n == name and w)
    if other:
        return None, None, f"tasks.csv counts {name} for {', '.join(other)}, not {window or 'the usage given'}, so tasks are not counted.", None
    ids = {r.task_id for r in recs if r.task_id}
    if ids and all(r.task_id for r in recs):
        files = sorted({r.file for r in recs})
        where = files[0] if len(files) == 1 else f"{len(files)} files ({files[0]} to {files[-1]})"
        return len(ids), f"distinct task ids in {where}", None, None
    if ids:
        return None, None, f"{sum(1 for r in recs if not r.task_id)} of {len(recs)} requests have no task id, so tasks are not counted.", None
    return None, None, None, None


def prior_lines(f: Json, recs: list[readers.Record], tasks: int | None, task_source: str | None, table: pricing_mod.Pricing, ledger: Ledger, window: str, pricing_src: str) -> None:
    """The same three lines for the prior window, and each line's change since then."""
    name = f["feature"]
    total = sum(sum(r.tokens.values()) for r in recs)
    if not total:
        f["gaps"].append(f"no usage in the prior window {window}, so there is no change to show.")
        return
    cost = math.fsum(table.rate_for(r.model).cost(r.tokens) for r in recs)
    files = sorted({r.file for r in recs}) + [pricing_src]
    values = {"price_per_token": (cost / total, fmt_price, "priced cost / tokens")}
    if tasks:
        values["tokens_per_task"] = (total / tasks, fmt_tokens, "tokens / tasks")
        values["cost_per_task"] = (cost / tasks, fmt_task_cost, "priced cost / tasks")
    elif "tokens_per_task" in f["checks"]:
        f["gaps"].append(f"no task count for the prior window {window}, so only price per token has a change.")
    for key, (value, show, formula) in values.items():
        c = f["checks"].get(key)
        if not c:
            continue
        sources = files + ([task_source] if task_source and key != "price_per_token" else [])
        c["prior"] = value
        c["prior_display"] = ledger.add(f"{name}.prior.{key}", f"{name} {key.replace('_', ' ')}, prior window", value, show(value), formula + f", {window}", sources)
        c["change"] = c["actual"] / value - 1
        c["change_display"] = ledger.add(f"{name}.{key}.change", f"{name} {key.replace('_', ' ')} since the prior window", c["change"], fmt_pct(c["change"]), "this window / prior window - 1", sources)


def write_pricing_template(path: Path, records: list[readers.Record]) -> int:
    """A pricing table with one row per model in the usage. Prices are null, so it is refused until filled."""
    models = sorted({r.model for r in records if r.model})
    row = dict.fromkeys(pricing_mod.TOKEN_TYPES)
    data = {"source": "", "retrieved": "", "currency": "USD", "models": [{"match": m, **row} for m in models]}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"{TOOL}: wrote {path} with {len(models)} models. Fill source, retrieved and every price per million tokens from the provider's pricing page or your contract.")
    return 0


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
    all_records = records
    records = in_window(records, window)
    prior_window = None
    prior: list[readers.Record] = []
    if args.prior_window:
        if not window:
            raise readers.InputError("--prior-window needs --window too.")
        prior_window = parse_window(args.prior_window)
        if prior_window[1] >= window[0]:
            raise readers.InputError(f"the prior window {args.prior_window} must end before the window {args.window} starts.")
        prior = in_window(all_records, prior_window)
        guard_double_count(prior)
    guard_double_count(records)
    unpriced = sorted({r.model or "(blank)" for r in records + prior if table.rate_for(r.model) is None})
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
        tokens = {t: sum(r.tokens.get(t, 0) for r in recs) for t in pricing_mod.ALL_TOKEN_TYPES}
        total = sum(tokens.values())
        cost = math.fsum(table.rate_for(r.model).cost(r.tokens) for r in recs)
        if name not in budgets:
            ledger.add(f"{name}.cost", f"{name} priced cost (no brief)", cost, fmt_money(cost), "sum of tokens x rate per token type", files + [pricing_src])
            unbriefed.append({"feature": name, "cost": cost, "cost_display": fmt_money(cost), "files": files})
            continue
        b = budgets[name]
        f: Json = {
            "feature": name,
            "title": b.title or name,
            "brief": b.source,
            "brief_path": b.path,
            "brief_sha256": b.sha256,
            "metric": b.metric,
            "line": b.line,
            "decides": b.decides,
            "files": files,
            "checks": {},
            "models": [],
            "gaps": [],
        }
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
        tasks, task_source, gap, succeeded = task_count(task_csv, name, args.window, recs)
        if gap:
            f["gaps"].append(gap)
        src = files + [pricing_src]
        f["tokens"] = {t: tokens[t] for t in pricing_mod.ALL_TOKEN_TYPES if t in pricing_mod.TOKEN_TYPES or tokens[t]}
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
            "status": status(ppt, b.price_per_token),
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
                    "status": status(actual, budget),
                }
                c["over_display"] = ledger.add(f"{name}.{key}.over", f"{name} {key.replace('_', ' ')} against budget", c["over"], fmt_pct(c["over"]), "actual / budget - 1", src + [task_source, b.source])
                f["checks"][key] = c
            if succeeded:
                f["success_rate_display"] = ledger.add(f"{name}.success_rate", f"{name} tasks that succeeded", succeeded / tasks, f"{succeeded / tasks * 100:.1f}%", "succeeded / tasks", [task_source])
                f["cost_per_success"] = cost / succeeded
                f["cost_per_success_display"] = ledger.add(f"{name}.cost_per_success", f"{name} cost per successful task", cost / succeeded, fmt_task_cost(cost / succeeded), "priced cost / tasks that succeeded", src + [task_source])
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
            mcost = math.fsum(table.rate_for(model).cost(r.tokens) for r in mrecs)
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
        f["status"] = OVER if any(c["status"] == OVER for c in f["checks"].values()) else WITHIN
        if prior_window:
            precs = [r for r in prior if r.feature == name]
            ptasks, psource, pgap, _ = task_count(task_csv, name, args.prior_window, precs)
            if pgap:
                f["gaps"].append(pgap.replace("tasks are not counted", "prior tasks are not counted"))
            prior_lines(f, precs, ptasks, psource, table, ledger, args.prior_window, pricing_src)
        stated = [r.stated_cost for r in recs]
        if all(s is not None for s in stated):
            gap = math.fsum(stated) - cost
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
        "prior_window": args.prior_window,
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
    bill = None
    if args.finance and (args.anthropic_cost or args.openai_costs):
        raise readers.InputError("pass the bill once: --finance, or --anthropic-cost and --openai-costs, not both.")
    if args.finance:
        billed, lines = readers.read_finance(Path(args.finance), args.finance_period)
        bill = (billed, lines, [Path(args.finance).name])
    elif args.anthropic_cost or args.openai_costs:
        if not window:
            raise readers.InputError("--anthropic-cost and --openai-costs need --window, to pick the cost buckets.")
        lines, total = [], 0.0
        for vendor, paths, label in (("anthropic", args.anthropic_cost, "Model API: Anthropic"), ("openai", args.openai_costs, "Model API: OpenAI")):
            if paths:
                try:
                    amount = from_ai_spend.api_spend(paths, vendor, window[0], window[1])
                except SystemExit as e:
                    raise readers.InputError(str(e)) from None
                total += amount
                lines.append(f"{label} {fmt_money(amount)}, cost report buckets in {args.window}")
        bill = (round(total, 2), lines, [Path(p).name for p in args.anthropic_cost + args.openai_costs])
    if bill:
        billed, lines, fsrc = bill
        priced = math.fsum([f.get("cost", 0.0) for f in features] + [u["cost"] for u in unbriefed])
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
    dated = sorted(r.date for r in records if r.date)
    if window:
        result["window_used"] = {"from": window[0].isoformat(), "to": window[1].isoformat()}
    elif dated:
        result["window_used"] = {"from": dated[0].isoformat(), "to": dated[-1].isoformat()}
    else:
        result["window_used"] = {"from": None, "to": None}
    result["ledger"] = ledger.rows
    return result


def render(result: Json) -> str:
    """The Markdown twin of the page: the same plain words, with model ids, files and flags under "For your engineers"."""
    p = result["pricing"]
    models = page.model_names(result)
    out = [f"# Cost budget check, {page.window_text(result) if result['window'] else 'all usage given'}", ""]
    if p["illustrative"]:
        out += ["*Illustrative: sample prices, not any provider's list price.*", ""]
    out += [f"**{page.headline(result)}**", "", page.lede(result), ""]
    if result.get("prior_window"):
        out += [f"The period before, for the change in each line: {page.window_text({'window': result['prior_window'], 'window_used': {}})}. As of {result['as_of']}.", ""]
    else:
        out += [f"As of {result['as_of']}.", ""]
    text, decides, due = page.next_step(result)
    out += ["## What to do next", "", f"{text}" + (f" Decides: {decides}." if decides else "") + f" Due: {due}.", ""]
    since = bool(result.get("prior_window"))
    out += ["## Each line against the budget", ""]
    out.append("| Project | Line | Budget | Actual | Against budget |" + (" Before | Since then |" if since else "") + " Status |")
    out.append("|---|---|---|---|---|" + ("---|---|" if since else "") + "---|")
    for f in result["features"]:
        for key in page.LINES:
            c = f["checks"].get(key)
            if c:
                extra = f" {c.get('prior_display', 'none')} | {c.get('change_display', 'none')} |" if since else ""
                out.append(f"| {page.name(f)} | {page.LABEL[key]} | {c['budget_display']} | {c['actual_display']} | {c['over_display']} |{extra} {c['status']} |")
        if not f["checks"]:
            out.append(f"| {page.name(f)} | none checked | | | |" + (" | |" if since else "") + " |")
    out.append("")
    out += ["## Where the money went", ""]
    if result["drivers"]:
        top = result["drivers"][0]
        out.append(f"**Largest part:** {page.name_of(result, top['feature'])} on {models.get(top['model'], top['model'])}, {top['drift_display']} over budget.")
        out.append("")
        out.append("| Project | Model | Share of AI usage | AI price per unit | Spent | Over budget |")
        out.append("|---|---|---|---|---|---|")
        for f in result["features"]:
            for m in sorted(f.get("models", []), key=lambda m: -m["drift"]):
                out.append(f"| {page.name(f)} | {models.get(m['model'], m['model'])} | {m['share_display']} | {m['price_per_token_display']} | {m['cost_display']} | {m['drift_display']} |")
        out.append("")
        out.append("Cost over budget is split by model as each model's cost minus its share of the budget by usage, so the parts add up. It shows where the money went, not why.")
    else:
        out.append("No project and model is over budget.")
    out.append("")
    for f in result["features"]:
        if f.get("cost_per_success_display"):
            out.append(f"**{page.name(f)}:** {f['success_rate_display']} of tasks succeeded, so each one that worked cost {f['cost_per_success_display']}. No budget line covers it; it is shown, not marked.")
            out.append("")
    if "reconcile" in result:
        r = result["reconcile"]
        out.append(f"**The bill:** {r['billed_display']} billed, {r['priced_display']} priced from usage, {r['unattributed_display']} not in the usage given.")
        out.append("")
    out += ["## Worth knowing", ""]
    for u in result["unbriefed"]:
        out.append(f"- {u['feature']}: {u['cost_display']} spent with no landing brief, so no budget to check.")
    out += [f"- {x}" for x in page.worth_knowing(result)]
    out += ["", "## For your engineers", ""]
    if models:
        out.append("- Models: " + "; ".join(f"{n} is `{m}`" for m, n in models.items()) + ".")
    out.append("- Line keys: `tokens_per_task` (tokens: input, output, cache read and cache write), `price_per_token` (priced cost over tokens, so cache reads pull it down) and `cost_per_task`.")
    for f in result["features"]:
        if f.get("tasks_source"):
            out.append(f"- {f['feature']}: tasks from {f['tasks_source']}.")
        for g in f["gaps"]:
            out.append(f"- {f['feature']}: {g}")
    for w in result["warnings"]:
        out.append(f"- Warning: {w}")
    for n in result["notes"]:
        out.append(f"- Read: {n}")
    out.append(f"- Prices: {p['file']}, {p['source'].rstrip('.')}, retrieved {p['retrieved']}.")
    gate = f" The --fail-on gate lets a line run {result['tolerance'] * 100:.0f}% over budget." if result["tolerance"] else ""
    out.append(f"- `--landing` and `--bet` add the `cost` key to `landing/<bet>.json`. `--fail-on over-budget` fails the run, for a CI gate, when a line is over budget.{gate}")
    out.append("")
    out.append("Every figure above is in the JSON beside this file, with its formula and sources. The check shows where spend went against budget, not why.")
    return "\n".join(out) + "\n"


SAMPLE = Path(__file__).resolve().parent.parent / "assets" / "acme"


def demo_args(out: str) -> list[str]:
    """The arguments for the bundled Acme sample: two features, one month, the month before, and a bill."""
    a = SAMPLE
    return [
        "--brief", f"visit-notes={a / 'briefs' / 'visit-notes.md'}",
        "--brief", f"quote-follow-up={a / 'briefs' / 'quote-follow-up.md'}",
        "--pricing", str(a / "pricing.json"),
        "--gateway-log", str(a / "gateway.jsonl"),
        "--usage-csv", str(a / "usage.csv"),
        "--tasks", str(a / "tasks.csv"),
        "--finance", str(a / "finance.csv"),
        "--feature-map", "acme-quote-follow-up=quote-follow-up",
        "--feature-map", "acme-search=search-assist",
        "--window", "2026-11-01..2026-11-30",
        "--prior-window", "2026-10-01..2026-10-31",
        "--as-of", "2026-12-01",
        "--out", out,
    ]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check AI feature spend against each landing brief's cost budget.")
    ap.add_argument("--brief", action="append", default=[], help="FEATURE=PATH to a landing brief (repeat per feature)")
    ap.add_argument("--pricing", help="pricing table JSON with its own source and retrieved date")
    ap.add_argument("--prior-window", help="YYYY-MM-DD..YYYY-MM-DD before --window; shows each line's change since then")
    ap.add_argument("--write-pricing-template", metavar="PATH", help="write a pricing table listing every model in the usage, to fill in, and stop")
    ap.add_argument("--demo", action="store_true", help="run on the bundled Acme sample (illustrative) and write to --out")
    ap.add_argument("--usage-csv", action="append", default=[], help="provider usage CSV (repeat)")
    ap.add_argument("--gateway-log", action="append", default=[], help="AI gateway log, JSON Lines or a JSON array (repeat)")
    ap.add_argument("--tasks", help="CSV of feature, tasks, source")
    ap.add_argument("--anthropic-usage", action="append", default=[], help="Anthropic Admin API usage_report/messages page, grouped by model and key or workspace (repeat)")
    ap.add_argument("--vercel-gateway", action="append", default=[], help="FEATURE=FILE, a Vercel AI Gateway usage response grouped by aiModel (repeat)")
    ap.add_argument("--run-records", action="append", default=[], help="FEATURE=GLOB, agent run records with a usage block, one file per task (repeat)")
    ap.add_argument("--run-records-cache-ttl", choices=("5m", "1h"), default="5m", help="which cache the run records' writes went to (Claude Code writes 1h); default 5m")
    ap.add_argument("--anthropic-cost", action="append", default=[], help="Anthropic Admin API cost_report page, as the bill (repeat)")
    ap.add_argument("--openai-costs", action="append", default=[], help="OpenAI /v1/organization/costs page, as the bill (repeat)")
    ap.add_argument("--landing", metavar="DIR", help="write the cost key of DIR/<bet>.json, the Landing Loop record, for each briefed feature")
    ap.add_argument("--bet", action="append", default=[], help="FEATURE=SLUG, the bet a feature's record is named for (default: the feature name)")
    ap.add_argument("--finance", help="finance.csv from the Leader Report's from_ai_spend.py, to reconcile against the bill")
    ap.add_argument("--finance-period", help="the finance.csv period label to use, when it holds several")
    ap.add_argument("--feature-map", action="append", default=[], help="RAW=FEATURE, to rename a key, workspace or tag (repeat)")
    ap.add_argument("--window", help="YYYY-MM-DD..YYYY-MM-DD; usage outside it is dropped")
    ap.add_argument("--as-of", help="YYYY-MM-DD; defaults to today")
    ap.add_argument("--tolerance", type=float, default=0.0, help="share over budget the --fail-on gate lets through (default 0); the line still reads over budget")
    ap.add_argument("--fail-on", choices=("over-budget",), help="exit 2 when a line is over budget by more than --tolerance")
    ap.add_argument("--out", default="run")
    ap.add_argument("--stem", default="cost_check", help="file name for the outputs: STEM.html, STEM.md and STEM.json (default cost_check)")
    args = ap.parse_args(argv)
    if args.demo:
        keep = (["--landing", args.landing] if args.landing else []) + [x for b in args.bet for x in ("--bet", b)] + (["--fail-on", args.fail_on] if args.fail_on else [])
        args = ap.parse_args(demo_args(args.out) + keep)
    if args.write_pricing_template:
        try:
            records, _ = gather(args)
        except readers.InputError as e:
            print(f"{TOOL}: {e}", file=sys.stderr)
            return 1
        return write_pricing_template(Path(args.write_pricing_template), records)
    if not args.pricing:
        print(f"{TOOL}: --pricing is required. Run once with --write-pricing-template pricing.json to list the models to price.", file=sys.stderr)
        return 1
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
    (out / f"{args.stem}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report = render(result)
    (out / f"{args.stem}.md").write_text(report, encoding="utf-8")
    (out / f"{args.stem}.html").write_text(page.render(result), encoding="utf-8")
    print(report, end="")
    if args.landing:
        try:
            for path in landing.write(result, Path(args.landing), pairs(args.bet, "--bet")):
                print(f"{TOOL}: wrote the cost key of {path}.")
        except landing.LandingError as e:
            print(f"{TOOL}: {e}", file=sys.stderr)
            return 1
    if args.fail_on and any(c["over"] > args.tolerance for f in result["features"] for c in f["checks"].values()):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
