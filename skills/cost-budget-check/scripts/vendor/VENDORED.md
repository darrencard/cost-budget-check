# Vendored from the Product & Technology Leader Report

Copied unchanged from github.com/darrencard/product-engineering-update at commit
8b843de107d080ed88e248428972b23f996d12fd (v0.11.0). Do not edit these files here. To update, copy
them again from a newer commit and change the commit and the hashes below and in evals/test_check.py.

| File | Source path | sha256 |
|---|---|---|
| landing_brief.py | skills/landing-brief/scripts/landing_brief.py | 2d13573543c74ebe1bf001b97287287474a0ec298f34709a1bbfc643be051948 |
| from_ai_spend.py | skills/product-engineering-update/scripts/from_ai_spend.py | 4d29c095942f6613837ce5e04b986313faaea817e0db9cdd7a57becf40544536 |
| convert.py | skills/product-engineering-update/scripts/convert.py | f1d055c02e29c67690f3caac7b7eb3213afab20042ff78a8080ebf172b183a55 |
| collect.py | skills/product-engineering-update/scripts/collect.py | f58d3cd6db1fc7a5e73441618ed94460189aeb724be1c42934313d23d5bd93c4 |

landing_brief.py parses the brief, the one format the Landing Loop shares. from_ai_spend.py (with
convert.py and collect.py, which it imports) reads the Anthropic and OpenAI admin cost exports, used
here as the bill.

assets/leader-report-template.html is skills/product-engineering-update/assets/template.html from the same
commit, byte-identical (sha256 e5740431ab5269606709d352d3d253325df740830e8316f06478873e71d430d0). scripts/page.py
reads its style block (tokens and embedded Geist, Geist Mono and Instrument Sans, SIL Open Font License) at
render time, so the page is in the same brand family as the Leader Report with no network.

## From landing-loop

svgkit.py is landing-loop's tools/svgkit.py at commit 5d01756d08ab3eb92b457c3286729791df6bcf5f, byte-identical
(sha256 8526cf100159a9e5a8958bba4ceb0373a7edc265f481d63795d1731a5999d054), pinned in VENDORED.json beside this file
under `landing-loop`. scripts/page.py draws the page's pictures with it, in the Landing Loop's one visual family.
