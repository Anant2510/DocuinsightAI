"""What a case costs, and the switches that stop it costing more.

Every model call any agent makes is counted where it is made (the harness), against the case it was made for: which agent,
which step, which document or documents, tokens in and out, and money when a price is set. Nothing is estimated: a call
the provider reports no usage for counts as a call with no tokens.

A case keeps exact running sums (in all, by document, by agent, by kind of work) and the last calls as a log.

Three things stop spend, all checked before a call is made, never after:

    a limit     tokens or money for one case, tokens for one document (settings below)
    a person    "stop model use" on a case, or "stop the assessment"
    a pause     the whole workspace runs without the model until someone resumes it

A call that is refused is not an error: the agent that asked falls back to the use case's patterns, as it does when no
model is connected, and its run says why. Rules never needed the model, so a case stopped this way still gets its
recommendation. A call already sent when the stop arrives finishes and is counted; the next one is not made.

Settings come from the environment and can be changed per workspace from the portal (kept in the workspace, audited):

    DOCUINSIGHTS_PRICE_INPUT, DOCUINSIGHTS_PRICE_OUTPUT   money per million tokens in and out (your contracted rate)
    DOCUINSIGHTS_PRICE_CURRENCY                           the currency those are in (default USD)
    DOCUINSIGHTS_PRICES                                   optional JSON: {"<model name>": {"input": 3, "output": 15}}
    DOCUINSIGHTS_CASE_TOKEN_LIMIT                         tokens one case may use in all (0: no limit)
    DOCUINSIGHTS_CASE_COST_LIMIT                          money one case may cost in all (0: no limit)
    DOCUINSIGHTS_DOC_TOKEN_LIMIT                          tokens one document may use (0: no limit)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .throttle import Throttled

LOG = 300   # the calls a case keeps as a log; the sums are exact however many were made
# Published list prices, US dollars for a million tokens in and out (platform.claude.com/docs/en/about-claude/pricing, read on the date below).
# They make cost visible before anyone has set a price, and are always shown as an estimate at list price: a contracted rate, a regional
# multiplier or a later price change is the installation's to state (the settings above), and what it states is used instead.
LIST_PRICES_AS_OF = "2026-11-26"
LIST_PRICES = {"claude-fable-5-2": (8.0, 40.0), "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
               "claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-sonnet-4-6": (3.0, 15.0), "claude-sonnet-4-5": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0)}


def list_price(model: str) -> tuple[float, float] | None:
    """The published price of a model by its name (the longest name that the given one contains), or None for one this table does not know."""
    name = str(model or "").lower().replace("_", "-").replace(".", "-")
    hits = [k for k in LIST_PRICES if k in name]
    return LIST_PRICES[max(hits, key=len)] if hits else None
ACTIVITY = {"assistant": "questions", "correspondence": "drafts", "counterfactual": "what_if"}   # every other agent works on an assessment
ACTIVITY_NAMES = {"assessment": "Assessments", "questions": "Questions asked", "drafts": "Drafts", "what_if": "What-if runs"}
NUMBERS = ("price_input", "price_output", "case_token_limit", "case_cost_limit", "doc_token_limit")


def _number(value: Any, name: str = "") -> float:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        raise ValueError(f"{name or 'the value'} must be a number") from None
    if n != n or n < 0 or n > 1e12:
        raise ValueError(f"{name or 'the value'} must be zero or more")
    return n


def defaults(env: dict[str, str] | None = None) -> dict[str, Any]:
    """The installation's settings (the environment). A workspace's own settings are laid over these."""
    env = env if env is not None else dict(os.environ)

    def num(key: str) -> float:
        try:
            return max(0.0, float(env.get(key) or 0))
        except ValueError:
            return 0.0

    by_model: dict[str, dict[str, float]] = {}
    try:
        for name, row in (json.loads(env.get("DOCUINSIGHTS_PRICES") or "{}") or {}).items():
            if isinstance(row, dict):
                by_model[str(name)] = {"input": max(0.0, float(row.get("input") or 0)), "output": max(0.0, float(row.get("output") or 0))}
    except (ValueError, TypeError, AttributeError):
        by_model = {}
    return {"price_input": num("DOCUINSIGHTS_PRICE_INPUT"), "price_output": num("DOCUINSIGHTS_PRICE_OUTPUT"), "currency": (env.get("DOCUINSIGHTS_PRICE_CURRENCY") or "USD").strip()[:8] or "USD",
            "prices_by_model": by_model, "case_token_limit": int(num("DOCUINSIGHTS_CASE_TOKEN_LIMIT")), "case_cost_limit": num("DOCUINSIGHTS_CASE_COST_LIMIT"),
            "doc_token_limit": int(num("DOCUINSIGHTS_DOC_TOKEN_LIMIT")), "paused": None,
            "list_prices": (env.get("DOCUINSIGHTS_LIST_PRICES") or "1").strip().lower() not in ("0", "false", "no", "off")}


class Settings:
    """One workspace's prices, limits and pause: the installation's, with what the workspace changed laid over them."""

    def __init__(self, path: Path | None = None):
        self.path = path

    def own(self) -> dict[str, Any]:
        if self.path is None or not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def read(self) -> dict[str, Any]:
        base, own = defaults(), self.own()
        out = {**base, **{k: own[k] for k in (*NUMBERS, "currency") if k in own}}
        out["paused"] = own.get("paused") or None            # {"by", "at", "note"} while the workspace runs without the model
        out["changed"] = sorted(k for k in (*NUMBERS, "currency") if k in own)
        out["priced"] = bool(out["price_input"] or out["price_output"] or out["prices_by_model"])     # the installation or the workspace has stated a price
        out["estimates"] = bool(out["list_prices"] and not out["priced"] and out["currency"] == "USD")    # none stated: known models are costed at their published list price
        out["list_prices_as_of"] = LIST_PRICES_AS_OF
        return out

    def change(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Lay new values over the installation's. A value given as null goes back to the installation's own."""
        if not isinstance(payload, dict):
            raise ValueError("give the settings as an object")
        own = self.own()
        for key in NUMBERS:
            if key in payload:
                if payload[key] in (None, ""):
                    own.pop(key, None)
                else:
                    n = _number(payload[key], key.replace("_", " "))
                    own[key] = int(n) if key.endswith("token_limit") else round(n, 6)
        if "currency" in payload:
            cur = str(payload["currency"] or "").strip().upper()[:8]
            if cur and not cur.isalpha():
                raise ValueError("the currency is a short code such as USD, EUR or INR")
            own.pop("currency", None) if not cur else own.__setitem__("currency", cur)
        if "paused" in payload:
            own.pop("paused", None) if not payload["paused"] else own.__setitem__("paused", payload["paused"])
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(own, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        return self.read()


def price_of(model: str, settings: dict[str, Any]) -> tuple[float, float, str | None]:
    """(price in, price out, where it comes from) for a million tokens of this model: "set" when the installation or the workspace stated
    it, "list" when it is the published list price (US dollars; used only while nothing is stated), None when there is no price at all."""
    row = (settings.get("prices_by_model") or {}).get(model)
    if row and (row.get("input") or row.get("output")):
        return float(row.get("input") or 0), float(row.get("output") or 0), "set"
    if settings.get("price_input") or settings.get("price_output"):
        return float(settings.get("price_input") or 0), float(settings.get("price_output") or 0), "set"
    listed = list_price(model) if settings.get("list_prices", True) and (settings.get("currency") or "USD") == "USD" and not settings.get("prices_by_model") else None
    return (*listed, "list") if listed else (0.0, 0.0, None)


def cost_of(call: dict[str, Any], settings: dict[str, Any]) -> float | None:
    """Money for one call at the price in force, or None when there is no price for it (it is then counted in tokens only)."""
    pin, pout, basis = price_of(str(call.get("model") or ""), settings)
    if basis is None:
        return None
    return round((int(call.get("input_tokens") or 0) * pin + int(call.get("output_tokens") or 0) * pout) / 1_000_000, 6)


SUMS = ("calls", "input_tokens", "output_tokens", "cost", "unpriced", "listed", "failed", "ms")


def _blank() -> dict[str, Any]:
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0, "unpriced": 0, "listed": 0, "failed": 0, "ms": 0}


