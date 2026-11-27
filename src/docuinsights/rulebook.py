"""A workspace's own rules, laid over the rules a use case ships with.

A use case ships with rules that are plausible and are nobody's policy. A business makes them its own here, without
code and without a restart: change a limit, switch a rule off, add a rule, add a document requirement. A rule is a
choice of kind, fields and limits (profiles.RULE_TYPES): every kind is a fixed calculation, so a rule added on the
portal runs exactly like one that shipped, and can be tested against a case before it is saved.

What is kept, per workspace and use case (`<data>/<tenant>/rules/<use case>.json`):

    version   a number that goes up by one with every change
    rules     the rules changed or added here, each whole, with the workbook version it was last changed at
    evidence  the document requirements added here
    off       what is switched off, shipped or added: {"rules": [...], "evidence": [...], "consistency": [...]}
    history   every change: who, when, what it was before and after, and why

Nothing is ever edited in place in the shipped profile: taking a rule back to how it shipped is one more change.

Every assessment records the workbook version it ran under, and every rule finding carries the rule as it stood (its
version and its limits), so an old case shows the rule that was in force when it was assessed, not today's.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .profiles import RULE_TYPES, Profile, ProfileError

GROUPS = ("rules", "evidence", "consistency")
COLUMNS = ["id", "title", "kind", "field_1", "field_2", "limit_or_values", "tolerance_pct", "applies_when_field", "applies_when_value", "enabled", "note"]
KINDS = {"date_order": "the first date is not after the second", "date_interval": "the second date is within a number of days of the first",
         "amount_limit": "an amount is within a limit read from another field", "amounts_match": "amounts agree within a tolerance",
         "value_in": "a value is one of a list", "value_not_in": "a value is none of a list", "value_limit": "an amount is within fixed bounds",
         "required_field": "a value is stated", "document_required": "a document is in the package"}
ID = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


class RuleError(ValueError):
    """A change to the rules that cannot be made, said in words."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Rulebook:
    def __init__(self, path: Path | None = None):
        self.path = path

    def read(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.path is not None and self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if not isinstance(data, dict):   # never read as "this workspace has no rules of its own": that would quietly put the shipped limits back
                raise RuleError(f"the rules this workspace made its own could not be read ({self.path.name} is damaged). Nothing is assessed on rules that may not be the right ones. "
                                "Restore the file from a backup; every change it held is also in the provenance ledger, with the rule before and after.")
        return {"version": int(data.get("version") or 0), "rules": dict(data.get("rules") or {}), "evidence": dict(data.get("evidence") or {}),
                "off": {g: list((data.get("off") or {}).get(g) or []) for g in GROUPS}, "history": list(data.get("history") or [])}

    def save(self, data: dict[str, Any]) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)


# ------------------------------------------------------------------------------------------------ the rules in force
def apply(profile: Profile, book: dict[str, Any]) -> Profile:
    """The use case as this workspace runs it: the shipped rules with the workspace's changes laid over them."""
    if not book.get("version"):
        return profile
    out = copy.copy(profile)
    off = book.get("off") or {}
    mine = book.get("rules") or {}
    shipped = {r["id"] for r in profile.rules}
    out.rules = [_runnable(profile, mine[r["id"]]) if r["id"] in mine else copy.deepcopy(r) for r in profile.rules if r["id"] not in (off.get("rules") or [])] + \
                [_runnable(profile, r) for rid, r in mine.items() if rid not in shipped and rid not in (off.get("rules") or [])]
    added = book.get("evidence") or {}
    out.evidence = [e for e in profile.evidence if e["id"] not in (off.get("evidence") or [])] + [copy.deepcopy(e) for eid, e in added.items() if eid not in (off.get("evidence") or [])]
    out.consistency = [c for c in profile.consistency if c["id"] not in (off.get("consistency") or [])]
    out.rulebook = {"version": book["version"], "changed": sorted(mine), "added_evidence": sorted(added), "off": {g: sorted(off.get(g) or []) for g in GROUPS if off.get(g)}}
    return out


def problem(profile: Profile, rule: dict[str, Any]) -> str:
    """Why a rule of the workspace's own can no longer run in this build ("" when it can): a value the use case no longer reads, a kind this build
    does not know. It was sound when it was saved; an upgrade or a hand edit made it not so."""
    try:
        return "; ".join(profile.rule_problems(rule))
    except Exception as exc:   # noqa: BLE001 (a rule too broken to be checked is a rule that cannot run)
        return f"the rule could not be checked ({type(exc).__name__})"


