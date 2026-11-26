#!/usr/bin/env python3
"""Read usage exports into one record shape, and read task counts and billed spend.

Three inputs are read as they stand:

  Provider usage CSV  one row per day, model and key or workspace, as a provider console or usage API
                      export gives it. Columns are matched by name (see ALIASES). A column naming the
                      feature (feature, workspace, api_key, project, tag) is required; --feature-map
                      renames its values to the feature names the briefs use.
  AI gateway logs     JSON Lines or a JSON array, one object per request, in the OpenAI-compatible
                      shape most gateways log (model, usage, metadata or tags). The feature comes from
                      metadata.feature, a "feature:NAME" tag or a top-level feature field. A task id
                      (metadata.task_id, task_id or trace_id) lets tasks be counted in code.
  Billed spend        run/ai_spend/finance.csv from the Product & Technology Leader Report's
                      from_ai_spend.py (line, period, plan, actual). Lines starting "Model API" are
                      the bill, used to reconcile the priced usage against what was invoiced.

Cache tokens: OpenAI-style exports count cached tokens inside prompt or input tokens
(prompt_tokens with cached_tokens, input_tokens with input_cached_tokens). Those are subtracted so
each token is priced once, at its own rate. Anthropic-style exports (input_tokens beside
cache_read_input_tokens) already count them apart. The rule used is printed for every file.

These functions read files and return records. They make no network calls.

Standard library only. Runs on Python 3.9 or later.
"""

from __future__ import annotations

import csv
import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_BYTES = 200_000_000
ALIASES = {
    "date": ("date", "day", "usage_date", "starting_at", "start_time", "bucket_start", "timestamp"),
    "model": ("model", "model_id", "model_name", "model_version"),
    "feature": ("feature", "workspace", "workspace_name", "api_key", "api_key_name", "project", "project_name", "tag"),
    "input": ("uncached_input_tokens", "input_tokens", "prompt_tokens", "input"),
    "output": ("output_tokens", "completion_tokens", "output"),
    "cache_read": ("cache_read_input_tokens", "cache_read_tokens", "input_cached_tokens", "cached_tokens", "cache_read"),
    "cache_write": ("cache_creation_input_tokens", "cache_write_tokens", "cache_creation_tokens", "cache_write"),
    "requests": ("requests", "num_model_requests", "request_count"),
    "cost": ("cost", "cost_usd", "amount_usd"),
}
# Input columns that count cached tokens inside them, with the cache column that names the subset.
INCLUSIVE = {("input_tokens", "input_cached_tokens"), ("prompt_tokens", "cached_tokens"), ("prompt_tokens", "input_cached_tokens")}


class InputError(ValueError):
    """An export that cannot be read safely. The message says which file and why."""


@dataclass
class Record:
    date: datetime.date | None
    feature: str
    model: str
    tokens: dict[str, int]
    requests: int
    task_id: str | None
    stated_cost: float | None
    file: str
    kind: str


@dataclass
class Read:
    records: list[Record] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def day(value: Any) -> datetime.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).date()  # noqa: UP017  (runs on 3.9)
    text = str(value).strip()
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        return None


def whole(value: Any, what: str, where: str) -> int:
    if value in (None, ""):
        return 0
    try:
        number = float(str(value).replace(",", ""))
    except ValueError:
        raise InputError(f"{where}: {what} is {value!r}, not a number.") from None
    if number < 0 or number != int(number):
        raise InputError(f"{where}: {what} is {value!r}. Token and request counts are whole numbers, 0 or more.")
    return int(number)