def _add(row: dict[str, Any], tin: int, tout: int, cost: float | None, failed: bool, calls: float = 1, *, listed: bool = False, ms: float = 0) -> None:
    row["calls"] = round(row.get("calls", 0) + calls, 4)
    row["input_tokens"] = row.get("input_tokens", 0) + tin
    row["output_tokens"] = row.get("output_tokens", 0) + tout
    row["ms"] = round(row.get("ms", 0) + ms * calls, 1)
    if cost is None:
        row["unpriced"] = round(row.get("unpriced", 0) + calls, 4)
    else:
        row["cost"] = round(row.get("cost", 0.0) + cost, 6)
        if listed:   # costed at the published list price, not at a price the installation stated
            row["listed"] = round(row.get("listed", 0) + calls, 4)
    if failed:
        row["failed"] = round(row.get("failed", 0) + calls, 4)


def basis_of(row: dict[str, Any]) -> str:
    """What a sum of money rests on: "none" (no call was priced), "list" (the published list price: an estimate), "set" (the price the
    installation stated) or "mixed"."""
    priced = (row.get("calls") or 0) - (row.get("unpriced") or 0)
    if priced <= 0:
        return "none"
    listed = row.get("listed") or 0
    return "list" if listed >= priced else "set" if not listed else "mixed"