def _runnable(profile: Profile, rule: dict[str, Any]) -> dict[str, Any]:
    """The rule as the pipeline runs it. One that can no longer run is kept in the rules as itself, marked: the assessment says so and a person is asked,
    because a rule that is quietly skipped is a check the business believes it has."""
    why = problem(profile, rule)
    if not why:
        return copy.deepcopy(rule)
    return {"id": rule.get("id"), "title": rule.get("title") or str(rule.get("id")), "family": rule.get("family") or "policy", "version": rule.get("version"), "note": rule.get("note") or "",
            "type": "unrunnable", "problem": why, "written_as": str(rule.get("type") or "")}


def sentence(rule: dict[str, Any], profile: Profile) -> str:
    """One rule in a sentence a claims handler would write."""
    n, kind = profile.field_name, rule.get("type")
    if kind == "date_order":
        text = f"{n(rule['first'])} is not after {n(rule['then'])}"
    elif kind == "date_interval":
        text = f"{n(rule['to'])} is within {rule.get('max_days')} day(s) of {n(rule['from'])}"
    elif kind == "amount_limit":
        text = f"{n(rule['amount'])} is not more than {n(rule['limit'])}" + (f", give or take {rule['tolerance_pct']}%" if rule.get("tolerance_pct") else "")
    elif kind == "amounts_match":
        text = " and ".join(n(x) for x in rule.get("amounts") or []) + f" agree within {rule.get('tolerance_pct') or 0}%"
    elif kind == "value_in":
        text = f"{n(rule['field'])} is {'none' if rule.get('negate') else 'one'} of: {', '.join(str(v) for v in rule.get('values') or [])}"
    elif kind == "value_limit":
        bounds = " and ".join(x for x in (f"at least {_num(rule['min'])}" if rule.get("min") not in (None, "") else "", f"at most {_num(rule['max'])}" if rule.get("max") not in (None, "") else "") if x)
        text = f"{n(rule['field'])} is {bounds}" + (f" {rule['currency']}" if rule.get("currency") else "")
    elif kind == "required_field":
        text = f"{n(rule['field'])} is stated"
    elif kind == "codes_consistent":
        text = "the codes stated agree with each other and with the reference"
    else:
        text = rule.get("title") or str(rule.get("id"))
    when = rule.get("applies_when")
    if when:
        text += (f" (when {n(when['ref'])} is none of {', '.join(str(x) for x in when['not_in'])})" if when.get("not_in")
                 else f" (when {n(when['ref'])} is {' or '.join(str(x) for x in (when.get('in') or [when.get('is')]))})")
    return text[:1].upper() + text[1:] + "."


def fields(profile: Profile) -> list[dict[str, Any]]:
    """Every field a rule may name, with its kind of value, for the screen and the template."""
    out = [{"ref": f"case.{f['id']}", "name": f"Case record · {f.get('name') or f['id']}", "type": f.get("type", "text"), "from": "case"} for f in profile.case.get("fields") or []]
    for tid, t in profile.types.items():
        out += [{"ref": f"{tid}.{f['id']}", "name": f"{t.get('name') or tid} · {f.get('name') or f['id']}", "type": f.get("type", "text"), "from": "document"} for f in t.get("fields") or []]
    for s in profile.systems:
        out += [{"ref": f"record.{s['id']}.{f['id']}", "name": f"{s.get('name') or s['id']} · {f.get('name') or f['id']}", "type": f.get("type", "text"), "from": "record"} for f in s.get("fields") or []]
    return out