def money(value: Any, where: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        raise InputError(f"{where}: cost is {value!r}, not a number.") from None


def text_of(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_BYTES:
            raise InputError(f"{path.name} is over {MAX_BYTES // 1_000_000} MB. Split the export by month.")
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise InputError(f"cannot read {path} ({e}). Save the export as UTF-8.") from None


def column(header: list[str], key: str) -> str | None:
    lower = {h.strip().lower(): h for h in header}
    return next((lower[a] for a in ALIASES[key] if a in lower), None)


def split_cache(tokens: dict[str, int], inclusive: bool, where: str) -> dict[str, int]:
    if inclusive:
        if tokens["cache_read"] > tokens["input"]:
            raise InputError(f"{where}: cached tokens ({tokens['cache_read']}) exceed input tokens ({tokens['input']}), which count them.")
        tokens["input"] -= tokens["cache_read"]
    return tokens


def read_usage_csv(path: Path, feature_map: dict[str, str]) -> Read:
    rows = list(csv.DictReader(text_of(path).splitlines()))
    if not rows:
        raise InputError(f"{path.name} has no rows.")
    header = list(rows[0].keys())
    cols = {k: column(header, k) for k in ALIASES}
    missing = [k for k in ("model", "feature", "input", "output") if not cols[k]]
    if missing:
        raise InputError(f"{path.name}: no column for {', '.join(missing)}. Columns found: {', '.join(header)}.")
    inclusive = (cols["input"].lower(), (cols["cache_read"] or "").lower()) in INCLUSIVE
    out = Read()
    rule = "input counts cached tokens, so they were subtracted" if inclusive else "input and cache reads are counted apart"
    out.notes.append(f"{path.name}: {len(rows)} rows read as a provider usage CSV; {rule}.")
    for i, row in enumerate(rows, 2):
        where = f"{path.name} line {i}"
        raw = (row.get(cols["feature"]) or "").strip()
        tokens = {k: whole(row.get(cols[k]) if cols[k] else None, k, where) for k in ("input", "output", "cache_read", "cache_write")}
        out.records.append(
            Record(
                date=day(row.get(cols["date"])) if cols["date"] else None,
                feature=feature_map.get(raw, raw) or "(none)",
                model=(row.get(cols["model"]) or "").strip(),
                tokens=split_cache(tokens, inclusive, where),
                requests=whole(row.get(cols["requests"]) if cols["requests"] else None, "requests", where),
                task_id=None,
                stated_cost=money(row.get(cols["cost"]), where) if cols["cost"] else None,
                file=path.name,
                kind="provider usage CSV",
            )
        )
    return out


def gateway_objects(path: Path) -> list[dict[str, Any]]:
    text = text_of(path).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise InputError(f"{path.name} is not valid JSON ({e.msg}, line {e.lineno}).") from None
        return [d for d in data if isinstance(d, dict)]
    objects = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise InputError(f"{path.name} line {n} is not valid JSON ({e.msg}).") from None
        if isinstance(obj, dict):
            objects.append(obj)
    return objects


def tag_feature(tags: Any) -> str | None:
    if isinstance(tags, dict):
        return tags.get("feature")
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, str) and t.startswith("feature:"):
                return t.split(":", 1)[1]
    return None


def read_gateway(path: Path, feature_map: dict[str, str]) -> Read:
    out = Read()
    objects = gateway_objects(path)
    if not objects:
        raise InputError(f"{path.name} holds no request objects.")
    inclusive_count = 0
    for n, obj in enumerate(objects, 1):
        where = f"{path.name} request {n}"
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else obj
        raw = meta.get("feature") or tag_feature(obj.get("tags")) or tag_feature(obj.get("request_tags")) or obj.get("feature") or ""
        details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
        inclusive = "prompt_tokens" in usage and "input_tokens" not in usage
        inclusive_count += inclusive
        tokens = {
            "input": whole(usage.get("input_tokens", usage.get("prompt_tokens")), "input tokens", where),
            "output": whole(usage.get("output_tokens", usage.get("completion_tokens")), "output tokens", where),
            "cache_read": whole(usage.get("cache_read_input_tokens", details.get("cached_tokens")), "cache read tokens", where),
            "cache_write": whole(usage.get("cache_creation_input_tokens"), "cache write tokens", where),
        }
        task = meta.get("task_id") or obj.get("task_id") or meta.get("trace_id") or obj.get("trace_id")
        out.records.append(
            Record(
                date=day(obj.get("timestamp") or obj.get("created_at") or obj.get("startTime") or obj.get("created")),
                feature=feature_map.get(str(raw), str(raw)) or "(none)",
                model=str(obj.get("model") or "").strip(),
                tokens=split_cache(tokens, inclusive, where),
                requests=1,
                task_id=str(task) if task else None,
                stated_cost=money(obj.get("cost", obj.get("response_cost", obj.get("spend"))), where),
                file=path.name,
                kind="AI gateway log",
            )
        )
    rule = f"{inclusive_count} of {len(objects)} requests counted cached tokens inside prompt tokens, so they were subtracted"
    out.notes.append(f"{path.name}: {len(objects)} requests read as an AI gateway log; {rule}.")
    return out


def json_of(path: Path) -> Any:
    try:
        return json.loads(text_of(path))
    except json.JSONDecodeError as e:
        raise InputError(f"{path.name} is not valid JSON ({e.msg}, line {e.lineno}).") from None


def read_anthropic_usage(path: Path, feature_map: dict[str, str]) -> Read:
    """One page of the Anthropic Admin API usage report (GET /v1/organizations/usage_report/messages).

    Fetch it grouped by model and by api_key_id or workspace_id, so each row names a model and a key or
    workspace; --feature-map renames those ids to features. Cache creation is split into five-minute
    and one-hour writes, which can bill at different rates.
    """
    data = json_of(path)
    buckets = data.get("data") if isinstance(data, dict) else None
    if not isinstance(buckets, list):
        raise InputError(f"{path.name} has no data list. Save the usage_report/messages response as it stands.")
    out = Read()
    ungrouped = 0
    for b, bucket in enumerate(buckets, 1):
        when = day(bucket.get("starting_at"))
        for n, r in enumerate(bucket.get("results") or [], 1):
            where = f"{path.name} bucket {b} result {n}"
            raw = r.get("workspace_id") or r.get("api_key_id") or ""
            ungrouped += not raw
            if not r.get("model"):
                raise InputError(f"{where}: no model. Fetch the report with group_by[]=model so each row can be priced.")
            creation = r.get("cache_creation") if isinstance(r.get("cache_creation"), dict) else {}
            tokens = {
                "input": whole(r.get("uncached_input_tokens"), "uncached input tokens", where),
                "output": whole(r.get("output_tokens"), "output tokens", where),
                "cache_read": whole(r.get("cache_read_input_tokens"), "cache read tokens", where),
                "cache_write": whole(creation.get("ephemeral_5m_input_tokens"), "five-minute cache writes", where),
                "cache_write_1h": whole(creation.get("ephemeral_1h_input_tokens"), "one-hour cache writes", where),
            }
            out.records.append(Record(when, feature_map.get(raw, raw) or "(none)", str(r["model"]), tokens, 0, None, None, path.name, "Anthropic usage report"))
    out.notes.append(f"{path.name}: {len(out.records)} rows read as an Anthropic usage report; input, cache reads and both cache writes are counted apart.")
    if ungrouped:
        out.notes.append(f"{path.name}: {ungrouped} rows name no workspace or key, so they fall under (none). Group the report by api_key_id or workspace_id.")
    return out


def groups(data: Any) -> list[dict[str, Any]]:
    """Every object in a response that carries token metrics, wherever it sits."""
    if isinstance(data, dict):
        if "input_tokens" in data or "inputTokens" in data:
            return [data]
        return [g for v in data.values() for g in groups(v)]
    if isinstance(data, list):
        return [g for v in data for g in groups(v)]
    return []


def read_vercel_gateway(path: Path, feature: str) -> Read:
    """A Vercel AI Gateway usage response grouped by model, for one feature (one project).

    Save the response of the gateway's usage query (the Vercel connector's get_ai_gateway_usage, with
    groupBy aiModel and metrics cost, count, input_tokens, output_tokens) as JSON. Its input tokens
    include any cached ones, with no split, so cached input is priced at the input rate here and the
    gateway's own billed cost is kept beside it to compare.
    """
    data = json_of(path)
    found = [g for g in groups(data) if g.get("aiModel") or g.get("model") or g.get("key")]
    if not found:
        raise InputError(f"{path.name} has no rows with a model and input_tokens. Query the usage grouped by aiModel with the token metrics.")
    when = None
    if isinstance(data, dict):
        when = day(data.get("end") or data.get("until"))
    out = Read()
    for n, g in enumerate(found, 1):
        where = f"{path.name} group {n}"
        model = str(g.get("aiModel") or g.get("model") or g.get("key"))
        tokens = {
            "input": whole(g.get("input_tokens", g.get("inputTokens")), "input tokens", where),
            "output": whole(g.get("output_tokens", g.get("outputTokens")), "output tokens", where),
            "cache_read": 0,
            "cache_write": 0,
        }
        out.records.append(Record(when, feature, model, tokens, whole(g.get("count"), "requests", where), None, money(g.get("cost"), where), path.name, "Vercel AI Gateway usage"))
    out.notes.append(f"{path.name}: {len(found)} models read as Vercel AI Gateway usage for {feature}; the gateway gives no cache split, so cached input is priced at the input rate.")
    return out


DATED = re.compile(r"(\d{4}-\d{2}-\d{2})")


def run_objects(paths: list[Path]) -> list[tuple[Path, str, Any]]:
    """(file, key, record): a file holding one record, or a JSON object whose values are records (key is their name)."""
    out = []
    for path in paths:
        data = json_of(path)
        if isinstance(data, dict) and "usage" not in data and data and all(isinstance(v, dict) and "usage" in v for v in data.values()):
            out += [(path, str(k), v) for k, v in data.items()]
        else:
            out.append((path, "", data))
    return out


def read_run_records(feature: str, paths: list[Path], cache_ttl: str = "5m") -> Read:
    """Agent run records, one JSON file per task, each with a model and a usage block.

    This is the shape Claude Code writes with --output-format json, and the shape the Leader Report's
    eval runs keep: usage.input_tokens, output_tokens, cache_read_input_tokens and
    cache_creation_input_tokens counted apart, and the run's own cost_usd or total_cost_usd. Each file is
    one task, or, when a file is an object whose every value has a usage block, each value is one task.
    Its date is the first YYYY-MM-DD in its path, if any. These records do not split cache writes by
    duration, so cache_ttl says which they are: "5m" (the default) or "1h". Claude Code writes the
    one-hour cache; the stated cost beside the priced cost shows which fits.
    """
    out = Read()
    skipped = 0
    for path, key, data in run_objects(paths):
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict) or not data.get("model"):
            skipped += 1
            continue
        where = f"{path.name}#{key}" if key else path.name
        tokens = {
            "input": whole(usage.get("input_tokens"), "input tokens", where),
            "output": whole(usage.get("output_tokens"), "output tokens", where),
            "cache_read": whole(usage.get("cache_read_input_tokens"), "cache read tokens", where),
            "cache_write": 0,
            "cache_write_1h": 0,
        }
        tokens["cache_write_1h" if cache_ttl == "1h" else "cache_write"] = whole(usage.get("cache_creation_input_tokens"), "cache write tokens", where)
        stated = usage.get("cost_usd", data.get("total_cost_usd"))
        dated = DATED.search(str(path))
        task = f"{path}#{key}" if key else str(path)
        out.records.append(Record(day(dated.group(1)) if dated else None, feature, str(data["model"]), tokens, whole(usage.get("num_turns"), "turns", where), task, money(stated, where), path.name, "agent run records"))
    if not out.records:
        raise InputError(f"no run record for {feature} has a model and a usage block ({len(paths)} files looked at).")
    ttl = "one-hour" if cache_ttl == "1h" else "five-minute"
    skip = f"; {skipped} file{'s' if skipped != 1 else ''} with no usage block skipped" if skipped else ""
    out.notes.append(f"{feature}: {len(out.records)} run records read, one task each, cache writes priced at the {ttl} rate{skip}.")
    return out