def book(case: dict[str, Any]) -> dict[str, Any]:
    """The case's own account, made the first time it is needed."""
    b = case.setdefault("spend", {})
    b.setdefault("totals", _blank())
    for part in ("documents", "agents", "activities", "days"):
        b.setdefault(part, {})
    b.setdefault("log", [])
    return b


def record(case: dict[str, Any], agent_id: str, calls: list[dict[str, Any]], docs: list[str] | None, settings: dict[str, Any]) -> None:
    """Count the calls one agent just made for this case. A call about several documents (one request naming a batch) is shared out
    evenly between them in the by-document sums, and counted once everywhere else."""
    if not calls:
        return
    b = book(case)
    docs = [d for d in dict.fromkeys(docs or []) if d]
    activity = ACTIVITY.get(agent_id, "assessment")
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for c in calls:
        tin, tout = int(c.get("input_tokens") or 0), int(c.get("output_tokens") or 0)
        cost, failed, ms = cost_of(c, settings), bool(c.get("error")), float(c.get("ms") or 0)
        listed = cost is not None and price_of(str(c.get("model") or ""), settings)[2] == "list"
        for row in (b["totals"], b["agents"].setdefault(agent_id, _blank()), b["activities"].setdefault(activity, _blank()), b["days"].setdefault(at[:10], _blank())):
            _add(row, tin, tout, cost, failed, listed=listed, ms=ms)
        n = len(docs)
        for i, d in enumerate(docs):   # whole tokens: what does not divide goes to the first document
            share_in, share_out = tin // n + (tin % n if i == 0 else 0), tout // n + (tout % n if i == 0 else 0)
            row = b["documents"].setdefault(d, _blank())
            _add(row, share_in, share_out, None if cost is None else round(cost * (share_in + share_out) / max(1, tin + tout), 6) if tin + tout else 0.0, failed, calls=round(1 / n, 4), listed=listed, ms=ms)
            row["own" if n == 1 else "shared"] = row.get("own" if n == 1 else "shared", 0) + 1   # requests about this document alone, and batch requests it was one of
        b["log"].append({"at": at, "agent": agent_id, "step": c.get("step") or "", "model": c.get("model") or "", "docs": docs,
                         "input_tokens": tin, "output_tokens": tout, "cost": cost, "ms": c.get("ms") or 0, **({"error": str(c["error"])[:120]} if c.get("error") else {})})
    del b["log"][:-LOG]
    b["currency"] = settings.get("currency") or "USD"
    for day in sorted(b["days"])[:-90]:   # a case that lives longer than three months keeps its sums; the oldest days fold away
        b["days"].pop(day)


def totals(case: dict[str, Any]) -> dict[str, Any]:
    t = {**_blank(), **((case.get("spend") or {}).get("totals") or {})}
    t["tokens"] = t["input_tokens"] + t["output_tokens"]
    t["currency"] = (case.get("spend") or {}).get("currency") or "USD"
    t["priced"] = t["calls"] > t["unpriced"] if t["calls"] else None    # None: nothing was spent, so there is nothing to price
    t["basis"] = basis_of(t)
    return t


