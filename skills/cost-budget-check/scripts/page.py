#!/usr/bin/env python3
"""Render cost_check.json as one self-contained HTML page, on the Leader Report's template and the Landing
Loop's one visual family.

The stylesheet, tokens and fonts are the Leader Report's own, read at render time from its template, vendored
byte-identical as assets/leader-report-template.html (see scripts/vendor/VENDORED.md). The pictures are drawn
with svgkit (scripts/vendor/svgkit.py, vendored byte-identical from landing-loop and pinned in
scripts/vendor/VENDORED.json). Only a few rules for this page's layout are added.

It reads top down for someone who has never seen a token: the shared header, the verdict as the heading, the
budget word, then one picture per project: each budget line as a bar against its budget notch, the part over
hatched, and the cost over budget split by model. Then one thing to do next, owned by the person the landing
brief names, and the detail in two columns. Model ids, line keys, flags, files and the evidence ledger fold
under "For your engineers". Public copy uses plain words: AI usage per task, AI price per unit, cheaper repeat
reads, the large model.

within budget and over budget are this check's own words and print in ink. Green, grey-white and red mean a
project's landed, watch and stalled, which only did-it-land sets, so this page uses none of them. Brass is the
person who decides the next step. Every figure is a display string from the ledger; the page computes only the
positions of marks. Every piece of text is escaped. The page needs no network.

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import datetime
import html
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import svgkit as sk  # noqa: E402  (vendored, unchanged; see vendor/VENDORED.json)

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "leader-report-template.html"
LINES = ("tokens_per_task", "price_per_token", "cost_per_task")
LABEL = {"tokens_per_task": "AI usage per task", "price_per_token": "AI price per unit", "cost_per_task": "Cost per task"}
LOWER = {"tokens_per_task": "AI usage per task", "price_per_token": "AI price per unit", "cost_per_task": "cost per task"}
DEFINITION = {
    "tokens_per_task": "How much text the AI reads and writes for one task, counted in units the provider bills by.",
    "price_per_token": "What those units cost on average. Cheaper repeat reads pull it down; a dearer model pushes it up.",
    "cost_per_task": "What one task costs. Its budget is the other two budgets multiplied.",
}
BRIEF_MEANS = "the landing brief, a one-page plan: what good looks like, by when, at what cost"
NEXT_STEP_DAYS = 14
Json = dict[str, Any]

# Public copy for stored sentences (gaps, warnings): plain words, no flags or files. Longer phrases first.
WORDS = (
    (r" Pass --tasks or log a task id per request\.", " Add a count of tasks, or log a task id with each request."),
    (r" Pass --[\w-]+[^.]*\.", ""),
    (r"\btokens per task\b", "AI usage per task"),
    (r"\bprice per token\b", "AI price per unit"),
    (r"\bcache reads\b", "cheaper repeat reads"),
    (r"\busage rows\b", "usage records"),
    (r"\bthe feature tag\b", "the project label"),
    (r"\bthe export's own cost\b", "the provider's own cost figure"),
    (r"\bthe export\b", "the usage export"),
    (r"\bthe pricing table\b", "the price list"),
    (r"\bno model budget\b", "no AI budget"),
    (r"\bfeature\b", "project"),
    (r"\bbet\b", "project"),
)

# Layout for this page only. Everything else comes from the template's stylesheet and svgkit.CSS.
PAGE_CSS = """
main.solo{margin-left:0}
.solo .slide{min-height:0}
.solo .slide.cover{min-height:0;padding-top:40px;padding-bottom:48px;justify-content:flex-start}
.solo h1{font-size:clamp(34px,4.6vw,60px);line-height:1;letter-spacing:-.04em;max-width:22ch;margin-bottom:20px}
.solo .lede{margin-bottom:24px}
.bud{display:inline-block;font:400 10px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t1);border:1px solid var(--line3);border-radius:3px;padding:1px 6px;white-space:nowrap}
.bud.over{background:var(--t1);color:var(--bg);border-color:var(--t1)}
.verdict{margin:0 0 20px}
.panel{border:1px solid var(--line);border-radius:12px;background:var(--s1);padding:24px 28px 20px}
.panel h3{margin:0 0 14px}
.panel .sk+h3{margin-top:32px}
@media (min-width:1100px){.panel .sk{display:grid;grid-template-columns:720px minmax(0,1fr);gap:16px 40px;align-items:center}.panel .sk figcaption{margin-top:0;flex-direction:column;align-items:flex-start}}
.next{margin-top:28px;display:grid;grid-template-columns:200px minmax(0,1fr);gap:8px 32px;align-items:baseline;border:1px solid var(--brass);border-radius:12px;padding:20px 24px;background:var(--brass-bg)}
.next>b{font:400 10px/22px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--brass)}
.next p{margin:0;font-size:16px;line-height:1.5;color:var(--t1)}
.next p+p{margin-top:8px}
.next .who{display:flex;flex-wrap:wrap;gap:4px 24px;margin-top:10px;font:400 11.5px/16px var(--mono);color:var(--brass)}
.next .who span::before{font-size:10px;letter-spacing:.1em;color:var(--t3);margin-right:8px}
.next .who .o::before{content:"DECIDES"}.next .who .d::before{content:"DUE"}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px 56px;align-items:start}
.cols h3{margin-bottom:8px}
.cols h3:not(:first-child){margin-top:28px}
.figs{margin:0;display:grid}
.figs>div{display:grid;grid-template-columns:150px minmax(0,1fr);gap:4px 16px;border-top:1px solid var(--line);padding:11px 0}
.figs dt .bud{margin-top:4px}
.figs dt{font:400 10px/22px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
.figs dd{margin:0;font-size:13.5px;line-height:1.55;color:var(--t2)}
.figs dd b{color:var(--t1);font-weight:500}
.figs dd small{display:block;font-size:12.5px;color:var(--t3);margin-top:2px}
.plain{margin:0;padding:0;list-style:none}
.plain li{border-top:1px solid var(--line);padding:11px 0;font-size:13px;line-height:1.5;color:var(--t2)}
.sc-d{font-size:12.5px;line-height:1.5;color:var(--t3);margin:0 0 8px}
.solo details{margin-top:4px}
.solo details>*:not(summary){margin-top:12px}
.solo details p,.solo details li{margin:0 0 10px;font-size:13px;color:var(--t2);max-width:80ch}
.solo details ul{padding-left:18px}
.tablewrap td,.tablewrap th{overflow-wrap:anywhere}
.tablewrap .ex{font-size:12px;color:var(--t3)}
::selection{background:var(--t1);color:var(--bg)}
:focus-visible{outline-color:var(--t1)}
.foot{max-width:1120px;margin:0 auto;padding:28px 40px 64px;color:var(--t3);font-size:12px}
@media (max-width:980px){.foot{padding:24px 16px 48px}.solo .slide.cover{padding-top:24px}.cols,.next{grid-template-columns:1fr}.panel{padding:18px 16px 16px}
.stack table,.stack tbody,.stack tr,.stack td{display:block}.stack tr:first-child{display:none}.stack tr{padding:10px 16px;border-bottom:1px solid var(--line)}
.stack td{border:0;padding:3px 0;display:grid;grid-template-columns:104px 1fr;gap:12px}.stack td.num{text-align:left;white-space:normal}
.stack td::before{content:attr(data-l);font:400 10px/20px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}}
@media (max-width:560px){.figs>div{grid-template-columns:1fr;gap:0}}
"""


def stylesheet() -> str:
    """The Leader Report's style block (fonts and tokens included), from the vendored template."""
    text = TEMPLATE.read_text(encoding="utf-8")
    start, end = text.index("<style>") + len("<style>"), text.index("</style>")
    return text[start:end]


def e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def plain(text: str) -> str:
    for pattern, to in WORDS:
        text = re.sub(pattern, to, text)
    return text


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def name(f: Json) -> str:
    """What a page calls a feature: its brief's title, so a leader reads "Quote drafting", not the slug."""
    return f.get("title") or f["feature"]


def name_of(result: Json, feature: str) -> str:
    return next((name(f) for f in result["features"] if f["feature"] == feature), feature)


def model_names(result: Json) -> dict[str, str]:
    """Plain names for the models, by price per unit across the whole check: the dearest is the large model.

    Model ids are vendor words; they print only in the engineers' fold."""
    price: dict[str, float] = {}
    for f in result["features"]:
        for m in f.get("models", []):
            if m["tokens"]:
                price[m["model"]] = max(price.get(m["model"], 0.0), m["cost"] / m["tokens"])
    ranked = sorted(price, key=lambda k: (-price[k], k))
    if len(ranked) == 1:
        return {ranked[0]: "the model"}
    names = {ranked[0]: "the large model", ranked[-1]: "the standard model"}
    middle = ranked[1:-1]
    for i, model in enumerate(middle, start=1):
        names[model] = "the mid-size model" if len(middle) == 1 else f"mid-size model {i}"
    return names


def headline(result: Json) -> str:
    models = model_names(result)
    if result["drivers"]:
        top = result["drivers"][0]
        f = next(x for x in result["features"] if x["feature"] == top["feature"])
        if f["drift"] > 0:
            return f"{name(f)} is {f['drift_display']} over its cost budget, and {models.get(top['model'], top['model'])} drives the largest part."
        return f"{name(f)} is within its cost budget overall, but {models.get(top['model'], top['model'])} runs over it."
    over = [name(f) for f in result["features"] if f.get("status") == "over budget"]
    if over:
        return f"{', '.join(over)}: a budget line is over budget."
    if any(f.get("status") for f in result["features"]):
        return "Every project checked is within its cost budget."
    return "No project could be checked against its cost budget."


def window_text(result: Json) -> str:
    w = result["window"] or f"{result['window_used']['from']}..{result['window_used']['to']}"
    a, _, b = w.partition("..")
    return f"{a} to {b}" if b else w


def lede(result: Json) -> str:
    one = len(result["features"]) == 1
    said = ""
    if one:
        f = result["features"][0]
        c = f["checks"].get("cost_per_task")
        if c:
            said = f" From {window_text(result)}, each task cost {c['actual_display']} against a budget of {c['budget_display']} ({c['over_display']})."
    return f"Each project's AI spend against the cost budget in {BRIEF_MEANS}. The budget is two lines, AI usage per task and AI price per unit; multiplied, they give cost per task.{said}"


def part(top: Json, f: Json) -> str:
    """The driver's share of the project's cost over budget, said so the parts add up."""
    if 0 < top["drift"] <= f["drift"]:
        return f"{top['drift_display']} of the {f['drift_display']} over budget"
    return f"{top['drift_display']} over budget on its own, {f['drift_display']} for the project in all"


def next_step(result: Json) -> tuple[str, str, str]:
    """One step, who decides it and when: the largest part over budget first."""
    as_of = datetime.date.fromisoformat(result["as_of"])
    due = str(as_of + datetime.timedelta(days=NEXT_STEP_DAYS))
    models = model_names(result)
    if result["drivers"]:
        top = result["drivers"][0]
        f = next(x for x in result["features"] if x["feature"] == top["feature"])
        lines = [LOWER[k] for k in LINES if f["checks"].get(k, {}).get("status") == "over budget" and k != "cost_per_task"]
        rise = f" and the rise in {' and '.join(lines)}" if lines else ""
        text = f"Review the {name(f)} work sent to {models.get(top['model'], top['model'])} ({part(top, f)}){rise}. Then bring cost per task back under budget, or change the budget in the landing brief, and run this check again."
        return text, f.get("decides") or "", due
    over = [f for f in result["features"] if f.get("status") == "over budget"]
    if over:
        f = over[0]
        return f"Look at why {name(f)} runs over a budget line, then run this check again.", f.get("decides") or "", due
    checked = [f for f in result["features"] if f.get("status")]
    if checked:
        return "Nothing to change. Run this check again on the next period of usage.", checked[0].get("decides") or "", due
    return "Fix what stopped the check, listed below, then run it again.", "", due


# The signature picture


def line_sentence(c: Json, key: str) -> str:
    return f"{LOWER[key]} {c['actual_display']} against {c['budget_display']} ({c['over_display']}, {c['status']})"


def answer(result: Json, f: Json) -> str:
    """The aria-label: the verdict for this project, in one sentence."""
    lines = [line_sentence(f["checks"][k], k) for k in LINES if k in f["checks"]]
    text = f"{name(f)} is {f.get('status') or 'not checked'}: " + "; ".join(lines)
    models = model_names(result)
    over = [m for m in f.get("models", []) if m["drift"] > 0]
    if over and f.get("drift", 0) > 0:
        top = max(over, key=lambda m: m["drift"])
        text += f". {cap(models.get(top['model'], top['model']))} drives the largest part: {part(top, f)}"
    return text + "."


def bars(result: Json, f: Json, index: int, variant: str) -> str:
    """Each budget line as a bar against its budget notch, the part over hatched; a hollow dot marks the two
    period before. Under them, the cost over budget split by model, the largest part in ink."""
    wide = variant == "wide"
    width = float(sk.WIDE if wide else sk.TALL)
    track = 470.0 if wide else width
    hid = f"sk-cb-{index}-{variant}"
    parts = [sk.defs(sk.hatch_pattern(hid))]
    y = 14.0
    for key in LINES:
        c = f["checks"].get(key)
        if not c:
            continue
        prior = c.get("prior")
        top = max(c["budget"], c["actual"], prior or 0) * 1.12 or 1
        x = sk.scale((0, top), (0, track))
        parts.append(sk.label(0, y, LABEL[key], tone=sk.INK))
        bar_y = y + 12
        if wide:
            parts.append(sk.label(x(c["budget"]), y, "budget", anchor="middle"))
            parts.append(sk.value(492, bar_y + 11, c["actual_display"], size=16))
            parts.append(sk.label(492, bar_y + 29, f"budget {c['budget_display']} · {c['over_display']}"))
        else:
            parts.append(sk.value(width, y + 1, c["actual_display"], anchor="end", size=15))
        parts.append(sk.rule(0, bar_y + 6, track, bar_y + 6, tone=sk.LINE))
        parts.append(sk.hbar(0, bar_y, actual=x(c["actual"]), budget=x(c["budget"]), height=12, tone=sk.INK2, hatch_id=hid))
        if prior is not None:
            parts.append(sk.hollow(x(prior), bar_y + 6, r=3.5, tone=sk.INK))
        if wide:
            y = bar_y + 56
        else:
            parts.append(sk.label(0, bar_y + 32, f"budget {c['budget_display']} · {c['over_display']}"))
            y = bar_y + 62
    over = sorted((m for m in f.get("models", []) if m["drift"] > 0), key=lambda m: -m["drift"])
    if over:
        models = model_names(result)
        y += 6
        parts.append(sk.rule(0, y - 14, width, y - 14, tone=sk.LINE))
        parts.append(sk.label(0, y + 6, f"Over budget by model · {f['drift_display']}", tone=sk.INK))
        total = sum(m["drift"] for m in over)
        x = sk.scale((0, total), (0, track))
        at, sy = 0.0, y + 18
        for i, m in enumerate(over):
            w = x(m["drift"])
            fill = sk.INK if i == 0 else sk.MUTED
            parts.append(sk.tile(at, sy, max(1.0, w - (2 if i < len(over) - 1 else 0)), 14, filled=True, tone=fill))
            at += w
        ky = sy + 38
        for i, m in enumerate(over):
            tone = sk.INK if i == 0 else sk.MUTED
            parts.append(sk.tile(0, ky - 9, 10, 10, filled=True, tone=tone))
            parts.append(sk.value(18, ky, cap(models.get(m["model"], m["model"])), size=14, tone=sk.INK if i == 0 else sk.INK2))
            right = 492 if wide else width
            parts.append(sk.value(right, ky, m["drift_display"], anchor="start" if wide else "end", size=14, tone=sk.INK if i == 0 else sk.INK2))
            if wide:
                parts.append(sk.label(570, ky, f"{m['share_display']} of usage"))
            ky += 24
        y = ky - 10
    return sk.frame("".join(parts), label=answer(result, f), height=y + 4, width=width, variant=variant)


# The detail


class Table:
    """A table whose cells carry their column name, so a phone shows each row as labelled lines."""

    def __init__(self, heads: tuple[str, ...]) -> None:
        self.heads = heads
        self.rows: list[str] = []

    def row(self, *cells: tuple[str, str]) -> None:
        tds = []
        for head, (cls, body) in zip(self.heads, cells, strict=True):
            attr = f' class="{cls}"' if cls else ""
            tds.append(f'<td{attr} data-l="{e(head)}">{body}</td>')
        self.rows.append("<tr>" + "".join(tds) + "</tr>")

    def html(self) -> str:
        head = "<tr>" + "".join(f"<th>{e(h)}</th>" for h in self.heads) + "</tr>"
        return f'<div class="tablewrap stack"><table>{head}{"".join(self.rows)}</table></div>'


def status(word: str | None) -> str:
    """within budget or over budget, as plain words in ink, with no status colour."""
    if word in ("within budget", "over budget"):
        return f'<span class="bud{" over" if word == "over budget" else ""}">{e(word)}</span>'
    return '<span class="bud">not checked</span>'


def lines_list(result: Json) -> str:
    out = []
    many = len(result["features"]) > 1
    for f in result["features"]:
        rows = []
        for key in LINES:
            c = f["checks"].get(key)
            if not c:
                continue
            since = f" The period before: {e(c['prior_display'])} ({e(c['change_display'])} since)." if c.get("prior_display") else ""
            rows.append(f"<div><dt>{LABEL[key]}<br>{status(c['status'])}</dt><dd><b>{e(c['actual_display'])}</b> against a budget of {e(c['budget_display'])}, {e(c['over_display'])}.<small>{DEFINITION[key]}{since}</small></dd></div>")
        if not rows:
            rows.append(f"<div><dt>Not checked</dt><dd>{e(plain('; '.join(f['gaps'])))}</dd></div>")
        head = f"<h3>{e(name(f))}</h3>" if many else ""
        out.append(f'{head}<dl class="figs">{"".join(rows)}</dl>')
    return "".join(out)


def money_list(result: Json) -> str:
    models = model_names(result)
    rows = []
    for f in result["features"]:
        for m in sorted(f.get("models", []), key=lambda m: -m["drift"]):
            who = cap(models.get(m["model"], m["model"])) + (f" on {name(f)}" if len(result["features"]) > 1 else "")
            rows.append(f"<div><dt>{e(who)}</dt><dd><b>{e(m['drift_display'])}</b> over budget. {e(m['share_display'])} of the AI usage, {e(m['cost_display'])} spent, {e(m['price_per_token_display'])} a unit.</dd></div>")
        if f.get("cost_display"):
            tasks = f" over {e(f['tasks_display'])} tasks" if f.get("tasks_display") else ""
            rows.append(f"<div><dt>{e(name(f))} in all</dt><dd><b>{e(f['cost_display'])}</b> spent{tasks}; {e(f.get('drift_display', ''))} over budget.</dd></div>")
        if f.get("cost_per_success_display"):
            rows.append(
                f"<div><dt>Per task that worked</dt><dd>{e(f['success_rate_display'])} of tasks succeeded, so each one that worked cost "
                f"<b>{e(f['cost_per_success_display'])}</b>. No budget line covers it; it is shown, not marked.</dd></div>"
            )
    for u in result["unbriefed"]:
        rows.append(f"<div><dt>No plan</dt><dd>{e(u['feature'])}: <b>{e(u['cost_display'])}</b> spent with no landing brief, so no budget to check.</dd></div>")
    if "reconcile" in result:
        r = result["reconcile"]
        rows.append(f"<div><dt>The bill</dt><dd><b>{e(r['billed_display'])}</b> billed; {e(r['priced_display'])} priced from usage; {e(r['unattributed_display'])} not in the usage given.</dd></div>")
    if not rows:
        return "<p class='sc-d'>No spend to split.</p>"
    lede = "Cost over budget is split by model as each model's cost minus its share of the budget by usage, so the parts add up. It shows where the money went, not why."
    return f"<p class='sc-d'>{lede}</p><dl class='figs'>{''.join(rows)}</dl>"


def worth_knowing(result: Json) -> list[str]:
    items = [f"{name(f)}: {plain(g)}" for f in result["features"] for g in f["gaps"]]
    items += [cap(plain(w)) for w in result["warnings"]]
    p = result["pricing"]
    ill = " They are illustrative, not any provider's list price." if p["illustrative"] else ""
    items.append(f"Prices were retrieved {p['retrieved']}, in {p['currency']}.{ill}")
    return items


def engineers(result: Json) -> str:
    models = model_names(result)
    eng = []
    if models:
        eng.append("<p>Models: " + "; ".join(f"{e(n)} is <code>{e(m)}</code>" for m, n in models.items()) + ".</p>")
    eng.append(
        "<p>Line keys: <code>tokens_per_task</code> (AI usage per task, in tokens: input, output, cache read and cache write), "
        "<code>price_per_token</code> (AI price per unit: priced cost over tokens, so cache reads pull it down) and <code>cost_per_task</code>.</p>"
    )
    t = Table(("Feature", "Model", "Share of tokens", "Price per token", "Priced cost", "Over budget"))
    for f in result["features"]:
        for m in f.get("models", []):
            t.row(("", e(f["feature"])), ("", f"<code>{e(m['model'])}</code>"), ("num", e(m["share_display"])), ("num", e(m["price_per_token_display"])), ("num", e(m["cost_display"])), ("num", e(m["drift_display"])))
    if t.rows:
        eng.append(t.html())
    notes = [f"{f['feature']}: tasks from {f['tasks_source']}." for f in result["features"] if f.get("tasks_source")]
    notes += [f"Read: {n}" for n in result["notes"]]
    notes += [f"{f['feature']}: {g}" for f in result["features"] for g in f["gaps"]]
    p = result["pricing"]
    notes.append(f"Prices: {p['file']}, {p['source'].rstrip('.')}, retrieved {p['retrieved']}, {p['currency']}.")
    eng.append("<ul>" + "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul>")
    gate = f" --tolerance {result['tolerance']:g} lets a line run that share over budget before the gate fails; the line still reads over budget." if result["tolerance"] else ""
    eng.append(
        "<p>With --landing and --bet, the run adds its page to the project file: the <code>cost</code> key of <code>landing/&lt;bet&gt;.json</code>, and no other key. "
        f"--fail-on over-budget turns the check into a CI gate (exit code 2).{e(gate)}</p>"
    )
    lt = Table(("ID", "Figure", "Formula", "Sources"))
    for r in result["ledger"]:
        lt.row(("", f"<code>{e(r['id'])}</code>"), ("num", e(r["display"])), ("", e(r["formula"])), ("ex", e("; ".join(r["sources"]))))
    eng.append(f"<p>Every figure, its formula and sources ({len(result['ledger'])} in all):</p>" + lt.html())
    eng.append(f"<p>cost-budget-check {e(result['version'])}. Every figure is computed in code by scripts/check.py; this page computes none.</p>")
    return f"<details><summary>For your engineers</summary>{''.join(eng)}</details>"


def render(result: Json) -> str:
    p = result["pricing"]
    header = sk.page_header("cost-budget-check", date=result["as_of"], version=f"v{result['version']}", illustrative=p["illustrative"])
    pics = []
    checked = [f for f in result["features"] if f["checks"]]
    for i, f in enumerate(checked):
        cap_text = (
            "Each bar is a line's actual figure against its budget notch; the hatched part is over budget. "
            + ("The open dot is the period before. " if any("prior" in c for c in f["checks"].values()) else "")
            + ("Under them, the cost over budget split by model, the largest part in ink." if any(m["drift"] > 0 for m in f.get("models", [])) else "")
        )
        head = f"<h3>{e(name(f))}</h3>" if len(checked) > 1 else ""
        pics.append(head + sk.figure(bars(result, f, i, "wide"), bars(result, f, i, "tall"), caption=cap_text.strip(), illustrative=p["illustrative"]))
    overall = "over budget" if any(f.get("status") == "over budget" for f in result["features"]) else ("within budget" if checked else None)
    text, decides, due = next_step(result)
    who = f'<span class="o">{e(decides)}</span>' if decides else ""
    step = f'<div class="next"><b>What to do next</b><div><p>{e(text)}</p><span class="who">{who}<span class="d">{e(due)}</span></span></div></div>'
    panel = f'<div class="panel">{"".join(pics)}</div>' if pics else ""
    cover = f'<section class="slide cover">{header}<h1>{e(headline(result))}</h1><p class="lede">{e(lede(result))}</p><p class="verdict">{status(overall)}</p>{panel}{step}</section>'
    notes = "".join(f"<li>{e(n)}</li>" for n in worth_knowing(result))
    before = f" The period before is {e(window_text({'window': result['prior_window'], 'window_used': {}}))}." if result.get("prior_window") else ""
    detail = (
        f'<section class="slide"><div class="meta"><span>{e(window_text(result))}</span></div><div class="cols">'
        f"<div><h3>Each line against the budget</h3><p class='sc-d'>Usage from {e(window_text(result))}.{before}</p>{lines_list(result)}</div>"
        f"<div><h3>Where the money went</h3>{money_list(result)}<h3>Worth knowing</h3><ul class='plain'>{notes}</ul></div>"
        "</div></section>"
    )
    more = f'<section class="slide"><div class="meta"><span>Detail</span></div>{engineers(result)}</section>'
    title = f"Cost budget check: {window_text(result)}"
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><style>{stylesheet()}{sk.CSS}{PAGE_CSS}</style></head><body><main class="solo">{cover}{detail}{more}'
        '<p class="foot">A cost check says whether AI spend stays inside the budget the plan set. It is not the project\'s result: only did-it-land reads that. '
        "It shows where the money went, not why.</p></main></body></html>\n"
    )
