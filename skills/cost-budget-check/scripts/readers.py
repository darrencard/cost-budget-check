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

Standard library only. Runs on Python 3.11 or later.
"""

from __future__ import annotations

import csv
import datetime
import json
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
        return datetime.datetime.fromtimestamp(seconds, datetime.UTC).date()
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


def read_tasks(path: Path, feature_map: dict[str, str]) -> dict[str, tuple[int, str]]:
    """{feature: (tasks, what was counted)} from a CSV with feature, tasks and source columns."""
    rows = list(csv.DictReader(text_of(path).splitlines()))
    out: dict[str, tuple[int, str]] = {}
    for i, row in enumerate(rows, 2):
        where = f"{path.name} line {i}"
        lower = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        name, source = lower.get("feature", ""), lower.get("source", "")
        if not name or not source:
            raise InputError(f"{where}: each row needs feature, tasks and source (what was counted as a task, and where).")
        tasks = whole(lower.get("tasks"), "tasks", where)
        if tasks == 0:
            raise InputError(f"{where}: tasks is 0. A feature with no tasks has no tokens per task; leave it out.")
        name = feature_map.get(name, name)
        if name in out:
            raise InputError(f"{where}: {name} is counted twice. Keep one row per feature.")
        out[name] = (tasks, f"{source} ({path.name})")
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