def since(case: dict[str, Any], before: dict[str, Any] | None) -> dict[str, Any]:
    """What was spent since `before` (an earlier totals()): the spend of one assessment."""
    now, before = totals(case), before or _blank()
    out = {k: round(now[k] - (before.get(k) or 0), 6) for k in SUMS}
    for k in ("calls", "input_tokens", "output_tokens"):
        out[k] = int(out[k])
    out.update(tokens=out["input_tokens"] + out["output_tokens"], currency=now["currency"], priced=(out["calls"] > out["unpriced"]) if out["calls"] else None)
    out["basis"] = basis_of(out)
    return out


def switch(case: dict[str, Any]) -> dict[str, Any] | None:
    """{"by", "at", "note"} while a person has model use switched off for this case."""
    return (case.get("spend") or {}).get("model_off") or None


def check(case: dict[str, Any], settings: dict[str, Any], docs: list[str] | None = None, size: int = 0, *, names: dict[str, str] | None = None) -> None:
    """Before a model call for this case: raises Throttled, with the reason in plain words, when the call may not be made.
    `size` is about how many tokens the request itself is: a call that would take the case or a document past its limit is held back
    before it is paid for, not after."""
    paused = settings.get("paused")
    if paused:
        raise Throttled(f"model use is paused for this workspace (by {paused.get('by') or 'an administrator'})")
    off = switch(case)
    if off:
        raise Throttled(f"model use was stopped for this case by {off.get('by') or 'a caseworker'}")
    t = totals(case)
    limit = int(settings.get("case_token_limit") or 0)
    if limit and t["tokens"] >= limit:
        raise Throttled(f"this case has used {t['tokens']:,} tokens: its limit of {limit:,} is reached")
    if limit and t["tokens"] + size > limit:
        raise Throttled(f"this case has used {t['tokens']:,} of its {limit:,} tokens, and this request is about {size:,} more")
    money = float(settings.get("case_cost_limit") or 0)
    if money and t["cost"] >= money:
        raise Throttled(f"this case has cost {t['currency']} {t['cost']:,.2f}: its limit of {money:,.2f} is reached")
    per_doc = int(settings.get("doc_token_limit") or 0)
    if per_doc:
        book_ = (case.get("spend") or {}).get("documents") or {}
        for d in docs or []:
            used = (book_.get(d) or {}).get("input_tokens", 0) + (book_.get(d) or {}).get("output_tokens", 0)
            if used >= per_doc:
                raise Throttled(f"{(names or {}).get(d) or d} has used {used:,} tokens: the limit of {per_doc:,} for one document is reached")
            if used + size // max(1, len(docs or [])) > per_doc:
                raise Throttled(f"{(names or {}).get(d) or d} has used {used:,} of the {per_doc:,} tokens one document may use, and this request is about {size // max(1, len(docs or [])):,} more")


