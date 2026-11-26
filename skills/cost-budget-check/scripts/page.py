#!/usr/bin/env python3
"""Render cost_check.json as one self-contained HTML page in the Leader Report's style guide.

The rules come from the Leader Report's references/design.md and assets/template.html:

  - numbers get a picture: each budget line has paired bars, budget grey above actual ink, hatched
    when over; a share column gets a bar against 100
  - labels in Geist Mono capitals, sentences in Geist, headings in Instrument Sans
  - hairlines, not boxes; dark first; prints in light ink
  - green, grey-white and red are status only, and the word always prints beside the colour
  - one line per figure: prior -> actual . BUDGET x, in mono, with the actual in ink

The fonts are embedded from assets/fonts.css, so the page needs no network. Every figure on the page is
a display string from the ledger; the page computes nothing but bar widths. Every piece of text is
escaped.

Standard library only. Runs on Python 3.9 or later.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts.css"
LABEL = {"tokens_per_task": "Tokens per task", "price_per_token": "Price per token", "cost_per_task": "Cost per task"}
Json = dict[str, Any]

CSS = """
:root{color-scheme:dark;
  --bg:#0A0A0A;--s1:#121212;--s3:#1D1D1B;
  --line:rgba(242,242,239,.08);--line2:rgba(242,242,239,.15);--line3:rgba(242,242,239,.24);
  --t1:#F2F2EF;--t2:#B9B9B4;--t3:#97968F;--brass:#E3A948;--agent:#8F8B83;--agent-mid:#6E6A62;
  --landed:#5CD38C;--watch:#D6D6D1;--stalled:#F0654F;
  --sans:"Geist",system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --display:"Instrument Sans","Geist",system-ui,sans-serif;
  --mono:"Geist Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--t1);font-family:var(--sans);font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
main{max-width:1080px;margin:0 auto;padding:40px 40px 80px}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:15px;letter-spacing:-.01em}
.lab,th,h3{font:400 10px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3)}
h1{font-family:var(--display);font-weight:600;font-size:clamp(32px,4.4vw,56px);font-stretch:88%;line-height:1;letter-spacing:-.045em;margin:28px 0 16px;text-wrap:pretty}
h2{font-family:var(--display);font-weight:600;font-size:clamp(22px,2.4vw,30px);font-stretch:90%;line-height:1.1;letter-spacing:-.03em;margin:56px 0 18px}
p{color:var(--t2);max-width:760px;overflow-wrap:anywhere}
section{border-top:1px solid var(--line);margin-top:40px;padding-top:8px}
.st{display:inline-flex;align-items:center;gap:7px;font:400 10px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;white-space:nowrap}
.st::before{content:"";width:7px;height:7px;border-radius:2px;background:currentColor;flex:none}
.st.watch::before{width:8px;height:8px;border-radius:50%;background:none;border:1.5px solid currentColor}
.st.landed{color:var(--landed)}.st.watch{color:var(--watch)}.st.stalled{color:var(--stalled)}
.ill{display:inline-flex;align-items:center;font:400 10px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t2);background:var(--s3);border-radius:4px;padding:2px 7px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(180px,100%),1fr));border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:28px 0}
.fact{padding:22px 24px 20px 0}.fact+.fact{border-left:1px solid var(--line);padding-left:24px}
.fact b{display:block;font:600 30px/1.1 var(--display);letter-spacing:-.03em;font-variant-numeric:tabular-nums}

