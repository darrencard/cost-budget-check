#!/usr/bin/env python3
"""Render cost_check.json as one self-contained HTML page in the Leader Report's style guide.

The stylesheet, tokens and fonts are the Leader Report's own, read at render time from its template,
vendored byte-identical as assets/leader-report-template.html (see scripts/vendor/VENDORED.md). The page
follows that skill's references/design.md, the same brand family as dacard.ai/update:

  - scorecard rows: the line and its definition, then prior -> actual . BUDGET x in mono with a range
    line beneath (grey dot prior, status dot actual, a tick at the budget, a green band under it), then
    the status word
  - plan against actual: budget grey above actual ink, hatched when over budget
  - labels in Geist Mono capitals, sentences in Geist, headings in Instrument Sans; hairlines, not boxes
  - green, grey-white and red are status only, and the word always prints beside the colour
  - an Illustrative tag when the prices are illustrative

Every figure on the page is a display string from the ledger; the page computes nothing but the
positions of marks. Every piece of text is escaped. The page needs no network.

Standard library only. Runs on Python 3.9 or later.
"""

from __future__ import annotations

import html
import math
from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "leader-report-template.html"
LABEL = {"tokens_per_task": "Tokens per task", "price_per_token": "Price per token", "cost_per_task": "Cost per task"}
DEFINITION = {
    "tokens_per_task": "Every token a task used (input, output, cache read, cache write), over tasks.",
    "price_per_token": "Priced cost over those tokens, so cheaper cache reads pull it down.",
    "cost_per_task": "Priced cost over tasks. Its budget is the brief's two lines multiplied.",
}
Json = dict[str, Any]

# Layout for a report page on top of the Leader Report stylesheet: no rail, sections instead of slides.
PAGE_CSS = """
main{margin-left:0}
.slide{min-height:0;padding:56px 40px 48px}
.slide.first{padding-top:64px}
.slide h1{font-size:clamp(36px,4.6vw,60px);max-width:22ch}
.brand{margin-bottom:32px}
.lede{max-width:64ch;color:var(--t2);font-size:15px;margin:0}
.sc{padding:0}
.sc-g:first-of-type{border-top:0}
.pv-wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:8px 40px}
.pv-wrap h3{margin:20px 0 4px}
td .sh{width:64px}
.notes{list-style:none;margin:0;padding:0}
.notes li{border-top:1px solid var(--line);padding:14px 0;color:var(--t2);font-size:13px;overflow-wrap:anywhere}
.notes li:first-child{border-top:0}
.scroll{overflow-x:auto}
.ledger td{font-size:12px}
.models code{white-space:nowrap}
@media (max-width:980px){.slide{padding:36px 16px 32px}.slide.first{padding-top:40px}}
@media (max-width:640px){.models td:first-child,.models th:first-child{display:none}}
@media (max-width:640px){.sc-h,.sc-r{grid-template-columns:minmax(0,1fr) auto;gap:10px 16px}.sc-h span:nth-child(2){display:none}.sc-v{grid-column:1/-1;grid-row:2}.sc-s{grid-column:2;grid-row:1}}
"""

BRAND = (
    '<div class="brand"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">'
    '<rect x="2" y="13" width="3" height="7" fill="var(--agent)"/><rect x="7" y="10" width="3" height="10" fill="var(--agent)"/>'
    '<rect x="12" y="2" width="1.5" height="20" fill="var(--brass)"/><rect x="16" y="4" width="4" height="16" fill="var(--t1)"/></svg>'
    '<span translate="no">DACARD</span></div>'
)


def stylesheet() -> str:
    """The Leader Report's style block (fonts and tokens included), from the vendored template."""
    text = TEMPLATE.read_text(encoding="utf-8")
    start, end = text.index("<style>") + len("<style>"), text.index("</style>")
    return text[start:end]


def e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def pct(v: float) -> str:
    """A mark position, rounded half up to one decimal so the page is the same on every run."""
    v = math.floor(max(0.0, min(v, 1.0)) * 1000 + 0.5) / 10
    return str(int(v)) if v == int(v) else str(v)


def status(word: str | None) -> str:
    if word in ("landed", "watch", "stalled"):
        return f'<span class="st {e(word)}">{e(word)}</span>'
    return '<span class="li-t">not checked</span>'


def range_line(c: Json) -> str:
    """Prior, actual and the budget on one line, as the scorecard draws them. Lower is better, so the band sits under the budget."""
    prior = c.get("prior")
    top = max(c["budget"], c["actual"], prior or 0) * 1.18 or 1
    b, a = c["budget"] / top, c["actual"] / top
    p = prior / top if prior is not None else a
    lo, hi = sorted((p, a))
    marks = [
        '<i class="tr"></i>',
        f'<i class="ok" style="left:0;width:{pct(b)}%"></i>',
        f'<i class="goal" style="left:{pct(b)}%"></i>',
        f'<i class="mv" style="left:{pct(lo)}%;width:{pct(hi - lo)}%"></i>' if prior is not None else "",
        f'<i class="pr" style="left:{pct(p)}%"></i>' if prior is not None else "",
        f'<i class="ac {e(c["status"])}" style="left:{pct(a)}%"></i>',
    ]
    return f'<span class="bl" aria-hidden="true">{"".join(marks)}</span>'


