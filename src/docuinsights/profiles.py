"""Use-case profiles: everything DocuInsights knows about a domain is declared in docuinsights/profiles/<id>.yaml.

Extra folders can be added with DOCUINSIGHTS_PROFILES_DIR (a profile there replaces a shipped one with the same id).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
FIELD_TYPES = ("text", "party", "date", "money", "number", "code", "ref")


class ProfileError(ValueError):
    pass


class Profile:
    def __init__(self, raw: dict[str, Any], path: Path):
        self.raw = raw
        self.path = path
        self.id: str = raw["id"]
        self.name: str = raw.get("name") or self.id
        self.version: str = str(raw.get("version") or "1.0")
        self.description: str = raw.get("description") or ""
        self.brand: dict[str, Any] = raw.get("brand") or {}
        self.case: dict[str, Any] = raw.get("case") or {}
        self.types: dict[str, dict[str, Any]] = {t["id"]: t for t in raw.get("document_types") or []}
        self.entities: dict[str, Any] = raw.get("entities") or {}
        self.evidence: list[dict[str, Any]] = raw.get("evidence") or []
        self.references: list[dict[str, Any]] = raw.get("reference_sources") or []
        self.rules: list[dict[str, Any]] = raw.get("rules") or []
        self.systems: list[dict[str, Any]] = raw.get("systems") or []   # the systems of record this use case checks against (systems.py)
        self.consistency: list[dict[str, Any]] = raw.get("consistency") or []
        self.outcomes: dict[str, Any] = raw.get("outcomes") or {}
        self.counterfactuals: list[dict[str, Any]] = raw.get("counterfactuals") or []
        self.correspondence: dict[str, Any] = raw.get("correspondence") or {}
        self.synonyms: dict[str, dict[str, str]] = raw.get("synonyms") or {}
        self.samples: list[dict[str, Any]] = raw.get("samples") or []
        self.ontology: dict[str, Any] = raw.get("ontology") or {}
        self.order: int = int(raw.get("order") or 100)          # where the use case sits in a list: the plainest first
        self.sector: str = raw.get("sector") or ""              # the kind of organisation that runs it
        self.plain: str = raw.get("plain") or self.description  # what it does, in one sentence anyone can read
        self.memory: dict[str, Any] = raw.get("memory") or {}
        # the assurance agents: what each is told about this use case (all four work without a word here)
        self.integrity: dict[str, Any] = raw.get("integrity") or {}   # sums, check digits, dates and details that must not change
        self.screening: dict[str, Any] = raw.get("screening") or {}   # who is screened against the watchlists
        self.privacy: dict[str, Any] = raw.get("privacy") or {}       # personal data the use case does not expect
        self.service: dict[str, Any] = raw.get("service") or {}       # the service target a case is triaged against
        self.formats: dict[str, Any] = raw.get("formats") or {}       # how its documents write a date: {dates: day_first | month_first}
        order = self.formats.get("dates") or "day_first"
        if order not in ("day_first", "month_first"):
            raise ProfileError(f"{self.id}: formats.dates is day_first or month_first")
        for t in self.types.values():   # each date field reads the way the use case says, unless the field says otherwise itself
            for f in t.get("fields") or []:
                if f.get("type") == "date":
                    f.setdefault("order", order)
        self._check()

    def _check(self) -> None:
        for tid, t in self.types.items():
            for f in t.get("fields") or []:
                if f.get("type", "text") not in FIELD_TYPES:
                    raise ProfileError(f"{self.id}: field {tid}.{f.get('id')} has unknown type '{f.get('type')}'")
        known = set(self.types)
        for ev in self.evidence:
            unknown = [t for t in ev.get("any_of") or [] if t not in known]
            if unknown:
                raise ProfileError(f"{self.id}: evidence '{ev.get('id')}' names unknown document type(s) {unknown}")
        for sysd in self.systems:
            if not sysd.get("id") or not str(sysd["id"]).replace("_", "").isalnum():
                raise ProfileError(f"{self.id}: a system of record needs an id of letters, digits and underscores")
            if not self.knows(sysd.get("key") or ""):
                raise ProfileError(f"{self.id}: system '{sysd['id']}' is looked up by unknown field '{sysd.get('key')}'")
            for f in sysd.get("fields") or []:
                if f.get("type", "text") not in FIELD_TYPES:
                    raise ProfileError(f"{self.id}: system field {sysd['id']}.{f.get('id')} has unknown type '{f.get('type')}'")
        for group in (self.rules, self.consistency):
            for r in group:
                for problem in self.rule_problems(r):
                    raise ProfileError(f"{self.id}: {problem}")
        from . import assurance   # imported here: it reads profiles

        wrong = assurance.check_profile(self)
        if wrong:
            raise ProfileError(f"{self.id}: " + "; ".join(wrong))

    def type_name(self, type_id: str | None) -> str:
        return (self.types.get(type_id or "") or {}).get("name") or (type_id or "Unclassified")

    def field(self, type_id: str, field_id: str) -> dict[str, Any] | None:
        for f in (self.types.get(type_id) or {}).get("fields") or []:
            if f["id"] == field_id:
                return f
        return None

    def spec_of(self, ref: str) -> dict[str, Any] | None:
        """The declaration of the field a rule names (`type.field`, `case.field` or `record.system.field`), or None when there is none."""
        head, _, fld = str(ref or "").partition(".")
        if head == "case":
            return next((f for f in self.case.get("fields") or [] if f["id"] == fld), None)
        if head == "record":
            sid, _, name = fld.partition(".")
            sysd = next((x for x in self.systems if x["id"] == sid), None) or {}
            return next((f for f in sysd.get("fields") or [] if f["id"] == name), None)
        return next((f for f in (self.types.get(head) or {}).get("fields") or [] if f["id"] == fld), None)

    def knows(self, ref: str) -> bool:
        return self.spec_of(ref) is not None

    def rule_problems(self, r: dict[str, Any]) -> list[str]:
        """What is wrong with one rule or consistency check, in words (an empty list when nothing is)."""
        rid, kind = r.get("id"), r.get("type")
        bad = [f"rule '{rid}' refers to unknown field '{ref}'" for ref in _refs_of(r) if not self.knows(ref)]
        if "kind" in r and not kind:   # a consistency check: its fields are all it names
            return bad
        if kind not in RULE_TYPES:
            return [f"rule '{rid}' has unknown type '{kind}' (known: {', '.join(sorted(RULE_TYPES))})"]
        missing = [k for k in RULE_TYPES[kind] if r.get(k) in (None, "", [])]
        if missing:
            bad.append(f"rule '{rid}' ({kind}) needs {', '.join(missing)}")

        def is_type(ref: Any, *types: str) -> bool:
            return (self.spec_of(str(ref)) or {}).get("type", "text") in types

        if kind in ("date_order", "date_interval"):
            a, b = (r.get("first"), r.get("then")) if kind == "date_order" else (r.get("from"), r.get("to"))
            bad += [f"rule '{rid}': '{x}' is not a date" for x in (a, b) if x and self.knows(x) and not is_type(x, "date")]
            if kind == "date_interval" and not _is_number(r.get("max_days"), whole=True):
                bad.append(f"rule '{rid}': max_days must be a whole number of days, zero or more")
        if kind in ("amount_limit", "amounts_match"):
            refs = [r.get("amount"), r.get("limit")] if kind == "amount_limit" else list(r.get("amounts") or [])
            bad += [f"rule '{rid}': '{x}' is not an amount" for x in refs if x and self.knows(x) and not is_type(x, "money", "number")]
            if kind == "amounts_match" and len(refs) < 2:
                bad.append(f"rule '{rid}': name at least two amounts to compare")
            if r.get("tolerance_pct") not in (None, "") and not _is_number(r.get("tolerance_pct")):
                bad.append(f"rule '{rid}': the tolerance is a percentage, zero or more")
        if kind == "value_limit":
            if r.get("field") and self.knows(r["field"]) and not is_type(r["field"], "money", "number"):
                bad.append(f"rule '{rid}': '{r['field']}' is not an amount or a number")
            if r.get("max") in (None, "") and r.get("min") in (None, ""):
                bad.append(f"rule '{rid}': give a most, a least, or both")
            bad += [f"rule '{rid}': {k} must be a number" for k in ("max", "min") if r.get(k) not in (None, "") and not _is_number(r.get(k))]
        if kind == "value_in" and (not isinstance(r.get("values"), list) or not all(str(v).strip() for v in r.get("values") or [])):
            bad.append(f"rule '{rid}': give the values as a list")
        when = r.get("applies_when")
        if when is not None and (not isinstance(when, dict) or not self.knows(when.get("ref") or "") or not (when.get("is") or when.get("in") or when.get("not_in"))
                                 or any(not isinstance(when.get(k) or [], list) for k in ("in", "not_in"))):
            bad.append(f"rule '{rid}': 'applies when' names a known field and the value or values it must have (is, in) or must not have (not_in)")
        return bad

    def field_name(self, ref: str) -> str:
        head, _, fld = ref.partition(".")
        if head == "record":
            sid, _, name = fld.partition(".")
            spec = next((s for s in self.systems if s["id"] == sid), None) or {}
            f = next((x for x in spec.get("fields") or [] if x["id"] == name), None) or {}
            return f"{spec.get('name') or sid} · {f.get('name') or name.replace('_', ' ')}"
        if head == "case":
            for f in self.case.get("fields") or []:
                if f["id"] == fld:
                    return f.get("name") or fld
            return fld.replace("_", " ")
        f = self.field(head, fld)
        return f"{self.type_name(head)} · {(f or {}).get('name') or fld}"

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "version": self.version, "description": self.description, "brand": self.brand, "sector": self.sector, "plain": self.plain,
                "memory": self.memory, "service": self.service, "assurance": self._assurance(), "consistency": [{"id": r["id"], "title": r.get("title"), "kind": r.get("kind")} for r in self.consistency],
                "case": self.case, "document_types": [{"id": t["id"], "name": t.get("name") or t["id"], "group": t.get("group") or "",
                                                       "fields": [{"id": f["id"], "name": f.get("name") or f["id"], "type": f.get("type", "text"),
                                                                   "required": bool(f.get("required"))} for f in t.get("fields") or []]}
                                                      for t in self.types.values()],
                "evidence": self.evidence, "outcomes": self.outcomes, "ontology": self.ontology,
                "rules": [{"id": r["id"], "title": r.get("title"), "family": r.get("family"), "version": r.get("version"), "type": r.get("type")} for r in self.rules],
                "counterfactuals": [{"id": c["id"], "title": c.get("title"), "expect": c.get("expect"), "ask": c.get("ask"),
                                     "value": (c.get("change") or {}).get("value") if c.get("ask") else None} for c in self.counterfactuals],
                "samples": [{"id": s["id"], "title": s.get("title"), "path": s.get("path"), "story": s.get("story")} for s in self.samples],
                "reference_sources": [{"id": r["id"], "name": r.get("name"), "connector": r.get("connector")} for r in self.references]}

    def _assurance(self) -> list[dict[str, Any]]:
        from . import assurance

        return [{"key": r["key"], "title": r["title"], "kind": r["kind"], "family": r["family"]} for r in assurance.declared_rules(self)]


# What a rule of each kind must state. Every kind is a fixed calculation in checks.policy: a rule is a choice of kind, fields and limits, never code.
RULE_TYPES = {"date_order": ("first", "then"), "date_interval": ("from", "to", "max_days"), "amount_limit": ("amount", "limit"), "amounts_match": ("amounts",),
              "codes_consistent": ("codes",), "value_in": ("field", "values"), "value_limit": ("field",), "required_field": ("field",)}


def _is_number(v: Any, whole: bool = False) -> bool:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return False
    return n == n and 0 <= n < 1e15 and (not whole or n == int(n))


def _refs_of(rule: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("from", "to", "first", "then", "amount", "limit", "field"):
        v = rule.get(key)
        if isinstance(v, str) and "." in v and " " not in v:
            out.append(v)
    for key in ("fields", "amounts", "codes"):
        out += [v for v in rule.get(key) or [] if isinstance(v, str) and "." in v]
    return out


def profile_dirs() -> list[Path]:
    extra = [Path(p) for p in (os.environ.get("DOCUINSIGHTS_PROFILES_DIR") or "").split(os.pathsep) if p.strip()]
    return [HERE / "profiles", *extra]


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, Profile]:
    found: dict[str, Profile] = {}
    for folder in profile_dirs():
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not raw.get("id"):
                raise ProfileError(f"{path.name}: a profile needs an id")
            found[raw["id"]] = Profile(raw, path)
    if not found:
        raise ProfileError("no profiles found")
    return dict(sorted(found.items(), key=lambda kv: (kv[1].order, kv[1].name)))


def get_profile(profile_id: str | None) -> Profile:
    profiles = load_profiles()
    if not profile_id:
        return next(iter(profiles.values()))
    if profile_id not in profiles:
        raise ProfileError(f"unknown profile '{profile_id}'; the profiles are: {', '.join(profiles)}")
    return profiles[profile_id]


def reset_profiles() -> None:
    load_profiles.cache_clear()