.feat{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:0 36px}
.pvr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 16px;align-items:center;border-top:1px solid var(--line);padding:16px 0}
.pvr .name{color:var(--t1)}
.track{grid-column:1/-1;display:grid;gap:3px}
.b{height:6px;border-radius:1px;background:var(--agent-mid)}.b.a{background:var(--t1)}
.b.a.over{background:repeating-linear-gradient(135deg,var(--t1) 0 4px,transparent 4px 7px);outline:1px solid var(--t1);outline-offset:-1px}
.fl{grid-column:1/-1;overflow-wrap:anywhere;font:400 11.5px var(--mono);font-variant-numeric:tabular-nums;color:var(--t3)}.fl .act{color:var(--t1)}
.key{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 6px}.key i{display:inline-block;width:14px;height:8px;border-radius:2px;margin-right:6px;background:var(--agent-mid);vertical-align:middle}.key i.a{background:var(--t1)}
.key i.o{background:repeating-linear-gradient(135deg,var(--t1) 0 3px,transparent 3px 5px);outline:1px solid var(--t1);outline-offset:-1px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;padding:14px 18px 12px 0;border-bottom:1px solid var(--line2);white-space:nowrap}
td{padding:13px 18px 13px 0;border-bottom:1px solid var(--line);vertical-align:top;color:var(--t2)}
tr:last-child td{border-bottom:0}td:first-child{color:var(--t1)}
td.num,th.num{text-align:right;white-space:nowrap;font-family:var(--mono);font-variant-numeric:tabular-nums}
.share{display:inline-block;width:64px;height:6px;background:var(--line2);border-radius:1px;margin-right:10px;vertical-align:middle;position:relative}
.share i{position:absolute;inset:0 auto 0 0;background:var(--t2);border-radius:1px}
ul.notes{list-style:none;padding:0;margin:0}ul.notes li{border-top:1px solid var(--line);padding:12px 0;color:var(--t2)}
ul.notes .tag{font:400 10px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3);margin-right:10px}
details summary{cursor:pointer;font:400 10px/16px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--t3);padding:12px 0}
code{font-family:var(--mono);font-size:11.5px;color:var(--t2)}
footer{margin-top:56px;border-top:1px solid var(--line);padding-top:16px;color:var(--t3);font-size:12px}
@media (max-width:640px){main{padding:24px 16px 56px}.fact+.fact{border-left:0;padding-left:0}.fact{border-top:1px solid var(--line)}}
@media print{:root{color-scheme:light;--bg:#fff;--t1:#111;--t2:#333;--t3:#555;--line:rgba(0,0,0,.12);--line2:rgba(0,0,0,.2);--agent-mid:#999;--s3:#eee;--watch:#666}
  body{font-size:11px}main{padding:0}@page{size:A4 landscape;margin:14mm}details{display:block}details>*{display:block}}
"""

MARK = (
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">'
    '<rect x="2" y="13" width="3" height="7" fill="var(--agent)"/><rect x="7" y="10" width="3" height="10" fill="var(--agent)"/>'
    '<rect x="12" y="2" width="1.5" height="20" fill="var(--brass)"/><rect x="16" y="4" width="4" height="16" fill="var(--t1)"/></svg>'
)


def e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def status(word: str | None) -> str:
    return f'<span class="st {e(word)}">{e(word)}</span>' if word in ("landed", "watch", "stalled") else '<span class="lab">not checked</span>'


def bars(c: Json) -> str:
    top = max(c["budget"], c["actual"], c.get("prior") or 0) or 1
    over = " over" if c["actual"] > c["budget"] else ""
    return f'<div class="track"><div class="b" style="width:{c["budget"] / top * 100:.1f}%" title="budget"></div><div class="b a{over}" style="width:{c["actual"] / top * 100:.1f}%" title="actual"></div></div>'


def figure_line(c: Json) -> str:
    prior = f"{e(c['prior_display'])} &rarr; " if c.get("prior_display") else ""
    since = f" &middot; {e(c['change_display'])} since prior" if c.get("change_display") else ""
    return f'<div class="fl">{prior}<span class="act">{e(c["actual_display"])}</span> &middot; BUDGET {e(c["budget_display"])} &middot; {e(c["over_display"])}{since}</div>'


def headline(result: Json) -> str:
    stalled = [f for f in result["features"] if f.get("status") == "stalled"]
    if result["drivers"]:
        top = result["drivers"][0]
        return f"{top['feature']} is {top['drift_display']} over budget, most of it on {top['model']}."
    if stalled:
        return f"{', '.join(f['feature'] for f in stalled)}: a budget line is stalled."
    if any(f.get("status") for f in result["features"]):
        return "Every feature checked is within its cost budget."
    return "No feature could be checked against its cost budget."


def render(result: Json) -> str:
    p = result["pricing"]
    window = result["window"] or f"{result['window_used']['from']}..{result['window_used']['to']}"
    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>Cost budget check, {e(window)}</title>",
        f"<style>{FONTS.read_text(encoding='utf-8')}{CSS}</style></head><body><main>",
        f'<div class="brand">{MARK}<span translate="no">DACARD</span><span class="lab">&nbsp;Cost budget check</span></div>',
    ]
    tags = ['<span class="ill">Illustrative prices</span>'] if p["illustrative"] else []
    out.append(f'<p class="lab">{e(window)} &middot; as of {e(result["as_of"])}' + (f" &middot; prior {e(result['prior_window'])}" if result.get("prior_window") else "") + f" {' '.join(tags)}</p>")
    out.append(f"<h1>{e(headline(result))}</h1>")
    out.append(
        f"<p>Each feature's spend against the cost budget in its landing brief: tokens per task and price per token, and their product, cost per task. "
        f"A line over budget by no more than {result['tolerance'] * 100:.0f}% is watch; further over is stalled. Status is always against the budget.</p>"
    )
    facts = []
    for f in result["features"]:
        if f.get("cost_display"):
            facts.append(f'<div class="fact"><b>{e(f["cost_display"])}</b><span class="lab">{e(f["feature"])} priced</span></div>')
    if result["drivers"]:
        facts.append(f'<div class="fact"><b>{e(result["drivers"][0]["drift_display"])}</b><span class="lab">over budget on {e(result["drivers"][0]["model"])}</span></div>')
    if "reconcile" in result:
        facts.append(f'<div class="fact"><b>{e(result["reconcile"]["unattributed_display"])}</b><span class="lab">of the bill not in the usage</span></div>')
    if facts:
        out.append(f'<div class="facts">{"".join(facts)}</div>')

    for f in result["features"]:
        out.append(f"<section><h2>{e(f['feature'])} {status(f.get('status'))}</h2>")
        if f.get("metric"):
            out.append(f'<p class="lab">Brief {e(f["brief"])} &middot; metric: {e(f["metric"])}</p>')
        if f["checks"]:
            out.append('<div class="key lab"><span><i></i>budget</span><span><i class="a"></i>actual</span><span><i class="o"></i>over budget</span></div><div class="feat">')
            for key in ("tokens_per_task", "price_per_token", "cost_per_task"):
                c = f["checks"].get(key)
                if c:
                    out.append(f'<div class="pvr"><span class="name">{LABEL[key]}</span>{status(c["status"])}{bars(c)}{figure_line(c)}</div>')
            out.append("</div>")
        if f.get("cost_per_success_display"):
            out.append(f"<p>{e(f['success_rate_display'])} of tasks succeeded, so cost per successful task is <b>{e(f['cost_per_success_display'])}</b>. No budget line covers it; it is shown, not marked.</p>")
        if f.get("models"):
            out.append('<h3>By model</h3><div class="scroll"><table><thead><tr><th>Model</th><th>Share of tokens</th><th class="num">Price per token</th><th class="num">Priced cost</th><th class="num">Over budget</th></tr></thead><tbody>')
            for m in f["models"]:
                width = max(0.0, min(100.0, m["share"] * 100))
                out.append(
                    f'<tr><td><code>{e(m["model"])}</code></td><td><span class="share"><i style="width:{width:.1f}%"></i></span>{e(m["share_display"])}</td>'
                    f'<td class="num">{e(m["price_per_token_display"])}</td><td class="num">{e(m["cost_display"])}</td><td class="num">{e(m["drift_display"])}</td></tr>'
                )
            out.append("</tbody></table></div>")
        if f["gaps"]:
            out.append('<ul class="notes">' + "".join(f'<li><span class="tag">Gap</span>{e(g)}</li>' for g in f["gaps"]) + "</ul>")
        out.append("</section>")

    notes = []
    if "reconcile" in result:
        r = result["reconcile"]
        notes.append(("Bill", f"{r['billed_display']} billed, {r['priced_display']} priced from usage, {r['unattributed_display']} not in the usage given."))
    notes += [("No brief", f"{u['feature']}: {u['cost_display']} priced, with no landing brief, so no budget to check.") for u in result["unbriefed"]]
    notes += [("Warning", w) for w in result["warnings"]]
    notes += [("Read", n) for n in result["notes"]]
    notes.append(("Prices", f"{p['file']}: {p['source']}, retrieved {p['retrieved']}, {p['currency']}."))
    out.append('<section><h2>Data notes</h2><ul class="notes">' + "".join(f'<li><span class="tag">{e(t)}</span>{e(x)}</li>' for t, x in notes) + "</ul></section>")

    out.append('<section><details><summary>Evidence ledger: every figure, its formula and sources</summary><div class="scroll"><table><thead><tr><th>ID</th><th class="num">Figure</th><th>Formula</th><th>Sources</th></tr></thead><tbody>')
    for row in result["ledger"]:
        out.append(f'<tr><td><code>{e(row["id"])}</code></td><td class="num">{e(row["display"])}</td><td>{e(row["formula"])}</td><td>{e("; ".join(row["sources"]))}</td></tr>')
    out.append("</tbody></table></div></details></section>")
    out.append(f"<footer>cost-budget-check {e(result['version'])}. The check shows where spend went against budget, not why. Figures computed in code; the page computes nothing but bar widths.</footer>")
    out.append("</main></body></html>")
    return "\n".join(out) + "\n"
