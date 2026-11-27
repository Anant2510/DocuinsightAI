"""A reference adapter in the REST style of NewgenONE's web services.

The style (as the OmniDocs REST developer guide writes its calls, and as `docuinsights.repository` uses it to file documents):
every call is a POST of ONE named request object, which carries the cabinet and the caller's credentials beside what is
asked for; the answer is ONE named response object, which carries its own status ("0" is success) and a message.

    POST https://<server>:<port>/<service>/rest/services/<operation>
    {"<REQUEST>": {"cabinetName": "...", "userName": "...", "userPassword": "...", "<KEY_FIELD>": "<the key>", ...}}

    {"<RESPONSE>": {"status": "0", "message": "...", "<RECORD>": {...the record...}}}

Settings (DOCUINSIGHTS_SYSTEM_<ID>_<NAME>):

    ADAPTER       docuinsights.adapters.newgen_rest:lookup
    URL           the full address of the operation that returns the record
    REQUEST       the name of the request object, as your service documents it
    RESPONSE      the name of the response object (without it, the answer itself is read)
    KEY_FIELD     the field of the request that carries the key (default: key)
    CABINET, USER, PASSWORD    sent as cabinetName, userName, userPassword
    EXTRA         JSON of further fields of the request object                          (optional)
    RECORD        where the record sits inside the response object                      (optional: the response object itself)
    NOT_FOUND     the status values that mean "no such record", separated by commas     (your service's own codes)
    MAP           JSON {"<field>": "name.in.the.record"} where the record names things differently
    TIMEOUT_S     seconds to wait (default 15)

This is a pattern to copy, NOT a tested integration. Which operation returns a policy, a customer or an account is a
service of the installation (a data class search, a process variable, a service built for the purpose), so the names of
the operation, of its objects and of its fields are settings here and no name is assumed. It has not been run against a
live NewgenONE system. The tests run it against a stand-in that answers in this style, which proves the adapter contract
and the handling of each answer, and nothing about any one service.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .. import net
from ..systems import read_answer


def lookup(system: dict[str, Any], key: str, settings: dict[str, str]) -> dict[str, Any]:
    name = system.get("name") or system["id"]

    def answer(status: str, reason: str = "", record: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"status": status, "reason": reason, "record": record or {}}

    url, request = settings.get("url") or "", settings.get("request") or ""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https") or not request:
        return answer("unavailable", f"the adapter for {name} needs URL (an http(s) address) and REQUEST (the name of the request object)")
    try:
        extra = json.loads(settings.get("extra") or "{}")
        mapping = json.loads(settings.get("map") or "{}")
        timeout = float(settings.get("timeout_s") or 15)
        if not isinstance(extra, dict) or not isinstance(mapping, dict):
            raise ValueError("not an object")
    except (ValueError, TypeError):
        return answer("unavailable", f"the adapter settings for {name} are not valid JSON")
    body = {request: {"cabinetName": settings.get("cabinet") or "", "userName": settings.get("user") or "", "userPassword": settings.get("password") or "",
                      **extra, settings.get("key_field") or "key": key}}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "DocuInsights"})
    try:
        with net.urlopen(req, timeout=timeout) as resp:
            got = json.loads(resp.read(2_000_000).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return answer("unavailable", f"{name} answered {exc.code}")   # in this style a missing record is a status inside a 200, so no HTTP code is read as "not found"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return answer("unavailable", f"{name} could not be reached ({type(exc).__name__})")
    except ValueError:
        return answer("unavailable", f"{name} did not answer with JSON")
    out = got.get(settings["response"]) if isinstance(got, dict) and settings.get("response") else got
    if not isinstance(out, dict):
        return answer("unavailable", f"{name} did not answer with the response object this adapter is set to read")
    status = str(out.get("status", out.get("statusCode", ""))).strip()
    if status in [c.strip() for c in (settings.get("not_found") or "").split(",") if c.strip()]:
        return answer("not_found", f"{name} holds no record under {key}")
    if status != "0":
        return answer("unavailable", f"{name} answered status {status[:20] or 'nothing'}" + (f": {str(out.get('message'))[:120]}" if out.get("message") else ""))
    return answer(*read_answer(out, name=name, key=key, wanted=[f["id"] for f in system.get("fields") or []], mapping=mapping, record=settings.get("record") or ""))