def listing(profile: Profile, book: dict[str, Any]) -> dict[str, Any]:
    """Everything the Rules screen shows for one use case: each rule with where it comes from, whether it is on, and what it says."""
    off, mine = book.get("off") or {}, book.get("rules") or {}
    shipped = {r["id"]: r for r in profile.rules}
    rows = []
    for rid in [*shipped, *[k for k in mine if k not in shipped]]:
        r = mine.get(rid) or shipped[rid]
        rows.append({"id": rid, "group": "rules", "title": r.get("title") or rid, "kind": r.get("type"), "family": r.get("family") or "policy", "version": str(r.get("version") or profile.version),
                     "origin": "added here" if rid not in shipped else "changed here" if rid in mine else "shipped", "enabled": rid not in (off.get("rules") or []),
                     "says": sentence(r, profile), "note": r.get("note") or "", "rule": r, "shipped": shipped.get(rid), "problem": problem(profile, r) if rid in mine else ""})
    added = book.get("evidence") or {}
    evidence = [{"id": e["id"], "group": "evidence", "title": e.get("title") or e["id"], "kind": "document_required", "origin": "added here" if e["id"] in added else "shipped",
                 "enabled": e["id"] not in (off.get("evidence") or []), "any_of": e.get("any_of") or [], "required": e.get("required") or "always", "note": e.get("note") or "",
                 "says": " or ".join(profile.type_name(t) for t in e.get("any_of") or []) + (" is in the package." if (e.get("required") or "always") == "always" else " is in the package when it applies.")}
                for e in [*profile.evidence, *added.values()]]
    consistency = [{"id": c["id"], "group": "consistency", "title": c.get("title") or c["id"], "kind": f"agreement ({c.get('kind', 'text')})", "origin": "shipped",
                    "enabled": c["id"] not in (off.get("consistency") or []), "says": "The same on every document: " + ", ".join(profile.field_name(f) for f in c.get("fields") or []) + ".", "note": c.get("note") or ""}
                   for c in profile.consistency]
    return {"profile": profile.id, "name": profile.name, "version": book.get("version") or 0, "rules": rows, "evidence": evidence, "consistency": consistency,
            "history": list(reversed(book.get("history") or []))[:100], "fields": fields(profile), "kinds": KINDS,
            "document_types": [{"id": tid, "name": t.get("name") or tid} for tid, t in profile.types.items()],
            "systems": [{"id": s["id"], "name": s.get("name") or s["id"], "key": profile.field_name(s["key"])} for s in profile.systems]}


# ------------------------------------------------------------------------------------------------ changing them
def _core(rule: dict[str, Any]) -> dict[str, Any]:
    """A rule as far as it decides anything or is read by anyone: without its version, and without what is empty."""
    return {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for k, v in rule.items() if k != "version" and v not in (None, "", [], False)}


