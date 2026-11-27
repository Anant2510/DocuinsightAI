"""Systems of record: what the business already knows about a case, asked for by key.

A document says a policy is in force; the policy administration system knows whether it is. A use case names the systems
it checks against (`systems:` in its profile): what to look a record up by, and the fields a record carries. A rule can
then use `record.<system>.<field>` wherever it uses `<document>.<field>`, so "the loss falls inside the cover" can be
answered from the record as well as from the schedule the claimant sent.

One contract, whatever stands behind it:

    lookup(system, key) -> {"status": "found" | "not_found" | "unavailable" | "not_configured", "record": {...}, "source": {...}}

Connectors, chosen per system by the installation (settings are DOCUINSIGHTS_SYSTEM_<ID>_<NAME>, <ID> in upper case):

    synthetic   the demonstration records shipped with this build (policy administration for the United States and India):
                the default for a system that ships with one, and always labelled as demonstration.
                DOCUINSIGHTS_SYNTHETIC_SYSTEMS=0 switches them off: a system with no connector of its own then says so.
    http        your own system, over REST, by settings alone:
                    URL         https://host/policies/{key}       ({key} is the value looked up, URL-encoded)
                    TOKEN       sent as "Authorization: Bearer <token>"                               (optional)
                    HEADERS     JSON of further headers                                                (optional)
                    METHOD      GET (default) or POST
                    BODY        for POST: the JSON to send; {key} inside any text of it is the value looked up
                    RECORD      where the record sits in the answer (data.policy); a list there is read as its first row,
                                and an empty list as "not found"                                       (optional)
                    NOT_FOUND   the answer that means "no such record" when the system says it with a 200:
                                path=value|value   (status.code=NOT_FOUND|E404)                        (optional)
                    OK          the answer that means "this is a good answer": path=value|value. Given, any other
                                answer is "unavailable" and its value is the reason                    (optional)
                    MAP         JSON: {"<field>": "path.in.the.record"} where your record names things differently;
                                a field not mapped is read by its own name                             (optional)
                    TIMEOUT_S   seconds to wait (default 10)
                A 404 is "not found". Anything else that is not a 2xx JSON object is "unavailable", and is never read as "not found".
    adapter     your own code, where settings are not enough (a session to open, two calls to join, SOAP, a database):
                    ADAPTER     package.module:function
                The function is called as function(system, key, settings) and returns
                    {"status": "found" | "not_found" | "unavailable", "record": {...}, "reason": "..."}
                `settings` holds every DOCUINSIGHTS_SYSTEM_<ID>_* value by its lower-case name. Whatever it raises is
                "unavailable". `docuinsights.adapters.newgen_rest` is a reference adapter to copy.

A record that cannot be fetched is said to be unavailable and the rules that need it go to a person: a system that did not
answer is never read as a record that does not exist. Every lookup is timed and written to the provenance ledger.
"""
from __future__ import annotations

import importlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import net

HERE = Path(__file__).parent
SYNTHETIC = {"policy_admin": HERE / "reference" / "policy_admin.json"}


