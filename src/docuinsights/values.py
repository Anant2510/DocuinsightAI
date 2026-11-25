"""Typed values: every extracted field is normalised by its declared type so rules compare like with like."""
from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
CURRENCY_SIGNS = {"£": "GBP", "$": "USD", "€": "EUR", "₹": "INR"}
LEGAL = {"ltd", "limited", "gmbh", "inc", "incorporated", "llc", "plc", "co", "company", "corp", "corporation", "sa", "ag", "bv", "pvt", "private", "pte", "srl", "spa", "the"}
STOP = {"the", "and", "for", "with", "of", "in", "to", "a", "an", "per", "no", "nos", "pcs", "pieces", "type", "row", "said", "contain", "containing", "cartons", "carton"}


def parse_date(text: Any) -> str | None:
    """An ISO date from the forms documents use: 2026-11-03, 03/11/2026 (day first), 3 Nov 2026, November 3, 2026."""
    if isinstance(text, (date, datetime)):
        return text.isoformat()[:10]
    s = str(text or "").strip()
    if not s:
        return None
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", s)
    if m:
        return _iso(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s-]+([A-Za-z]{3,9})\.?,?[\s-]+(\d{4})\b", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        return _iso(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        return _iso(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    return None


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_number(text: Any) -> float | None:
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    m = re.search(r"-?\d[\d,\s]*(?:\.\d+)?", str(text or ""))
    if not m:
        return None
    try:
        return float(re.sub(r"[,\s]", "", m.group(0)))
    except ValueError:
        return None


def parse_money(text: Any) -> dict[str, Any] | None:
    """{'amount': 15420.0, 'currency': 'GBP'} from 'GBP 15,420.00', '£15,420.00' or '15420.00 GBP'."""
    if isinstance(text, dict) and "amount" in text:
        return {"amount": float(text["amount"]), "currency": str(text.get("currency") or "")}
    s = str(text or "")
    amount = parse_number(s)
    if amount is None:
        return None
    cur = ""
    m = re.search(r"\b([A-Z]{3})\b", s)
    if m:
        cur = m.group(1)
    else:
        for sign, code in CURRENCY_SIGNS.items():
            if sign in s:
                cur = code
    return {"amount": amount, "currency": cur}


def parse_code(text: Any) -> str | None:
    digits = re.sub(r"\D", "", str(text or ""))
    return digits or None


def normalise(value: Any, ftype: str) -> Any:
    if value in (None, ""):
        return None
    if ftype == "date":
        return parse_date(value)
    if ftype == "number":
        return parse_number(value)
    if ftype == "money":
        return parse_money(value)
    if ftype == "code":
        return parse_code(value)
    return re.sub(r"\s+", " ", str(value)).strip() or None


def display(norm: Any, ftype: str = "text") -> str:
    if norm is None:
        return ""
    if isinstance(norm, dict) and "amount" in norm:
        return f"{norm.get('currency') or ''} {norm['amount']:,.2f}".strip()
    if isinstance(norm, float):
        return f"{norm:,.0f}" if norm == int(norm) else f"{norm:,.2f}".rstrip("0").rstrip(".")
    if ftype == "code" and str(norm).isdigit() and len(str(norm)) == 10:
        c = str(norm)
        return f"{c[:4]} {c[4:6]} {c[6:8]} {c[8:]}"
    return str(norm)


def party_name(value: Any) -> str:
    """The name part of 'Name, street, city, country'."""
    return str(value or "").split(",")[0].strip()


def party_key(value: Any) -> str:
    words = re.findall(r"[a-z0-9]+", party_name(value).lower())
    return " ".join(w for w in words if w not in LEGAL)


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def tokens(text: Any) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9][a-z0-9-]*", str(text or "").lower()):
        w = w.strip("-")
        if len(w) >= 3 and w not in STOP:
            out.add(w[:-1] if w.isalpha() and w.endswith("s") and len(w) > 4 else w)
    return out


def overlap(a: Any, b: Any) -> float:
    """Share of the smaller description's words found in the other (0..1)."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def ref_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def truthy(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() in ("yes", "y", "true", "1", "on")