def _num(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"


def _clean(rule: dict[str, Any], profile: Profile, rid: str) -> dict[str, Any]:
    """A rule as given on the portal or in the template, checked and made whole. Raises RuleError with every problem in words."""
    if not isinstance(rule, dict):
        raise RuleError("give the rule as an object")
    kind = str(rule.get("type") or rule.get("kind") or "").strip()
    out: dict[str, Any] = {"id": rid, "type": "value_in" if kind == "value_not_in" else kind, "title": " ".join(str(rule.get("title") or "").split())[:160], "family": str(rule.get("family") or "workspace")[:40],
                           "note": " ".join(str(rule.get("note") or "").split())[:300]}
    if kind == "value_not_in" or rule.get("negate"):
        out["negate"] = True
    for key in RULE_TYPES.get(out["type"], ()) + ("tolerance_pct", "max", "min", "currency", "severity"):
        if rule.get(key) not in (None, "", []):
            out[key] = rule[key]
    for key in ("max_days",):
        if key in out:
            try:
                out[key] = int(float(out[key]))
            except (TypeError, ValueError):
                pass
    for key in ("tolerance_pct", "max", "min"):
        if key in out:
            try:
                out[key] = float(out[key])
            except (TypeError, ValueError):
                pass
    if "values" in out:
        out["values"] = [str(v).strip() for v in (out["values"] if isinstance(out["values"], list) else str(out["values"]).split(";")) if str(v).strip()]
    if "amounts" in out and not isinstance(out["amounts"], list):
        out["amounts"] = [x.strip() for x in str(out["amounts"]).split(";") if x.strip()]
    if out.get("currency"):
        out["currency"] = str(out["currency"]).strip().upper()[:3]
    if out.get("severity") not in (None, "low", "medium", "high"):
        raise RuleError("severity is low, medium or high")
    when = rule.get("applies_when")
    if when:
        many = lambda v: [str(x).strip() for x in (v if isinstance(v, list) else str(v).split(";")) if str(x).strip()]  # noqa: E731
        out["applies_when"] = {"ref": str(when.get("ref") or ""), **({"not_in": many(when["not_in"])} if when.get("not_in") else {"in": many(when["in"])} if when.get("in") else {"is": str(when.get("is") or "")})}
    out = {k: v for k, v in out.items() if k in ("id", "type", "title", "family") or v not in (None, "", [])}
    problems = [] if out["title"] else ["give the rule a title: the sentence a caseworker will read"]
    problems += profile.rule_problems(out)
    if problems:
        raise RuleError("; ".join(p.replace(f"rule '{rid}': ", "").replace(f"rule '{rid}' ", "") for p in problems))
    return out


def change(profile: Profile, book: dict[str, Any], op: dict[str, Any], *, by: str = "caseworker") -> tuple[dict[str, Any], dict[str, Any]]:
    """Make one change to a workspace's rules and return (the new workbook, the history entry). `profile` is the use case as shipped.

    op: {"do": "set", "rule": {...}}                      change a shipped rule, or add or change one of the workspace's own
        {"do": "reset", "id": ...}                        take a shipped rule back to how it shipped; remove one that was added here
        {"do": "on" | "off", "group": ..., "id": ...}     switch a rule, a document requirement or a consistency check on or off
        {"do": "require", "evidence": {...}}              add or change a document requirement of the workspace's own
    Every op may carry "note": why."""
    if not isinstance(op, dict):
        raise RuleError("give the change as an object")
    book = copy.deepcopy(book)
    do, note = str(op.get("do") or ""), " ".join(str(op.get("note") or "").split())[:300]
    shipped = {r["id"]: r for r in profile.rules}
    entry: dict[str, Any] = {"at": now(), "by": by, "note": note}
    if do == "set":
        raw = op.get("rule") or {}
        rid = str(raw.get("id") or "").strip().lower()
        if not ID.match(rid):
            raise RuleError("a rule's id is 2 to 49 lower-case letters, digits and underscores, starting with a letter")
        if shipped.get(rid, {}).get("type") == "codes_consistent":
            raise RuleError("this rule reads a reference source and is changed in the use case's profile, not here")
        before = book["rules"].get(rid) or shipped.get(rid)
        asked = str(raw.get("type") or raw.get("kind") or "").strip()
        if before and asked and ("value_in" if asked == "value_not_in" else asked) != before.get("type"):
            raise RuleError("a rule keeps its kind: switch this one off and add another of the kind you need")
        rule = _clean({**(before or {}), **raw} if before else raw, profile, rid)
        if before and rid in shipped:
            rule["family"] = shipped[rid].get("family") or rule["family"]
        if before and _core(rule) == _core(before):
            raise RuleError("nothing was changed")
        rule["version"] = f"{shipped[rid].get('version') or profile.version}+w{book['version'] + 1}" if rid in shipped else f"w{book['version'] + 1}"
        book["rules"][rid] = rule
        entry.update(what="changed" if before else "added", group="rules", id=rid, title=rule["title"], before=before, after=rule)
    elif do == "reset":
        rid = str(op.get("id") or "")
        if rid in book["rules"]:
            entry.update(what="taken back to how it shipped" if rid in shipped else "removed", group="rules", id=rid, title=book["rules"][rid].get("title"), before=book["rules"].pop(rid), after=shipped.get(rid))
        elif rid in book["evidence"]:
            entry.update(what="removed", group="evidence", id=rid, title=book["evidence"][rid].get("title"), before=book["evidence"].pop(rid), after=None)
        else:
            raise RuleError(f"'{rid}' has not been changed in this workspace")
        for g in GROUPS:
            if rid in book["off"][g] and rid not in shipped and g != "consistency" and rid not in {e["id"] for e in profile.evidence}:
                book["off"][g].remove(rid)
    elif do in ("on", "off"):
        group, rid = str(op.get("group") or "rules"), str(op.get("id") or "")
        known = {"rules": {*shipped, *book["rules"]}, "evidence": {*(e["id"] for e in profile.evidence), *book["evidence"]}, "consistency": {c["id"] for c in profile.consistency}}
        if group not in GROUPS or rid not in known[group]:
            raise RuleError(f"there is no {group[:-1] if group == 'rules' else group} '{rid}' in this use case")
        if (do == "off") == (rid in book["off"][group]):
            raise RuleError(f"'{rid}' is already switched {do}")
        if do == "off" and len(note) < 5:
            raise RuleError("say why this is switched off: the reason is kept with the change")
        book["off"][group].append(rid) if do == "off" else book["off"][group].remove(rid)
        entry.update(what=f"switched {do}", group=group, id=rid, title=rid, before=None, after=None)
    elif do == "require":
        raw = op.get("evidence") or {}
        eid = str(raw.get("id") or "").strip().lower()
        if not ID.match(eid) or eid in {e["id"] for e in profile.evidence}:
            raise RuleError("give the requirement an id of its own: lower-case letters, digits and underscores")
        any_of = [t for t in (raw.get("any_of") if isinstance(raw.get("any_of"), list) else str(raw.get("any_of") or "").split(";")) if str(t).strip()]
        any_of = [str(t).strip() for t in any_of]
        unknown = [t for t in any_of if t not in profile.types]
        if not any_of or unknown:
            raise RuleError("name the kind of document that satisfies it" + (f" (unknown: {', '.join(unknown)}; known: {', '.join(profile.types)})" if unknown else ""))
        title = " ".join(str(raw.get("title") or "").split())[:120] or " or ".join(profile.type_name(t) for t in any_of)
        ev = {"id": eid, "title": title, "any_of": any_of, "required": "always", "note": " ".join(str(raw.get("note") or "").split())[:300]}
        before = book["evidence"].get(eid)
        book["evidence"][eid] = ev
        entry.update(what="changed" if before else "added", group="evidence", id=eid, title=title, before=before, after=ev)
    else:
        raise RuleError("say what to do: set, reset, on, off or require")
    book["version"] += 1
    entry["version"] = book["version"]
    book["history"].append(entry)
    del book["history"][:-500]
    return book, entry


# ------------------------------------------------------------------------------------------------ the template people fill in
def _row(r: dict[str, Any], enabled: bool) -> dict[str, Any]:
    kind = r.get("type")
    when = r.get("applies_when") or {}
    row = {"id": r["id"], "title": r.get("title") or "", "kind": "value_not_in" if kind == "value_in" and r.get("negate") else kind, "tolerance_pct": r.get("tolerance_pct", ""),
           "applies_when_field": when.get("ref", ""), "applies_when_value": ("not: " + "; ".join(when["not_in"]) if when.get("not_in") else "; ".join(when.get("in") or [when.get("is") or ""])) if when else "", "enabled": "yes" if enabled else "no", "note": r.get("note") or ""}
    if kind == "date_order":
        row.update(field_1=r["first"], field_2=r["then"])
    elif kind == "date_interval":
        row.update(field_1=r["from"], field_2=r["to"], limit_or_values=r.get("max_days", ""))
    elif kind == "amount_limit":
        row.update(field_1=r["amount"], field_2=r["limit"])
    elif kind == "amounts_match":
        row.update(field_1=(r.get("amounts") or [""])[0], field_2="; ".join((r.get("amounts") or [])[1:]))
    elif kind == "value_in":
        row.update(field_1=r["field"], limit_or_values="; ".join(str(v) for v in r.get("values") or []))
    elif kind == "value_limit":
        row.update(field_1=r["field"], limit_or_values="; ".join(f"{k}={r[k]}" for k in ("min", "max", "currency") if r.get(k) not in (None, "")))
    elif kind == "required_field":
        row.update(field_1=r["field"])
    return row


def template_csv(profile: Profile, book: dict[str, Any]) -> str:
    """The rules in force as a sheet to fill in: change a limit, add a row, mark a row "no" to switch it off. It imports back as it is."""
    view = listing(profile, book)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in view["rules"]:
        if r["kind"] != "codes_consistent":
            w.writerow({c: _row(r["rule"], r["enabled"]).get(c, "") for c in COLUMNS})
    for e in view["evidence"]:
        w.writerow({"id": e["id"], "title": e["title"], "kind": "document_required", "field_1": "; ".join(e["any_of"]), "enabled": "yes" if e["enabled"] else "no", "note": e["note"]})
    return buf.getvalue()


GUIDE = [   # how each kind of rule is written in the sheet: (kind, what it checks, field_1, field_2, limit_or_values, tolerance_pct, an example in words)
    ("date_order", "One date is on or before another", "the date that must come first", "the date that must come after", "", "", "The loss happened on or before the end of cover"),
    ("date_interval", "No more than a number of days between two dates", "the earlier date", "the later date", "the most days allowed, e.g. 30", "", "The claim was notified within 30 days of the loss"),
    ("amount_limit", "An amount is within a limit read from a document or a record", "the amount", "the limit it must not pass", "", "percent it may go over (0: none)", "The amount claimed is within the sum insured"),
    ("amounts_match", "Amounts agree across documents", "the first amount", "the amount(s) it must agree with; several separated by ;", "", "percent they may differ by", "The estimate supports the amount claimed, within 5 percent"),
    ("value_in", "A value is one of a list", "the value", "", "the values allowed, separated by ;", "", "The policy status is: in force"),
    ("value_not_in", "A value is none of a list", "the value", "", "the values not allowed, separated by ;", "", "The policy status is not: cancelled; lapsed"),
    ("value_limit", "A number or an amount is within bounds you state", "the value", "", "max=40000; currency=GBP (also min=)", "", "A claim above 40,000 goes to a senior handler"),
    ("required_field", "A value must have been found in the documents", "the value", "", "", "", "The claim form states a policy number"),
    ("document_required", "A kind of document must be in the package", "the document's id; alternatives separated by ;", "", "", "", "An incident report is always required"),
]
HOWTO = [
    "This sheet is the rules of one use case, one rule to a row. Change a row, add rows of your own, then import the file on the Rules screen.",
    "Nothing changes until someone presses Import and confirms the preview. A row that cannot be read is refused and named; the others are still made.",
    "id: a short name of your own for a new rule (lower-case letters, digits, underscores). Keep the id of a rule that is already there.",
    "title: the rule as a caseworker reads it. kind: one of the kinds below (the cell offers the list).",
    "field_1, field_2: the values the rule reads. Use the names on the sheet 'Values'.",
    "applies_when_field and applies_when_value: leave empty for a rule that always applies. To limit a rule, name a value and what it must be (several separated by ;). Example: record.policy_admin.region and IN. For 'everywhere but', begin with not: (not: US; IN).",
    "enabled: yes or no. 'no' switches the rule off without losing it. note: why the rule is what it is. It is kept with the change in the audit trail.",
    "To remove a rule you added, switch it off (enabled: no) or remove it on the Rules screen. Rows you delete from the sheet are left as they are in the product.",
    "Limits that shipped with the product are sample values. Replace them with the conditions of your own policies and procedures.",
]


def _xml(v: Any) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str("" if v is None else v)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _col(n: int) -> str:
    out = ""
    while n >= 0:
        out, n = chr(65 + n % 26) + out, n // 26 - 1
    return out


def _sheet(rows: list[list[Any]], widths: list[int], *, head: int = 1, lists: dict[int, list[str]] | None = None, bold: tuple[int, ...] = (), wrap_from: int = 0) -> str:
    """One worksheet: text cells as written (a number stays a number), the first `head` row(s) bold and frozen, optional pick-lists by column.
    `bold` names further heading rows; from row `wrap_from` on, long text wraps inside its cell."""
    body = []
    for i, row in enumerate(rows, start=1):
        cells = []
        for j, v in enumerate(row):
            if v in (None, ""):
                continue
            style = 1 if i <= head or i in bold else (2 if wrap_from and i >= wrap_from else 0)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append(f'<c r="{_col(j)}{i}" s="{style}"><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{_col(j)}{i}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{_xml(v)}</t></is></c>')
        body.append(f'<row r="{i}">{"".join(cells)}</row>')
    cols = "".join(f'<col min="{k}" max="{k}" width="{w}" customWidth="1"/>' for k, w in enumerate(widths, start=1))
    checks = ""
    if lists:
        items = "".join(f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" errorTitle="Not one of the list" error="Choose one of the values offered." sqref="{_col(c)}{head + 1}:{_col(c)}2000">'
                        f'<formula1>&quot;{_xml(",".join(vals))}&quot;</formula1></dataValidation>' for c, vals in lists.items())
        checks = f'<dataValidations count="{len(lists)}">{items}</dataValidations>'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="{head}" topLeftCell="A{head + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>{"".join(body)}</sheetData>{checks}</worksheet>')


def template_xlsx(profile: Profile, book: dict[str, Any]) -> bytes:
    """The same sheet as a workbook a claims or operations team fills in: the rules in force, how each kind is written, and the names a rule can use.
    It imports back as it is. Written here cell by cell, so the product needs no spreadsheet library."""
    import zipfile

    table = list(csv.reader(io.StringIO(template_csv(profile, book))))
    rules = [table[0]] + [[int(c) if re.fullmatch(r"\d{1,9}", c) and COLUMNS[k] in ("limit_or_values", "tolerance_pct") else c for k, c in enumerate(r)] for r in table[1:]]
    how = [["How to fill in the rules sheet"], *[[x] for x in HOWTO], [], ["kind", "What it checks", "field_1", "field_2", "limit_or_values", "tolerance_pct", "An example, in words"], *[list(g) for g in GUIDE]]
    vals = [["Name to use in the sheet", "What it is", "Kind of value"], *[[f["ref"], f["name"], f["type"]] for f in fields(profile)],
            [], ["Documents (for kind document_required)", "", ""], *[[t, (profile.types[t].get("name") or t), "document"] for t in profile.types]]
    sheets = [("Rules", _sheet(rules, [26, 52, 18, 34, 34, 26, 13, 30, 22, 9, 60], lists={2: list(KINDS), 9: ["yes", "no"]})),
              ("How to fill it in", _sheet(how, [20, 46, 34, 40, 36, 30, 52], bold=(len(HOWTO) + 3,), wrap_from=len(HOWTO) + 4)),
              ("Values", _sheet(vals, [44, 46, 16], bold=(len(fields(profile)) + 3,)))]
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE8ECF4"/><bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="{pkg}/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(sheets) + 1))
                   + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        z.writestr("_rels/.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg}/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="{rel}"><sheets>'
                   + "".join(f'<sheet name="{_xml(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in enumerate(sheets, start=1)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg}/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="{rel}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="{rel}/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", styles)
        for i, (_, xml) in enumerate(sheets, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    return buf.getvalue()


def sheet_text(data: bytes) -> str:
    """A filled-in workbook as the text `read_template` reads: the sheet named Rules (or the first one), a row to a line, each cell in its own column."""
    import zipfile
    from xml.etree import ElementTree

    ns, rns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}", "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        if sum(i.file_size for i in z.infolist()) > 20 * 1024 * 1024:
            raise RuleError("the workbook is larger than a rules sheet can be")
        names = z.namelist()
        target = ""
        if "xl/workbook.xml" in names and "xl/_rels/workbook.xml.rels" in names:
            where = {r.get("Id"): r.get("Target") or "" for r in ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
            listed = [(sh.get("name") or "", where.get(sh.get(f"{rns}id")) or "") for sh in ElementTree.fromstring(z.read("xl/workbook.xml")).iter(f"{ns}sheet")]
            pick = next((t for n, t in listed if n.strip().lower() == "rules"), listed[0][1] if listed else "")
            target = pick.lstrip("/") if pick.startswith("/") else "xl/" + pick if pick else ""
        if target not in names:
            target = next((n for n in sorted(names) if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)), "")
        if not target:
            raise RuleError("the workbook holds no sheet")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{ns}si"):
                shared.append("".join(t.text or "" for part in [si, *si.findall(f"{ns}r")] for t in part.findall(f"{ns}t")))   # the text and its runs, not the phonetic guide
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\n")
        for row in ElementTree.fromstring(z.read(target)).iter(f"{ns}row"):
            cells: dict[int, str] = {}
            at = 0
            for c in row.findall(f"{ns}c"):
                m = re.match(r"([A-Z]{1,3})", c.get("r") or "")
                if m:
                    at = 0
                    for ch in m.group(1):
                        at = at * 26 + ord(ch) - 64
                    at -= 1
                v = c.find(f"{ns}v")
                kind = c.get("t")
                if kind == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
                    text = shared[int(v.text)]
                elif kind == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(f"{ns}t"))
                elif kind == "b":
                    text = "yes" if v is not None and v.text == "1" else "no"
                else:
                    text = (v.text or "") if v is not None else ""
                    if re.fullmatch(r"-?\d+\.0+", text):
                        text = text.split(".")[0]
                if at < 60:
                    cells[at] = text
                at += 1
            if cells:
                w.writerow([cells.get(i, "") for i in range(max(cells) + 1)])
        return out.getvalue()
    except RuleError:
        raise
    except Exception as exc:   # noqa: BLE001 (whatever is wrong with the file, the answer is the same: it is not a rules workbook)
        raise RuleError(f"the file could not be read as a workbook ({type(exc).__name__}). Use the sheet downloaded from the Rules screen.") from exc


def _from_row(row: dict[str, str]) -> dict[str, Any]:
    g = lambda k: (row.get(k) or "").strip()   # noqa: E731
    kind = g("kind").lower().replace(" ", "_")
    rule: dict[str, Any] = {"id": g("id").lower(), "title": g("title"), "type": kind, "note": g("note")}
    if kind == "date_order":
        rule.update(first=g("field_1"), then=g("field_2"))
    elif kind == "date_interval":
        rule.update({"from": g("field_1"), "to": g("field_2"), "max_days": g("limit_or_values")})
    elif kind == "amount_limit":
        rule.update(amount=g("field_1"), limit=g("field_2"))
    elif kind == "amounts_match":
        rule.update(amounts=[x for x in [g("field_1"), *[y.strip() for y in g("field_2").split(";")]] if x])
    elif kind in ("value_in", "value_not_in"):
        rule.update(field=g("field_1"), values=[v.strip() for v in g("limit_or_values").split(";") if v.strip()])
    elif kind == "value_limit":
        rule.update(field=g("field_1"))
        for part in g("limit_or_values").split(";"):
            k, eq, v = part.partition("=")
            if eq and k.strip().lower() in ("min", "max", "currency"):
                rule[k.strip().lower()] = v.strip()
            elif part.strip():
                rule["max"] = part.strip()
    elif kind == "required_field":
        rule.update(field=g("field_1"))
    if g("tolerance_pct"):
        rule["tolerance_pct"] = g("tolerance_pct")
    if g("applies_when_field"):
        text = g("applies_when_value")
        other = text.lower().startswith("not:")   # "not: US; IN": everywhere but
        vals = [v.strip() for v in (text[4:] if other else text).split(";") if v.strip()]
        rule["applies_when"] = {"ref": g("applies_when_field"), **({"not_in": vals} if other else {"in": vals} if len(vals) > 1 else {"is": vals[0] if vals else ""})}
    return rule


def read_template(profile: Profile, book: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """A filled-in template as the changes it asks for, each checked on its own: [{"row", "id", "title", "does": "add" | "change" | "switch on" |
    "switch off" | "nothing" | "refused", "problem", "ops": [...]}]. Nothing is saved here."""
    text = (text or "").lstrip("\ufeff")
    head = text.split("\n", 1)[0]
    sep = max(",;\t", key=head.count)   # a spreadsheet saves the sheet with the separator of its region: a comma, a semicolon or a tab
    try:
        rows = list(csv.DictReader(io.StringIO(text), delimiter=sep))
    except csv.Error as exc:
        raise RuleError(f"the file could not be read as a sheet: {exc}") from exc
    if not rows or not {"id", "kind"} <= {(c or "").strip().lower() for c in rows[0]}:
        raise RuleError("the sheet needs the template's columns: " + ", ".join(COLUMNS))
    if len(rows) > 500:
        raise RuleError("a sheet holds at most 500 rules")
    view = listing(profile, book)
    have = {r["id"]: r for r in view["rules"]}
    have_ev = {e["id"]: e for e in view["evidence"]}
    out = []
    for n, raw in enumerate(rows, start=2):
        row = {(k or "").strip().lower(): (v or "") for k, v in raw.items()}
        rid, kind = row.get("id", "").strip().lower(), row.get("kind", "").strip().lower().replace(" ", "_")
        if not rid and not kind and not row.get("title", "").strip():
            continue
        item: dict[str, Any] = {"row": n, "id": rid, "title": row.get("title", "").strip(), "does": "nothing", "problem": "", "ops": []}
        wanted_on = row.get("enabled", "yes").strip().lower() not in ("no", "n", "off", "false", "0")
        try:
            if kind == "document_required":
                cur = have_ev.get(rid)
                types = [t.strip() for t in row.get("field_1", "").split(";") if t.strip()]
                if cur and cur["origin"] == "shipped":
                    if types and types != cur["any_of"]:
                        raise RuleError("a requirement that shipped keeps its documents: switch it off and add one of your own")
                else:
                    trial, _ = change(profile, book, {"do": "require", "evidence": {"id": rid, "title": item["title"], "any_of": types, "note": row.get("note", "")}})
                    if not cur or _core(trial["evidence"][rid]) != _core((book.get("evidence") or {}).get(rid, {})):
                        item["ops"].append({"do": "require", "evidence": {"id": rid, "title": item["title"], "any_of": types, "note": row.get("note", "")}})
                        item["does"] = "change" if cur else "add"
                group, was_on = "evidence", (cur or {}).get("enabled", True)
            else:
                cur = have.get(rid)
                rule = _from_row(row)
                try:
                    change(profile, book, {"do": "set", "rule": rule})
                    item["ops"].append({"do": "set", "rule": rule})
                    item["does"] = "change" if cur else "add"
                except RuleError as exc:
                    if str(exc) != "nothing was changed":
                        raise
                group, was_on = "rules", (cur or {}).get("enabled", True)
            if wanted_on != was_on:
                item["ops"].append({"do": "on" if wanted_on else "off", "group": group, "id": rid, "note": "Switched in the rules sheet"})
                item["does"] = (item["does"] + ", " if item["does"] != "nothing" else "") + ("switch on" if wanted_on else "switch off")
        except (RuleError, ProfileError, KeyError) as exc:
            item.update(does="refused", problem=str(exc), ops=[])
        out.append(item)
    return out


__all__ = ["Rulebook", "RuleError", "apply", "listing", "change", "sentence", "fields", "template_csv", "read_template", "COLUMNS", "KINDS", "GROUPS"]