def read_tasks(path: Path, feature_map: dict[str, str]) -> dict[tuple[str, str], tuple[int, str, int | None]]:
    """{(feature, window): (tasks, what was counted, tasks that succeeded)} from a CSV with feature, tasks and source.

    Optional start and end columns (YYYY-MM-DD) say which window a count covers, so one file can hold
    this window and the prior one. A row without them has window "" and is taken to cover the window
    being checked. An optional succeeded column (tasks that met the feature's own success test, from
    its evals or outcomes) gives cost per successful task.
    """
    rows = list(csv.DictReader(text_of(path).splitlines()))
    out: dict[tuple[str, str], tuple[int, str, int | None]] = {}
    for i, row in enumerate(rows, 2):
        where = f"{path.name} line {i}"
        lower = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        name, source = lower.get("feature", ""), lower.get("source", "")
        if not name or not source:
            raise InputError(f"{where}: each row needs feature, tasks and source (what was counted as a task, and where).")
        tasks = whole(lower.get("tasks"), "tasks", where)
        if tasks == 0:
            raise InputError(f"{where}: tasks is 0. A feature with no tasks has no tokens per task; leave it out.")
        succeeded = whole(lower["succeeded"], "succeeded", where) if lower.get("succeeded") else None
        if succeeded is not None and succeeded > tasks:
            raise InputError(f"{where}: succeeded ({succeeded}) is more than tasks ({tasks}).")
        start, end = lower.get("start", ""), lower.get("end", "")
        if bool(start) != bool(end) or (start and (day(start) is None or day(end) is None)):
            raise InputError(f"{where}: start and end must both be YYYY-MM-DD, or both be empty.")
        window = f"{start}..{end}" if start else ""
        name = feature_map.get(name, name)
        if (name, window) in out:
            raise InputError(f"{where}: {name} is counted twice{' for ' + window if window else ''}. Keep one row per feature and window.")
        out[(name, window)] = (tasks, f"{source} ({path.name}{', ' + window if window else ''})", succeeded)
    return out


def read_finance(path: Path, period: str | None) -> tuple[float, list[str]]:
    """The billed model API spend, summed over lines starting "Model API", and the lines used."""
    rows = list(csv.DictReader(text_of(path).splitlines()))
    lines = [r for r in rows if (r.get("line") or "").startswith("Model API")]
    periods = sorted({r.get("period") or "" for r in lines})
    if period:
        lines = [r for r in lines if r.get("period") == period]
    elif len(periods) > 1:
        raise InputError(f"{path.name} covers {len(periods)} periods ({', '.join(periods)}). Pass --finance-period to pick one.")
    if not lines:
        raise InputError(f"{path.name} has no 'Model API' lines{' for ' + period if period else ''}. Run from_ai_spend.py first.")
    total = 0.0
    for r in lines:
        value = money(r.get("actual"), f"{path.name} {r.get('line')}")
        if value is None:
            raise InputError(f"{path.name}: {r.get('line')} has no actual.")
        total += value
    return total, [f"{r['line']} {r.get('period') or ''}".strip() for r in lines]