def figure_line(c: Json) -> str:
    prior = f"{e(c['prior_display'])} <i>&rarr;</i> " if c.get("prior_display") else ""
    since = f" &middot; {e(c['change_display'])} since prior" if c.get("change_display") else ""
    return f"{prior}<b>{e(c['actual_display'])}</b> &middot; <em>Budget</em> {e(c['budget_display'])} &middot; {e(c['over_display'])}{since}"


def scorecard(result: Json) -> str:
    rows = ['<div class="sc-h"><span>Line</span><span>Prior &rarr; actual &middot; budget</span><span>Status</span></div>']
    for f in result["features"]:
        rows.append(f'<div class="sc-g">{e(f["feature"])}</div>')
        if not f["checks"]:
            rows.append(f'<div class="sc-r"><div class="sc-n"><span>No line checked</span><span class="sc-d">{e("; ".join(f["gaps"]))}</span></div><div class="sc-v"></div><div class="sc-s">{status(None)}</div></div>')
        for key in ("tokens_per_task", "price_per_token", "cost_per_task"):
            c = f["checks"].get(key)
            if not c:
                continue
            rows.append(
                f'<div class="sc-r"><div class="sc-n"><span>{LABEL[key]}</span><span class="sc-d">{DEFINITION[key]}</span></div>'
                f'<div class="sc-v">{range_line(c)}<span class="sc-l">{figure_line(c)}</span></div>'
                f'<div class="sc-s">{status(c["status"])}</div></div>'
            )
    return f'<div class="sc">{"".join(rows)}</div>'


def plan_vs_actual(f: Json) -> str:
    rows = []
    for key in ("tokens_per_task", "price_per_token", "cost_per_task"):
        c = f["checks"].get(key)
        if not c:
            continue
        top = max(c["budget"], c["actual"]) or 1
        over = " over" if c["actual"] > c["budget"] else ""
        rows.append(
            f'<div class="pvr"><span>{LABEL[key]}</span><span class="v">{e(c["budget_display"])} / {e(c["actual_display"])}</span>'
            f'<div class="track"><div class="b" style="width:{pct(c["budget"] / top)}%"></div>'
            f'<div class="b a{over}" style="width:{pct(c["actual"] / top)}%"></div></div></div>'
        )
    return f'<div><h3>{e(f["feature"])}</h3><div class="pv">{"".join(rows)}</div></div>' if rows else ""


def headline(result: Json) -> str:
    if result["drivers"]:
        top = result["drivers"][0]
        f = next(x for x in result["features"] if x["feature"] == top["feature"])
        if f["drift"] > 0:
            return f"{f['feature']} is {f['drift_display']} over its cost budget, and {top['model']} drives the largest part."
        return f"{f['feature']} is within its cost budget overall, but {top['model']} runs over it."
    stalled = [f["feature"] for f in result["features"] if f.get("status") == "stalled"]
    if stalled:
        return f"{', '.join(stalled)}: a budget line is stalled."
    if any(f.get("status") for f in result["features"]):
        return "Every feature checked is within its cost budget."
    return "No feature could be checked against its cost budget."


def lede(result: Json) -> str:
    over = []
    for f in result["features"]:
        for key in ("tokens_per_task", "price_per_token", "cost_per_task"):
            c = f["checks"].get(key)
            if c and c["status"] != "landed":
                over.append(f"{LABEL[key].lower()} is {c['actual_display']} against {c['budget_display']} ({c['status']})")
    said = f" For {result['features'][0]['feature']}, " + "; ".join(over) + "." if over and len(result["features"]) == 1 else ""
    return (
        "Each feature's model spend against the cost budget in its landing brief: two lines, tokens per task and price per token, "
        f"and their product, cost per task.{said} A line over budget by no more than {result['tolerance'] * 100:.0f}% is watch; further over is stalled."
    )


def section(label: str, title: str, body: str) -> str:
    return f'<section class="slide"><div class="meta"><span>{e(label)}</span></div><h2>{e(title)}</h2>{body}</section>'