@lru_cache(maxsize=8)
def _synthetic(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def key_of(value: Any) -> str:
    """A key as systems compare it: letters and digits only, upper case (PA-IN-2201987 and "pa in 2201987" are one policy)."""
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _env(system_id: str, name: str, env: dict[str, str]) -> str:
    return (env.get(f"DOCUINSIGHTS_SYSTEM_{system_id.upper()}_{name}") or "").strip()


SETTINGS = ("URL", "TOKEN", "HEADERS", "METHOD", "BODY", "RECORD", "NOT_FOUND", "OK", "MAP", "TIMEOUT_S", "ADAPTER")
SECRET = ("TOKEN", "HEADERS", "PASSWORD", "SECRET", "KEY")   # settings whose values are never shown, logged or returned


def settings_of(system_id: str, env: dict[str, str] | None = None) -> dict[str, str]:
    """Every setting of one system, by its lower-case name (DOCUINSIGHTS_SYSTEM_POLICY_ADMIN_URL -> "url"): what an adapter is handed."""
    env = env if env is not None else dict(os.environ)
    head = f"DOCUINSIGHTS_SYSTEM_{system_id.upper()}_"
    return {k[len(head):].lower(): str(v).strip() for k, v in env.items() if k.startswith(head) and str(v).strip()}


def connector_of(system: dict[str, Any], env: dict[str, str] | None = None) -> dict[str, Any]:
    """How this installation reaches the system: {"kind": "adapter" | "http" | "synthetic" | "none", ...}. Nothing secret is returned."""
    env = env if env is not None else dict(os.environ)
    sid = system["id"]
    url = _env(sid, "URL", env)
    if _env(sid, "ADAPTER", env):
        has = settings_of(sid, env)
        return {"kind": "adapter", "name": system.get("name") or sid, "target": _env(sid, "ADAPTER", env).split(":")[0][:80] + (" → " + urllib.parse.urlsplit(url).netloc if url else ""),
                "authenticated": any(k.upper() in SECRET or k.upper().endswith(SECRET) for k in has), "demonstration": False}
    if url:
        host = urllib.parse.urlsplit(url).netloc or url[:40]
        return {"kind": "http", "name": system.get("name") or sid, "target": host, "authenticated": bool(_env(sid, "TOKEN", env) or _env(sid, "HEADERS", env)), "demonstration": False}
    source = system.get("synthetic") or sid
    if source in SYNTHETIC and (env.get("DOCUINSIGHTS_SYNTHETIC_SYSTEMS") or "1").strip().lower() not in ("0", "false", "no", "off"):
        data = _synthetic(str(SYNTHETIC[source]))
        return {"kind": "synthetic", "name": data.get("name") or sid, "target": "bundled demonstration records", "authenticated": False, "demonstration": True,
                "records": len(data.get("records") or {}), "regions": data.get("regions") or {}, "note": data.get("note") or "",
                "by_region": {name: sum(1 for r in (data.get("records") or {}).values() if r.get("region") == code) for code, name in (data.get("regions") or {}).items()}}
    return {"kind": "none", "name": system.get("name") or sid, "target": "", "authenticated": False, "demonstration": False}


def _dig(data: Any, path: str) -> Any:
    for part in str(path).split("."):
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        else:
            return None
    return data


def lookup(system: dict[str, Any], key: Any, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Ask the system for the record under `key`. Never raises: what went wrong is the answer's status and reason."""
    env = env if env is not None else dict(os.environ)
    sid, t0 = system["id"], time.perf_counter()
    how = connector_of(system, env)
    out: dict[str, Any] = {"system": sid, "name": system.get("name") or sid, "key": str(key or ""), "connector": how["kind"], "demonstration": how["demonstration"], "record": {}, "reason": ""}

    def done(status: str, reason: str = "", record: dict[str, Any] | None = None) -> dict[str, Any]:
        out.update(status=status, reason=reason, record=record or {}, ms=round((time.perf_counter() - t0) * 1000, 1))
        return out

    if not key_of(key):
        return done("not_asked", "there is nothing to look it up by")
    if how["kind"] == "none":
        return done("not_configured", f"no connector is configured for {out['name']}")
    wanted = [f["id"] for f in system.get("fields") or []]
    if how["kind"] == "synthetic":
        rows = _synthetic(str(SYNTHETIC[system.get("synthetic") or sid])).get("records") or {}
        hit = next((row for k, row in rows.items() if key_of(k) == key_of(key)), None)
        return done("found", record={k: hit.get(k) for k in (wanted or hit) if hit.get(k) is not None}) if hit else done("not_found", f"{out['name']} holds no record under {key}")
    if how["kind"] == "adapter":
        return done(*_adapted(system, key, env, out["name"]))
    url = _env(sid, "URL", env).replace("{key}", urllib.parse.quote(str(key).strip(), safe=""))
    headers = {"Accept": "application/json", "User-Agent": "DocuInsights"}
    method = (_env(sid, "METHOD", env) or "GET").upper()
    data = None
    try:
        headers.update({str(k): str(v) for k, v in (json.loads(_env(sid, "HEADERS", env) or "{}") or {}).items()})
        mapping = json.loads(_env(sid, "MAP", env) or "{}") or {}
        timeout = float(_env(sid, "TIMEOUT_S", env) or 10)
        if method == "POST":
            data = json.dumps(_fill(json.loads(_env(sid, "BODY", env) or "{}"), str(key).strip())).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        if not isinstance(mapping, dict):
            raise ValueError("MAP")
    except (ValueError, TypeError, AttributeError):
        return done("unavailable", f"the connector settings for {out['name']} are not valid JSON")
    if method not in ("GET", "POST"):
        return done("unavailable", f"the connector for {out['name']} is set to {method[:12]}: it reads with GET or POST")
    if _env(sid, "TOKEN", env):
        headers["Authorization"] = "Bearer " + _env(sid, "TOKEN", env)
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        return done("unavailable", f"the address configured for {out['name']} is not an http(s) address")
    try:
        with net.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=timeout) as resp:   # the scheme is checked above
            body = json.loads(resp.read(2_000_000).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return done("not_found", f"{out['name']} holds no record under {key}") if exc.code == 404 else done("unavailable", f"{out['name']} answered {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return done("unavailable", f"{out['name']} could not be reached ({type(exc).__name__})")
    except ValueError:
        return done("unavailable", f"{out['name']} did not answer with JSON")
    return done(*read_answer(body, name=out["name"], key=key, wanted=wanted, mapping=mapping, record=_env(sid, "RECORD", env), not_found=_env(sid, "NOT_FOUND", env), ok=_env(sid, "OK", env)))


def _fill(template: Any, key: str) -> Any:
    """The request to send: {key} inside any text of the template becomes the value looked up (as data, never as markup)."""
    if isinstance(template, str):
        return template.replace("{key}", key)
    if isinstance(template, dict):
        return {k: _fill(v, key) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, key) for v in template]
    return template


def _says(body: Any, rule: str) -> tuple[bool, str]:
    """`path=value|value` against an answer: (does it hold, what the answer has at that path)."""
    path, _, values = rule.partition("=")
    got = _dig(body, path.strip())
    text = "" if got is None else str(got).strip()
    return text.lower() in [v.strip().lower() for v in values.split("|")], text


def read_answer(body: Any, *, name: str, key: Any, wanted: list[str], mapping: dict[str, Any] | None = None, record: str = "", not_found: str = "", ok: str = "") -> tuple[str, str, dict[str, Any]]:
    """What a system's answer means: (status, reason, record). Shared by the http connector and by adapters, so that every connector tells
    "no such record" from "no answer" the same way."""
    if not isinstance(body, (dict, list)):
        return "unavailable", f"{name} did not answer with a record", {}
    if not_found and _says(body, not_found)[0]:
        return "not_found", f"{name} holds no record under {key}", {}
    if ok:
        good, said = _says(body, ok)
        if not good:
            return "unavailable", f"{name} answered {ok.partition('=')[0].strip()}: {said[:80] or 'nothing'}", {}
    row = _dig(body, record) if record else body
    if isinstance(row, list):
        if not row:
            return ("not_found", f"{name} holds no record under {key}", {}) if record else ("unavailable", f"{name} did not answer with a record", {})
        row = row[0]
    if not isinstance(row, dict):
        return "unavailable", f"{name} answered, but with no record where one was expected" + (f" ({record})" if record else ""), {}
    mapping = mapping or {}
    got = {f: _dig(row, str(mapping.get(f) or f)) for f in wanted} if wanted else dict(row)
    got = {k: v for k, v in got.items() if v is not None and not isinstance(v, (dict, list)) and str(v).strip() != ""}
    return ("found", "", got) if got else ("unavailable", f"{name} answered, but with none of the fields this use case reads", {})


def _adapted(system: dict[str, Any], key: Any, env: dict[str, str], name: str) -> tuple[str, str, dict[str, Any]]:
    """An installation's own adapter, held to the contract: one of three answers, a flat record, and never an exception."""
    sid = system["id"]
    spec = _env(sid, "ADAPTER", env)
    module, _, func = spec.partition(":")
    try:
        fn = getattr(importlib.import_module(module.strip()), (func or "lookup").strip())
    except Exception as exc:   # noqa: BLE001 (a module that is not there, or fails as it loads)
        return "unavailable", f"the adapter for {name} could not be loaded ({type(exc).__name__})", {}
    try:
        ans = fn(system, str(key).strip(), settings_of(sid, env))
    except Exception as exc:   # noqa: BLE001 (whatever an adapter raises, the system did not answer)
        return "unavailable", f"the adapter for {name} failed ({type(exc).__name__})", {}
    if not isinstance(ans, dict) or ans.get("status") not in ("found", "not_found", "unavailable"):
        return "unavailable", f"the adapter for {name} returned something that is not an answer", {}
    wanted = [f["id"] for f in system.get("fields") or []]
    rec = ans.get("record") if isinstance(ans.get("record"), dict) else {}
    rec = {k: v for k, v in rec.items() if (not wanted or k in wanted) and v is not None and not isinstance(v, (dict, list)) and str(v).strip() != ""}
    if ans["status"] == "found" and not rec:
        return "unavailable", f"{name} answered, but with none of the fields this use case reads", {}
    reason = str(ans.get("reason") or "")[:200] or (f"{name} holds no record under {key}" if ans["status"] == "not_found" else f"{name} did not answer" if ans["status"] == "unavailable" else "")
    return ans["status"], reason, rec if ans["status"] == "found" else {}


__all__ = ["lookup", "connector_of", "key_of", "read_answer", "settings_of", "SETTINGS", "SYNTHETIC"]