def limit_state(case: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Where the case stands against its limits, for the screen: nothing here stops anything (check() does)."""
    t = totals(case)
    tokens, money, per_doc = int(settings.get("case_token_limit") or 0), float(settings.get("case_cost_limit") or 0), int(settings.get("doc_token_limit") or 0)
    reached: list[str] = []
    if tokens and t["tokens"] >= tokens:
        reached.append("the case's token limit")
    if money and t["cost"] >= money:
        reached.append("the case's cost limit")
    docs = (case.get("spend") or {}).get("documents") or {}
    over = [d for d, r in docs.items() if per_doc and r.get("input_tokens", 0) + r.get("output_tokens", 0) >= per_doc]
    return {"case_token_limit": tokens, "case_cost_limit": money, "doc_token_limit": per_doc, "reached": reached, "documents_at_limit": over,
            "share": round(max(t["tokens"] / tokens if tokens else 0.0, t["cost"] / money if money else 0.0), 4)}


def summary(case: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """The case's spend as a screen or another system reads it."""
    b = case.get("spend") or {}
    names = {d["id"]: d.get("name") or d["id"] for d in case.get("documents") or []}

    def rows(part: str, name_of: Any) -> list[dict[str, Any]]:
        out = [{"id": k, "name": name_of(k), **{**_blank(), **v}, "tokens": v.get("input_tokens", 0) + v.get("output_tokens", 0)} for k, v in (b.get(part) or {}).items()]
        return sorted(out, key=lambda r: (-r["tokens"], -r["calls"], r["name"]))

    out = {"totals": totals(case), "documents": rows("documents", lambda k: names.get(k, k)), "agents": rows("agents", lambda k: k),
           "activities": rows("activities", lambda k: ACTIVITY_NAMES.get(k, k)), "log": list(reversed(b.get("log") or []))[:60], "model_off": switch(case)}
    for row in out["log"]:
        row["doc_names"] = [names.get(d, d) for d in row.get("docs") or []]
    if settings is not None:
        out["limits"] = limit_state(case, settings)
        out["paused"] = settings.get("paused")
    return out


def workspace(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The workspace's spend from its cases' own sums (each row: a case's reference, use case and totals)."""
    total = _blank()
    by_profile: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = r.get("spend") or {}
        p = by_profile.setdefault(r.get("profile") or "", {**_blank(), "cases": 0})
        for k in SUMS:
            total[k] = round(total[k] + (t.get(k) or 0), 6)
            p[k] = round(p[k] + (t.get(k) or 0), 6)
        p["cases"] += 1
    spent = [r for r in rows if (r.get("spend") or {}).get("calls")]
    top = sorted(spent, key=lambda r: (-(r["spend"].get("input_tokens", 0) + r["spend"].get("output_tokens", 0)), r.get("reference") or ""))[:10]
    total["tokens"] = int(total["input_tokens"] + total["output_tokens"])
    total["basis"] = basis_of(total)
    return {"totals": total, "cases": len(rows), "cases_with_spend": len(spent),
            "average_tokens": round(total["tokens"] / len(spent)) if spent else 0, "average_cost": round(total["cost"] / len(spent), 4) if spent else 0.0,
            "by_profile": [{"profile": k, **v, "tokens": int(v["input_tokens"] + v["output_tokens"]), "basis": basis_of(v)} for k, v in sorted(by_profile.items(), key=lambda kv: -(kv[1]["input_tokens"] + kv[1]["output_tokens"]))],
            "top": [{"reference": r.get("reference"), "profile": r.get("profile"), "tokens": int(r["spend"].get("input_tokens", 0) + r["spend"].get("output_tokens", 0)),
                     "calls": r["spend"].get("calls", 0), "cost": r["spend"].get("cost", 0.0), "unpriced": r["spend"].get("unpriced", 0), "listed": r["spend"].get("listed", 0),
                     "model_off": bool(r.get("model_off"))} for r in top]}


def observe(cases: list[dict[str, Any]], settings: dict[str, Any], *, days: int = 14, today: str | None = None) -> dict[str, Any]:
    """The workspace seen through what its agents did and what that cost: the model's use (calls, tokens, money, time, failures, calls held
    back) by day, by agent, by case and by document, the agents' runs under the harness, and the latest calls. Counted from the case files:
    nothing here is sampled or estimated except money at a list price, which is marked as such."""
    total, by_agent, by_day = _blank(), {}, {}
    rows, docs, calls, harness = [], [], [], {}
    held = {"calls": 0, "model_stops": 0, "assessments_stopped": 0, "reasons": {}}
    for c in cases:
        b = c.get("spend") or {}
        t = {**_blank(), **(b.get("totals") or {})}
        for k in SUMS:
            total[k] = round(total[k] + (t.get(k) or 0), 6)
        for part, into in (("agents", by_agent), ("days", by_day)):
            for key, row in (b.get(part) or {}).items():
                agg = into.setdefault(key, _blank())
                for k in SUMS:
                    agg[k] = round(agg[k] + (row.get(k) or 0), 6)
        names = {d["id"]: d.get("name") or d["id"] for d in c.get("documents") or []}
        if t["calls"]:
            n_docs = len([d for d in c.get("documents") or [] if not d.get("removed")])
            rows.append({"reference": c.get("reference"), "profile": c.get("profile"), "documents": n_docs, **{k: t[k] for k in SUMS}, "tokens": t["input_tokens"] + t["output_tokens"],
                         "basis": basis_of(t), "per_document": round((t["input_tokens"] + t["output_tokens"]) / max(1, n_docs)), "model_off": bool(b.get("model_off")),
                         "last": (b.get("log") or [{}])[-1].get("at")})
        for d, row in (b.get("documents") or {}).items():
            docs.append({"reference": c.get("reference"), "id": d, "name": names.get(d, d), "tokens": row.get("input_tokens", 0) + row.get("output_tokens", 0), "calls": row.get("calls", 0),
                         "cost": row.get("cost", 0.0), "basis": basis_of(row)})
        for entry in (b.get("log") or [])[-40:]:
            calls.append({**entry, "reference": c.get("reference"), "doc_names": [names.get(d, d) for d in entry.get("docs") or []]})
        for e in c.get("events") or []:
            if e.get("kind") == "model.stopped":
                held["model_stops"] += 1
            elif e.get("kind") == "assessment.stopped":
                held["assessments_stopped"] += 1
        for r in ((c.get("assessment") or {}).get("runs") or []):   # the agents' runs of the case's latest assessment, as the harness recorded them
            h = harness.setdefault(r.get("agent") or "", {"runs": 0, "kept": 0, "ms": 0.0, "model_calls": 0, "held": 0, "fell_back": 0, "failed": 0})
            h["runs"] += 1
            h["kept"] += 1 if (r.get("contract") or {}).get("kept") else 0
            h["ms"] += float(r.get("duration_ms") or 0)
            h["model_calls"] += int(r.get("model_calls") or 0)
            shed = int((r.get("throttle") or {}).get("shed") or 0)
            h["held"] += shed
            h["failed"] += 1 if r.get("status") == "failed" else 0
            h["fell_back"] += 1 if r.get("status") not in ("ok", "failed", None) else 0   # it finished, on the use case's patterns where it would have used the model
            held["calls"] += shed
            for why in (r.get("throttle") or {}).get("why") or []:
                key = "a person's stop" if "stopped" in why else "a pause" if "paused" in why else "a limit" if ("limit" in why or "may use" in why or "tokens" in why) else "the rate limit or an agent's budget"
                held["reasons"][key] = held["reasons"].get(key, 0) + 1
    today = today or datetime.now(timezone.utc).date().isoformat()
    from datetime import date, timedelta
    end = date.fromisoformat(today)
    series = []
    for n in range(days - 1, -1, -1):
        day = (end - timedelta(days=n)).isoformat()
        row = by_day.get(day) or _blank()
        series.append({"day": day, "calls": row["calls"], "tokens": row["input_tokens"] + row["output_tokens"], "cost": row["cost"], "basis": basis_of(row)})
    total["tokens"] = int(total["input_tokens"] + total["output_tokens"])
    total["basis"] = basis_of(total)
    total["average_ms"] = round(total["ms"] / total["calls"]) if total["calls"] else 0
    rows.sort(key=lambda r: (-r["tokens"], r["reference"] or ""))
    docs.sort(key=lambda r: (-r["tokens"], r["reference"] or "", r["name"]))
    calls.sort(key=lambda r: r.get("at") or "", reverse=True)
    return {"settings": {k: v for k, v in settings.items() if k != "prices_by_model"}, "totals": total, "cases": len(cases), "cases_with_spend": len(rows),
            "average_tokens": round(total["tokens"] / len(rows)) if rows else 0, "average_cost": round(total["cost"] / len(rows), 6) if rows else 0.0,
            "by_day": series, "by_agent": sorted(({"id": k, **v, "tokens": v["input_tokens"] + v["output_tokens"], "basis": basis_of(v), "average_ms": round(v["ms"] / v["calls"]) if v["calls"] else 0}
                                                  for k, v in by_agent.items()), key=lambda r: -r["tokens"]),
            "by_case": rows[:200], "by_document": docs[:15], "calls": calls[:40], "held": held,
            "harness": [{"agent": k, "runs": v["runs"], "kept": v["kept"], "average_ms": round(v["ms"] / v["runs"], 1) if v["runs"] else 0, "model_calls": v["model_calls"], "held": v["held"], "fell_back": v["fell_back"], "failed": v["failed"]}
                        for k, v in harness.items()]}


__all__ = ["Settings", "defaults", "record", "check", "summary", "totals", "since", "switch", "limit_state", "workspace", "observe", "cost_of", "price_of", "list_price", "basis_of", "book", "ACTIVITY_NAMES", "LIST_PRICES", "LIST_PRICES_AS_OF"]