def render(result: Json) -> str:
    p = result["pricing"]
    window = result["window"] or f"{result['window_used']['from']}..{result['window_used']['to']}"
    ill = '<span class="ill">Illustrative</span>' if p["illustrative"] else ""
    prior = f"<span>Prior {e(result['prior_window'])}</span>" if result.get("prior_window") else ""
    facts = []
    for f in result["features"]:
        c = f["checks"].get("cost_per_task")
        if c:
            facts.append(f"<span><b>{e(c['actual_display'])}</b>{e(f['feature'])} cost per task</span>")
        if f.get("cost_display"):
            facts.append(f"<span><b>{e(f['cost_display'])}</b>{e(f['feature'])} priced</span>")
    for f in result["features"]:
        if f.get("drift", 0) > 0:
            facts.append(f"<span><b>{e(f['drift_display'])}</b>{e(f['feature'])} over budget</span>")
    if "reconcile" in result:
        facts.append(f"<span><b>{e(result['reconcile']['unattributed_display'])}</b>billed, not in the usage</span>")
    cover = (
        f'<section class="slide first">{BRAND}<div class="meta"><span>Cost budget check</span><span>{e(window)}</span>'
        f"{prior}<span>As of {e(result['as_of'])}</span>{ill}</div>"
        f"<h1>{e(headline(result))}</h1><p class='lede'>{e(lede(result))}</p>" + (f'<div class="facts">{"".join(facts)}</div>' if facts else "") + "</section>"
    )
    lines = section("Budget lines", "Each line against the brief's budget", scorecard(result))

    pv = "".join(plan_vs_actual(f) for f in result["features"])
    budget_vs = (
        section(
            "Budget against actual",
            "Budget grey, actual ink, hatched where over",
            '<div class="key"><span><i></i>Budget</span><span><i class="a"></i>Actual</span><span><i class="o"></i>Over budget</span></div>' + f'<div class="pv-wrap">{pv}</div>',
        )
        if pv
        else ""
    )

    model_rows = []
    for f in result["features"]:
        for m in f.get("models", []):
            model_rows.append(
                f'<tr><td>{e(f["feature"])}</td><td><code>{e(m["model"])}</code></td><td><span class="sh"><i style="width:{pct(m["share"])}%"></i></span>{e(m["share_display"])}</td>'
                f'<td class="num">{e(m["price_per_token_display"])}</td><td class="num">{e(m["cost_display"])}</td><td class="num">{e(m["drift_display"])}</td></tr>'
            )
    driver = (
        f"<p class='lede'>The driver is {e(result['drivers'][0]['feature'])} on {e(result['drivers'][0]['model'])}: {e(result['drivers'][0]['drift_display'])} of the cost over budget. "
        "Cost over budget is split by model as each model's cost minus its share of the budget by tokens, so the parts add up. It shows where the money went, not why.</p>"
        if result["drivers"]
        else "<p class='lede'>No feature and model is over budget.</p>"
    )
    models = (
        section(
            "Where the money went",
            "By feature and model",
            driver
            + '<div class="scroll" style="margin-top:24px"><table class="models"><thead><tr><th>Feature</th><th>Model</th><th>Share of tokens</th><th class="num">Price per token</th>'
            + f'<th class="num">Priced cost</th><th class="num">Over budget</th></tr></thead><tbody>{"".join(model_rows)}</tbody></table></div>',
        )
        if model_rows
        else ""
    )

    notes = []
    if "reconcile" in result:
        r = result["reconcile"]
        notes.append(("Bill", f"{r['billed_display']} billed, {r['priced_display']} priced from usage, {r['unattributed_display']} not in the usage given."))
    notes += [("Gap", f"{f['feature']}: {g}") for f in result["features"] for g in f["gaps"]]
    notes += [("Tasks", f"{f['feature']}: {f['tasks_source']}.") for f in result["features"] if f.get("tasks_source")]
    notes += [("No brief", f"{u['feature']}: {u['cost_display']} priced, with no landing brief, so no budget to check.") for u in result["unbriefed"]]
    notes += [("Warning", w) for w in result["warnings"]]
    notes += [("Read", n) for n in result["notes"]]
    notes.append(("Prices", f"{p['file']}: {p['source'].rstrip('.')}, retrieved {p['retrieved']}, {p['currency']}."))
    data_notes = section("Data notes", "What was read, and what is missing", '<ul class="notes">' + "".join(f'<li><span class="li-t">{e(t)}</span>{e(x)}</li>' for t, x in notes) + "</ul>")

    ledger_rows = "".join(f'<tr><td><code>{e(r["id"])}</code></td><td class="num">{e(r["display"])}</td><td>{e(r["formula"])}</td><td>{e("; ".join(r["sources"]))}</td></tr>' for r in result["ledger"])
    ledger = section(
        "Evidence ledger",
        "Every figure, its formula and sources",
        f'<details><summary>Show all {len(result["ledger"])} figures</summary><div class="scroll ledger"><table><thead><tr><th>ID</th><th class="num">Figure</th><th>Formula</th><th>Sources</th></tr></thead>'
        f"<tbody>{ledger_rows}</tbody></table></div></details>"
        f'<p class="asof" style="margin-top:24px">cost-budget-check {e(result["version"])}. Every figure is computed in code by scripts/check.py; this page computes none.</p>',
    )
    return (
        "\n".join(
            [
                "<!DOCTYPE html>",
                '<html lang="en">',
                '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
                f"<title>Cost budget check: {e(window)}</title>",
                f"<style>{stylesheet()}{PAGE_CSS}</style></head>",
                "<body><main>",
                cover,
                lines,
                budget_vs,
                models,
                data_notes,
                ledger,
                "</main></body></html>",
            ]
        )
        + "\n"
    )
