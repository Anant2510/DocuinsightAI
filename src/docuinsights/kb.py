"""The knowledge base: one knowledge graph per workspace that grows with every case.

It is kept in the layout of a KB Forge knowledge base (schema 1.0), so the same folder opens there:

    graph/entities.jsonl      id, type, name, props, synonyms, sourceModules, confidence, stub
    graph/triples.jsonl       subject, predicate, object, props, sourceModule, confidence
    graph/index.json          counts per class and per relationship
    graph/provenance.json     documents, citations, what supports every entity and link, the last verification
    graph/verification.json   which provenance was checked, and what the check found
    ontology/…                the ontology the graph is typed with
    quality/metrics.json      the quality score and its components
    manifest.json             what this is, when it was built, every file with its SHA-256

The graph is never edited in place. It is REBUILT from its sources, so nothing is lost and nothing is double counted:

    the use-case profiles     what each use case asks for: document kinds, evidence, rules, references
    every assessed case       its documents, the parties, goods and reference numbers they name, and the findings
    imported knowledge        a KB Forge knowledge base, or any graph of nodes and edges, added as it is

Every entity and link carries what supports it (a document line, a case record, a profile declaration, a retrieved
reference, an import), and every build checks the document citations against the text they cite, with no model.

The graph has KB Forge's four levels of knowledge, top to bottom:

    industry    the kinds of organisation the use cases serve
    domain      what each use case asks for: its kinds of document, its evidence, its rules, its references
    solution    the accelerator and its agents, each under its contract (KB Forge's "Coforge experience" level)
    customer    the workspace: the organisations and goods met across cases, and each case with what it holds

An added knowledge base sits at the level it was built for in KB Forge (or the level chosen when it is added).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import threading
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import __version__, ontology as O
from .casefile import current, doc_type, live_docs, now
from .profiles import Profile

SCHEMA = "1.0"
MAX_IMPORT = 60_000
DOMAIN = "Document and case intelligence"   # the experience domain every use case of this accelerator belongs to
ACCELERATOR = "DocuInsights"
BUILD = 3   # the shape a build writes. 3: KB Forge's four levels in its own level ids, and the company at the head of the cases
LEVEL_ORDER = ("industry", "domain", "solution", "customer")
ORIGIN_WORDS = {"document": "read in a document", "system": "from the case record", "settings": "declared by a use case", "web": "from a retrieved reference",
                "imported": "imported knowledge", "inferred": "worked out from other links", "decision": "decided by a person", "unverified": "cited but not found in the text",
                "unknown": "no source recorded"}
_locks: dict[str, threading.RLock] = {}
_guard = threading.Lock()


def _hash(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _conf(value: Any) -> float | None:
    """A confidence as a number. KB Forge also writes it as a word: high 0.9, medium 0.65, low 0.35."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    word = {"high": 0.9, "medium": 0.65, "low": 0.35}.get(str(value).strip().lower())
    if word is not None:
        return word
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _squash(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


# ------------------------------------------------------------------------------------------------ what one source contributes
class Contribution:
    """Entities and links from one source, each with what supports it. Ids are final except organisations, which the
    build joins across sources by their name key."""

    def __init__(self, kind: str, sid: str, label: str, at: str = ""):
        self.source = {"kind": kind, "id": sid, "label": label, "at": at}
        self.entities: dict[str, dict[str, Any]] = {}
        self.triples: list[dict[str, Any]] = []
        self.documents: list[dict[str, Any]] = []
        self.texts: dict[str, list[str]] = {}

    def entity(self, type_: str, name: Any, *, description: str = "", props: dict[str, Any] | None = None, synonyms: list[str] | None = None, key: str | None = None,
               support: list[dict[str, Any]] | None = None, confidence: float | None = None, eid: str | None = None, stub: bool = False) -> str:
        name = " ".join(str(name).split())[:160] or "unnamed"
        eid = eid or O.entity_id(type_, name)
        e = self.entities.setdefault(eid, {"id": eid, "type": type_, "name": name, "props": {}, "synonyms": [], "support": [], "confidence": _conf(confidence), "key": key, "stub": stub})
        if description and not e["props"].get("description"):
            e["props"]["description"] = description
        for k, v in (props or {}).items():
            if v not in (None, "", [], {}):
                e["props"][k] = v
        e["synonyms"] += [s for s in synonyms or [] if s and s != e["name"] and s not in e["synonyms"]]
        e["support"] += support or []
        if not stub:
            e["stub"] = False
        return eid

    def triple(self, s: str, p: str, o: str, *, props: dict[str, Any] | None = None, support: list[dict[str, Any]] | None = None, confidence: float | None = None) -> None:
        if s and o and s != o:
            self.triples.append({"s": s, "p": p, "o": o, "props": {k: v for k, v in (props or {}).items() if v not in (None, "", [], {})}, "support": support or [], "confidence": _conf(confidence)})

    def data(self) -> dict[str, Any]:
        return {"source": self.source, "entities": list(self.entities.values()), "triples": self.triples, "documents": self.documents, "texts": self.texts}


def foundation_contribution(profiles: list[Profile]) -> dict[str, Any]:
    """The domain, the accelerator and its agents with their contracts: the solution level, and the head of the domain level."""
    from . import contracts as C, pipeline as P

    c = Contribution("foundation", "docuinsights", f"{ACCELERATOR} {__version__}")
    version = C.get("orchestrator")["version"]

    def said(locator: str, text: str) -> list[dict[str, Any]]:
        return [{"citation": {"kind": "profile", "source": f"agent contracts v{version}", "locator": locator, "text": text}, "section": "contracts", "how": "declared"}]

    dom = c.entity("ExperienceDomain", DOMAIN, description="Reading a set of documents, linking what they say, checking them against rules and handing a person a recommendation with the line behind every conclusion.",
                   support=said("domain", DOMAIN))
    acc = c.entity("Accelerator", ACCELERATOR, description="An agentic accelerator for document and case intelligence: one engine, a use case per configuration file, every agent under a contract.",
                   props={"assetType": "accelerator", "version": __version__}, support=said("accelerator", ACCELERATOR))
    c.triple(acc, "acceleratorForDomain", dom, support=said("accelerator", f"{ACCELERATOR} serves {DOMAIN}"))
    for p in profiles:
        c.triple(acc, "acceleratorSupportsUseCase", c.entity("UseCase", p.name), support=said(f"profile.{p.id}", f"{ACCELERATOR} assesses {p.name}"))
    for a in P.AGENTS:
        ct = C.get(a["id"])
        ag = c.entity("SoftwareAgent", a["name"], description=ct["purpose"], support=said(f"contracts.{a['id']}", a["name"]),
                      props={"agentId": a["id"], "stage": a.get("stage") or "on demand", "needs": [n.replace("_", " ") for n in ct["needs"]], "promises": [x["text"] for x in ct["promises"]], "never": ct["never"],
                             "modelUse": "none (code only)" if (ct["model"].get("use") or "none") == "none" else f"optional, up to {ct['model'].get('max_calls')} call(s) a run", "onFailure": ct["on_failure"],
                             "contractVersion": ct["version"]})
        c.triple(acc, "acceleratorHasAgent", ag, support=said(f"contracts.{a['id']}", f"{a['name']} is one of {ACCELERATOR}'s agents"))
    return c.data()


def profile_contribution(profile: Profile) -> dict[str, Any]:
    """What a use case declares: the domain level of the graph, and the industry it serves."""
    c = Contribution("profile", profile.id, f"{profile.name} v{profile.version}")

    def said(locator: str, text: str) -> list[dict[str, Any]]:
        return [{"citation": {"kind": "profile", "source": f"use-case profile {profile.id} v{profile.version}", "locator": locator, "text": text}, "section": "profile", "how": "declared"}]

    uc = c.entity("UseCase", profile.name, description=profile.description, props={"profileId": profile.id, "profileVersion": profile.version, "caseNoun": profile.brand.get("case_noun")},
                  support=said("id", f"use case '{profile.name}'"))
    dom = c.entity("ExperienceDomain", DOMAIN)
    c.triple(dom, "domainCoversUseCase", uc, support=said("id", f"{profile.name} is a use case of {DOMAIN}"))
    if profile.sector:
        ind = c.entity("IndustrySegment", profile.sector, description=f"Organisations in {profile.sector.lower()}: who runs '{profile.name}'.", support=said("sector", profile.sector))
        c.triple(uc, "useCaseServesIndustry", ind, support=said("sector", f"{profile.name} is run in {profile.sector}"))
        c.triple(dom, "domainRelevantToIndustry", ind, support=said("sector", f"{DOMAIN} is applied in {profile.sector}"))
    need: dict[str, dict[str, Any]] = {}
    for ev in profile.evidence:
        kind = "mandatory" if ev.get("required") == "always" else "conditional"
        for tid in ev.get("any_of") or []:
            need[tid] = {"requirement": "one of several" if len(ev["any_of"]) > 1 else kind, "requirementGroup": ev.get("title"), "condition": ev.get("note") or ev.get("when")}
    kinds: dict[str, str] = {}
    for t in profile.types.values():
        name = t.get("name") or t["id"]
        fields = [f.get("name") or f["id"] for f in t.get("fields") or []]
        kinds[t["id"]] = c.entity("Document", name, description=t.get("description") or f"{name}. Read for: {', '.join(fields[:8])}.",
                                  props={"documentGroup": t.get("group"), "keyFields": fields, "recognisedBy": list(t.get("signals") or [])[:8]}, support=said(f"document_types.{t['id']}", name))
        c.triple(uc, "processUsesDocument", kinds[t["id"]], props=need.get(t["id"]) or {"requirement": "optional"}, support=said(f"evidence.{t['id']}", f"{profile.name} works with {name}"))
    for role in sorted({str(r) for r in (profile.entities.get("parties") or {}).values()}):
        c.triple(c.entity("Role", role, description=f"The {role.lower()} named in the documents of a case.", support=said("entities.parties", role)), "participatesInProcess", uc,
                 support=said("entities.parties", f"{role} takes part in {profile.name}"))

    def rule(title: str, kind: str, family: str, version: str, note: str, params: list[str], types: set[str], locator: str) -> None:
        r = c.entity("PolicyRule", title, description=(note or f"{title}.") + f" Executed in code ({kind}), never by a model.",
                     props={"ruleKind": kind, "ruleFamily": family, "ruleVersion": str(version), "parameters": params}, support=said(locator, title))
        c.triple(uc, "governedByRegulation", r, support=said(locator, f"{profile.name} applies '{title}'"))
        for tid in sorted(types & set(kinds)):
            c.triple(r, "requiresDocument", kinds[tid], support=said(locator, f"'{title}' reads {profile.type_name(tid)}"))

    for ev in profile.evidence:
        rule(f"{ev['title']} " + ("is required" if ev.get("required") == "always" else "is required when it applies"), "evidence", "evidence", profile.version, ev.get("note") or "",
             [f"required={ev.get('required')}"], set(ev.get("any_of") or []), f"evidence.{ev['id']}")
    from .profiles import _refs_of

    for group, label in ((profile.rules, "rules"), (profile.consistency, "consistency")):
        for r in group:
            params = [f"{k}={r[k]}" for k in ("max_days", "min_days", "tolerance_pct", "tolerance") if r.get(k) is not None]
            rule(r.get("title") or r["id"], r.get("type") or f"consistency ({r.get('kind', 'text')})", r.get("family") or label, r.get("version") or profile.version, r.get("note") or "",
                 params, {ref.partition(".")[0] for ref in _refs_of(r)}, f"{label}.{r['id']}")
    for ref in profile.references:
        c.triple(uc, "usesReferenceSource", c.entity("ReferenceSource", ref.get("name") or ref["id"], description=ref.get("description") or f"Reference read for the date of the {profile.brand.get('case_noun', 'case')}.",
                                                     props={"connector": ref.get("connector")}, support=said(f"reference_sources.{ref['id']}", ref.get("name") or ref["id"])),
                 support=said(f"reference_sources.{ref['id']}", f"{profile.name} reads {ref.get('name') or ref['id']}"))
    return c.data()


def case_contribution(case: dict[str, Any], profile: Profile, owner: str = "This workspace") -> dict[str, Any] | None:
    """What one assessed case adds to the customer level: the case and what it holds, and the parties and goods it met."""
    a = case.get("assessment")
    if not a:
        return None
    ref = case["reference"]
    c = Contribution("case", ref, ref, a.get("at") or "")
    record = [{"citation": {"kind": "record", "system": "DocuInsights", "record": ref, "asOf": a.get("at") or "", "text": f"case record {ref}, assessment {a.get('id')}"}, "section": "intake", "how": "registered"}]
    docs = {d["id"]: d for d in live_docs(case) if not d.get("assumed")}
    doc_ent: dict[str, str] = {}
    doc_key: dict[str, str] = {}

    def cite(doc_id: str, page: Any, line: Any, quote: str, section: str, how: str) -> list[dict[str, Any]]:
        d = docs.get(doc_id)
        if d is None:
            return list(record)
        locator = f"p.{page}" + (f" l.{line}" if line else "") if page else ""
        return [{"citation": {"kind": "document", "document": doc_key[doc_id], "documentEntity": doc_ent[doc_id], "fileName": d["name"], "locator": locator, "quote": (quote or "")[:300],
                              "case": ref, "text": f"{d['name']} {locator}".strip() + (f" — {quote[:160]}" if quote else "")}, "section": section, "how": how}]

    def of_mention(m: dict[str, Any], section: str = "extract") -> list[dict[str, Any]]:
        anchor = ((docs.get(m["doc"]) or {}).get("fields") or {}).get(m.get("field") or "", {}).get("anchor") or {}
        return cite(m["doc"], anchor.get("page"), anchor.get("line"), anchor.get("snippet") or str(m.get("value") or ""), section, "extracted")

    def scoped(name: str) -> str:
        """The name of something that belongs to this case alone. KB Forge joins entities whose names differ only by a bracketed
        qualifier, so the case reference follows a dash, as KB Forge itself names an engagement after its client."""
        return f"{name} \u2014 {ref}"

    rec = a.get("recommendation") or {}
    decision = case.get("decision") or {}
    facts = {O.camel(k): v for k, v in (case.get("fields") or {}).items() if v not in (None, "")}
    ce = c.entity("Case", ref, description=(a.get("summary") or "").split("\n")[0][:400] or f"{profile.name} {ref}.",
                  props={**facts, "caseReference": ref, "status": case.get("status"), "outcome": rec.get("outcome"), "outcomeLabel": rec.get("label"), "assessedAt": a.get("at"),
                         "assessmentId": a.get("id"), "decision": decision.get("decision"), "decidedBy": decision.get("by")}, support=record)
    uc = c.entity("UseCase", profile.name, props={"profileId": profile.id})
    c.triple(ce, "caseOfUseCase", uc, support=record)
    c.triple(c.entity("Company", owner, description="The organisation whose cases this workspace holds.", support=record), "companyHasCase", ce, support=record)
    from . import pipeline as P

    agent_name = {**{a["id"]: a["name"] for a in P.AGENTS}, **{a["stage"]: a["name"] for a in P.AGENTS if a.get("stage")}}

    for d in docs.values():
        ver = current(d)
        tname = profile.type_name(doc_type(d)) if doc_type(d) else ""
        doc_key[d["id"]] = f"{ref}/{d['id']}v{d['current']}"
        pages = ver.get("pages") or ([ver["text"]] if ver.get("text") else [])
        doc_ent[d["id"]] = c.entity("SourceDocument", scoped(d["name"]), description=f"{tname or 'Document'} uploaded to {ref}, version {d['current']}, read by {ver.get('method') or 'no reader'}.",
                                    props={"documentId": doc_key[d["id"]], "fileName": d["name"], "format": d["name"].rsplit(".", 1)[-1].lower() if "." in d["name"] else "", "documentType": tname,
                                           "pages": len(pages), "sha256": ver.get("sha256"), "version": d["current"], "readMethod": ver.get("method"), "factCount": len(d.get("fields") or {}),
                                           "uploadedAs": profile.type_name(d["category"]) if d.get("category") in profile.types else None}, support=record)
        c.texts[doc_key[d["id"]]] = [str(p) for p in pages]
        c.documents.append({"id": doc_key[d["id"]], "entity": doc_ent[d["id"]], "fileName": d["name"], "case": ref, "version": d["current"], "sha256": ver.get("sha256"), "pages": len(pages),
                            "documentType": tname, "uploadedAt": ver.get("uploaded_at")})
        c.triple(ce, "hasSourceDocument", doc_ent[d["id"]], support=record)
        if tname:
            cl = d.get("classification") or {}
            c.triple(doc_ent[d["id"]], "documentOfKind", c.entity("Document", tname), props={"method": "reviewer" if d.get("effective_type") else cl.get("method"), "basis": (cl.get("rationale") or "")[:200]},
                     support=cite(d["id"], 1, None, "", "classify", "classified"), confidence=cl.get("confidence"))

    parties, products = [], []
    for e in a.get("entities") or []:
        mentions = [m for m in e.get("mentions") or [] if m.get("doc") in docs]
        sup = [s for m in mentions for s in of_mention(m)] or list(record)
        if e["type"] == "Party":
            address = next((m["value"].split(",", 1)[1].strip() for m in e.get("mentions") or [] if "," in str(m.get("value"))), None)
            eid = c.entity("Organization", e["name"], key=e.get("key"), synonyms=sorted({m.get("name") or "" for m in e.get("mentions") or []}), props={"address": address}, support=sup)
            parties.append((eid, e))
            c.triple(ce, "caseInvolvesOrganization", eid, props={"role": ", ".join(e.get("roles") or [])}, support=sup[:3])
            for role in e.get("roles") or []:
                c.triple(eid, "organizationActsAs", c.entity("Role", role), props={"case": ref}, support=[s for m in mentions if m.get("role") == role for s in of_mention(m)][:2] or sup[:1])
        elif e["type"] == "GoodsItem":
            traits = [f"{v.get('name')}: {v.get('value') if v.get('value') is not None else v.get('raw')}" for v in (e.get("characteristics") or {}).values()]
            eid = c.entity("Product", e["name"][:140], props={"characteristics": traits}, support=sup)
            products.append(eid)
            c.triple(ce, "caseConcernsProduct", eid, support=sup[:3])
        else:
            eid = c.entity("Identifier", f"{e['type']} {e['name']}", description=f"{e['type']} reference quoted in the documents.", props={"identifierType": e["type"], "value": e["name"]}, support=sup)
            c.triple(ce, "caseHasIdentifier", eid, support=sup[:3])
        for m in mentions:
            anchor = (docs[m["doc"]].get("fields") or {}).get(m.get("field") or "", {}).get("anchor") or {}
            c.triple(doc_ent[m["doc"]], "mentions", eid, props={"location": f"p.{anchor.get('page')}" + (f" l.{anchor.get('line')}" if anchor.get("line") else "") if anchor.get("page") else "",
                                                               "field": profile.field_name(m["ref"]) if m.get("ref") else m.get("field"), "role": m.get("role")}, support=of_mention(m))
    together = [{"citation": {"kind": "inferred", "text": f"both are named in case {ref}"}, "section": "resolve", "how": "inferred"}]
    if len(parties) <= 8:
        for i, (x, _) in enumerate(parties):
            for y, _ in parties[i + 1:]:
                c.triple(min(x, y), "transactsWith", max(x, y), props={"basis": f"named together in {ref}"}, support=together)
    by_local = {e["id"]: eid for eid, e in parties}
    for m in a.get("unresolved") or []:
        x, y = by_local.get(m.get("a")), by_local.get(m.get("b"))
        if x and y and m.get("decided") != "same":
            person = [{"citation": {"kind": "decision", "text": f"a reviewer confirmed two parties in case {ref}"}, "section": "review", "how": "decided"}]
            c.triple(min(x, y), "distinctFrom" if m.get("decided") == "different" else "possiblySameAs", max(x, y), props={"similarity": m.get("similarity"), "case": ref},
                     support=person if m.get("decided") else together)

    for r in a.get("references") or []:
        ret, res = r.get("retrieval") or {}, r.get("result") or {}
        web = [{"citation": {"kind": "web", "url": ret.get("url") or "", "asOf": ret.get("requested_as_of") or "", "source": ret.get("name") or "", "text": f"{ret.get('name')}, {ret.get('version') or ret.get('mode')}",
                             "quote": "", "contentHash": ret.get("result_hash") or ""}, "section": "reference", "how": "retrieved"}]
        rs = c.entity("ReferenceSource", ret.get("name") or r["id"], props={"connector": ret.get("connector"), "url": ret.get("url")}, support=web)
        entry: dict[str, str] = {}
        for ln in r.get("lines") or []:
            code = ln.get("display") or ln.get("code") or ""
            if not code:
                continue
            entry[str(ln.get("code") or code)] = c.entity("ReferenceEntry", f"{code} {ln.get('description') or ''}", description=ln.get("description") or "",
                                                          props={"code": code, "asOf": ret.get("requested_as_of"), "sourceVersion": ret.get("version")}, support=web)
            c.triple(rs, "referenceHasEntry", entry[str(ln.get("code") or code)], support=web)
        if res.get("status") == "supported" and str(res.get("code")) in entry and products:
            derived = [{"citation": {"kind": "inferred", "text": "; ".join(res.get("steps") or [])[:400]}, "section": "reference", "how": "derived"}]
            c.triple(products[0], "productClassifiedAs", entry[str(res["code"])], props={"asOf": ret.get("requested_as_of"), "case": ref}, support=derived + web)

    for f in a.get("findings") or []:
        srcs = [s for s in f.get("sources") or [] if s.get("doc") in docs]
        sup = [x for s in srcs for x in cite(s["doc"], s.get("page"), s.get("line"), s.get("snippet") if s.get("field") != "classification" else "", f.get("agent") or "", "concluded")] or list(record)
        fe = c.entity("CaseFinding", scoped(f["title"]), description=f.get("message") or "", confidence=f.get("confidence"), support=sup,
                      props={"status": f.get("status"), "severity": f.get("severity"), "family": f.get("family"), "agent": f.get("agent"), "ruleVersion": (f.get("rule") or {}).get("version")})
        c.triple(ce, "caseHasFinding", fe, props={"status": f.get("status")}, support=record)
        if agent_name.get(f.get("agent") or ""):
            c.triple(fe, "findingProducedByAgent", c.entity("SoftwareAgent", agent_name[f["agent"]]), props={"assessment": a.get("id")}, support=record)
        if (f.get("rule") or {}).get("title"):
            c.triple(fe, "findingAppliesRule", c.entity("PolicyRule", f["rule"]["title"], props={"ruleVersion": str(f["rule"].get("version") or "")}), support=record)
        seen: set[str] = set()
        for s in srcs:
            if s["doc"] in seen:
                continue
            seen.add(s["doc"])
            c.triple(fe, "findingCitesDocument", doc_ent[s["doc"]], props={"location": f"p.{s.get('page')}" + (f" l.{s.get('line')}" if s.get("line") else "") if s.get("page") else "", "field": s.get("field_name")},
                     support=cite(s["doc"], s.get("page"), s.get("line"), s.get("snippet") if s.get("field") != "classification" else "", f.get("agent") or "", "concluded"))
    return c.data()


# ------------------------------------------------------------------------------------------------ reading a graph built elsewhere
def read_graph(data: bytes, filename: str = "") -> dict[str, Any]:
    """A KB Forge knowledge base (.zip), a KB Forge graph page (.html), or a JSON file of nodes and edges."""
    name = filename.lower()
    if data[:2] == b"PK" or name.endswith(".zip"):
        return _read_zip(data)
    text = data.decode("utf-8", errors="replace")
    if name.endswith((".html", ".htm")) or text.lstrip()[:1] == "<":
        m = re.search(r'<script id="kbforge-graph" type="application/json">(.*?)</script>', text, re.S)
        if not m:
            raise ValueError("this page holds no KB Forge graph (no 'kbforge-graph' block)")
        obj = json.loads(m.group(1))
        g = obj.get("graph") or {}
        pg = g.get("pg") or {}
        skip = ("id", "uri", "type", "schemaTypes", "origin", "paraphrased", "unverified", "verbatim")   # the page's own bookkeeping, not knowledge
        lineage = {n["id"] for n in pg.get("nodes") or [] if "Provenance" in (n.get("labels") or [])}
        nodes, chains = [], {}
        for n in pg.get("nodes") or []:
            if n["id"] in lineage:
                continue
            labels = [x for x in n.get("labels") or [] if x != "Entity"] or ["Thing"]
            for child, parent in zip(labels, labels[1:]):
                chains.setdefault(child, parent)
            nodes.append({**{k: v for k, v in (n.get("props") or {}).items() if k not in skip}, "id": n["id"], "type": labels[0]})

        def said(ev: Any) -> str:
            items = ev if isinstance(ev, list) else [ev]
            return "; ".join(str((x.get("quote") or x.get("text") or "") if isinstance(x, dict) else x) for x in items if x)[:300]

        out = _read_json({"nodes": nodes, "ontology": g.get("ontology") if isinstance(g.get("ontology"), dict) else {},
                          "edges": [{"from": r.get("from"), "to": r.get("to"), "relation": (r.get("props") or {}).get("relation") or O.camel(r.get("type") or ""),
                                     "evidence": said((r.get("props") or {}).get("evidence")), "confidence": (r.get("props") or {}).get("confidence")}
                                    for r in pg.get("rels") or [] if r.get("from") not in lineage and r.get("to") not in lineage]})
        for child, parent in chains.items():   # a class the page's ontology does not describe still keeps the parent its nodes show
            out["classes"].setdefault(child, {"parent": parent, "definition": ""})
            out["classes"][child]["parent"] = out["classes"][child].get("parent") or parent
        out["meta"].update(app="KB Forge", project=str(g.get("title") or ""), exported_at=str((obj.get("export") or {}).get("exported_at") or g.get("built_at") or ""), level=str(g.get("kb_type") or ""))
        return out
    try:
        return _read_json(json.loads(text))
    except json.JSONDecodeError as exc:
        raise ValueError("the file is not a KB Forge knowledge base (.zip), a KB Forge graph page (.html) or JSON") from exc


def _read_zip(data: bytes) -> dict[str, Any]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("not a zip file") from exc
    names = z.namelist()

    def find(suffix: str) -> str | None:
        hits = [n for n in names if n.replace("\\", "/").endswith(suffix)]
        return sorted(hits, key=len)[0] if hits else None

    ents, trips = find("graph/entities.jsonl"), find("graph/triples.jsonl")
    if not ents or not trips:
        raise ValueError("not a KB Forge knowledge base: graph/entities.jsonl and graph/triples.jsonl are missing")
    out: dict[str, Any] = {"meta": {"app": "KB Forge", "project": "", "exported_at": "", "level": ""}, "nodes": [], "edges": [], "classes": {}, "relations": {}}
    if find("manifest.json"):
        m = json.loads(z.read(find("manifest.json")).decode("utf-8"))
        job = m.get("job") if isinstance(m.get("job"), dict) else m
        out["meta"].update(project=str(job.get("display_name") or job.get("subject_name") or job.get("company_name") or job.get("sub_industry") or ""), exported_at=str(job.get("created_at") or ""),
                           level=str(job.get("kb_type") or ""))
    if find("ontology/ontology_merged.json"):
        onto = json.loads(z.read(find("ontology/ontology_merged.json")).decode("utf-8"))
        out["classes"] = {c["name"]: {"parent": c.get("parent"), "definition": c.get("definition") or ""} for c in onto.get("classes") or [] if c.get("name")}
        out["relations"] = {r["name"]: {"domain": r.get("domain"), "range": r.get("range"), "inverse": r.get("inverse"), "definition": r.get("definition") or ""} for r in onto.get("relationships") or [] if r.get("name")}
    for line in z.read(ents).decode("utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            props = dict(d.get("props") or {})
            out["nodes"].append({"id": d["id"], "type": d.get("type") or "Thing", "name": d.get("name") or d["id"], "description": str(props.pop("description", "") or ""),
                                 "aliases": list(d.get("synonyms") or []), "props": props, "confidence": d.get("confidence"), "stub": bool(d.get("stub"))})
    for line in z.read(trips).decode("utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out["edges"].append({"from": d.get("subject"), "to": d.get("object"), "relation": d.get("predicate"), "props": dict(d.get("props") or {}), "confidence": d.get("confidence")})
    return _limit(out)


def _read_json(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("the JSON must be an object with nodes and edges")
    g = obj.get("graph") if isinstance(obj.get("graph"), dict) and not obj.get("nodes") else obj
    nodes = g.get("nodes") or g.get("entities") or []
    edges = g.get("edges") or g.get("links") or g.get("rels") or g.get("relationships") or g.get("triples") or []
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("the JSON holds no nodes (expected 'nodes' or 'entities')")
    out: dict[str, Any] = {"meta": {"app": str(obj.get("app") or "JSON"), "project": str(obj.get("project") or obj.get("title") or obj.get("name") or ""), "exported_at": str(obj.get("exported_at") or ""), "level": ""},
                           "nodes": [], "edges": [], "classes": {}, "relations": {}}
    reserved = {"id", "@id", "type", "class", "kind", "labels", "name", "label", "title", "description", "aliases", "synonyms", "props", "properties", "attributes", "confidence", "stub"}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or n.get("@id") or n.get("name") or "")
        type_ = n.get("type") or n.get("class") or n.get("kind") or next((x for x in n.get("labels") or [] if x != "Entity"), "Thing")
        props = dict(n.get("props") or n.get("properties") or n.get("attributes") or {})
        props.update({k: v for k, v in n.items() if k not in reserved and isinstance(v, (str, int, float, bool, list))})
        if nid:
            out["nodes"].append({"id": nid, "type": str(type_) if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", str(type_)) else O.pascal(str(type_)), "name": str(n.get("name") or n.get("label") or n.get("title") or nid), "description": str(n.get("description") or props.pop("description", "") or ""),
                                 "aliases": list(n.get("aliases") or n.get("synonyms") or []), "props": props, "confidence": n.get("confidence"), "stub": bool(n.get("stub"))})
    for e in edges:
        if not isinstance(e, dict):
            continue
        frm = e.get("from") or e.get("source") or e.get("subject") or e.get("src") or e.get("start")
        to = e.get("to") or e.get("target") or e.get("object") or e.get("dst") or e.get("end")
        rel = e.get("relation") or e.get("predicate") or e.get("rel") or e.get("relationship") or e.get("type") or e.get("label") or "relatedTo"
        if frm and to:
            props = dict(e.get("props") or e.get("properties") or {})
            if e.get("evidence"):
                props["evidence"] = e["evidence"]
            out["edges"].append({"from": str(frm), "to": str(to), "relation": O.camel(str(rel)) if str(rel).isupper() or "_" in str(rel) or " " in str(rel) else str(rel), "props": props, "confidence": e.get("confidence")})
    block = obj.get("ontology") if isinstance(obj.get("ontology"), dict) else {}
    for cdef in block.get("classes") or block.get("entities") or []:
        if isinstance(cdef, dict) and cdef.get("name"):
            out["classes"][cdef["name"] if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", str(cdef["name"])) else O.pascal(cdef["name"])] = {"parent": cdef.get("parent"), "definition": cdef.get("definition") or cdef.get("description") or ""}
    for rdef in block.get("relations") or block.get("relationships") or block.get("edges") or []:
        if isinstance(rdef, dict) and rdef.get("name"):
            out["relations"][rdef["name"]] = {"domain": rdef.get("domain"), "range": rdef.get("range"), "inverse": rdef.get("inverse") or rdef.get("inverseName"), "definition": rdef.get("definition") or rdef.get("description") or ""}
    return _limit(out)


def _limit(g: dict[str, Any]) -> dict[str, Any]:
    if not g["nodes"]:
        raise ValueError("the graph has no entities")
    if len(g["nodes"]) > MAX_IMPORT:
        raise ValueError(f"the graph has {len(g['nodes']):,} entities; the limit is {MAX_IMPORT:,}")
    return g


def import_contribution(g: dict[str, Any], slug: str, label: str) -> dict[str, Any]:
    """An imported graph as a source: ids and classes kept, every entity and link cited to the import."""
    meta = g.get("meta") or {}
    c = Contribution("import", slug, label, meta.get("exported_at") or now())
    where = " · ".join(x for x in (meta.get("app"), meta.get("project") or label) if x)
    sup = [{"citation": {"kind": "import", "app": meta.get("app") or "", "project": meta.get("project") or label, "asOf": (meta.get("exported_at") or "")[:10], "locator": where, "text": f"imported from {where}"},
            "section": "import", "how": "imported"}]
    known: dict[str, str] = {}
    # ids already written the KB Forge way (class-slug/name-slug, a combined graph adds a space in front) are kept as they are
    native = bool(g["nodes"]) and all(re.fullmatch(r"[a-z0-9-]+(/[a-z0-9-]+)+", str(n["id"])) for n in g["nodes"][:200])
    for n in g["nodes"]:
        eid = n["id"] if native else O.entity_id(n["type"], n["name"])
        known[n["id"]] = c.entity(n["type"], n["name"], description=n.get("description") or "", props={k: v for k, v in (n.get("props") or {}).items() if not str(k).startswith("_")},
                                  synonyms=[str(a) for a in n.get("aliases") or []], support=sup, confidence=n.get("confidence"), eid=eid, stub=bool(n.get("stub")))
    for e in g["edges"]:
        if e["from"] in known and e["to"] in known:
            props = {k: v for k, v in (e.get("props") or {}).items() if not str(k).startswith("_")}
            link = sup if not props.get("evidence") else [{"citation": {**sup[0]["citation"], "quote": str(props["evidence"])[:300]}, "section": "import", "how": "imported"}]
            c.triple(known[e["from"]], e["relation"], known[e["to"]], props=props, support=link, confidence=e.get("confidence"))
    out = c.data()
    out["classes"], out["relations"] = g.get("classes") or {}, g.get("relations") or {}
    return out


# ------------------------------------------------------------------------------------------------ building the graph from its sources
def build(contributions: list[dict[str, Any]], onto: O.Ontology | None = None) -> dict[str, Any]:
    onto = onto or O.load()
    ents: dict[str, dict[str, Any]] = {}
    trips: dict[tuple[str, str, str], dict[str, Any]] = {}
    cits: dict[str, dict[str, Any]] = {}
    esup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tsup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    documents: list[dict[str, Any]] = []
    texts: dict[str, list[str]] = {}
    org_key: dict[str, str] = {}
    invalid: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    stats: dict[str, dict[str, int]] = {}
    placed: dict[str, str] = {}   # an added knowledge base -> the level it sits at

    def keep(sup: dict[str, Any]) -> dict[str, Any]:
        cit = dict(sup["citation"])
        cid = "cit-" + _hash(cit.get("kind"), cit.get("document") or cit.get("source") or cit.get("url") or cit.get("record") or cit.get("project"), cit.get("locator"), cit.get("quote"), cit.get("text"))
        cits.setdefault(cid, {"id": cid, **cit})
        return {"citation": cid, "section": sup.get("section") or "", "how": sup.get("how") or ""}

    def add_support(store: dict[str, list[dict[str, Any]]], key: str, sups: list[dict[str, Any]]) -> None:
        have = {(s["citation"], s["how"]) for s in store[key]}
        for s in sups:
            k = keep(s)
            if (k["citation"], k["how"]) not in have:
                have.add((k["citation"], k["how"]))
                store[key].append(k)

    for contrib in contributions:
        src = contrib["source"]
        module = {"profile": f"profile:{src['id']}", "case": "case", "import": f"import:{src['id']}"}.get(src["kind"], src["kind"])
        if src["kind"] == "import" and src.get("placed") in LEVEL_ORDER:
            placed[module] = src["placed"]
        stats.setdefault(module, {"entities": 0, "triples": 0})
        for cname, cdef in (contrib.get("classes") or {}).items():
            if cname not in onto.classes:
                onto.add_class(cname, parent=cdef.get("parent"), definition=cdef.get("definition") or "", source="import")
            elif onto.classes[cname]["source"] == "import":   # first met as another class's parent: now it gets its own parent and definition
                known = onto.classes[cname]
                parent = cdef.get("parent")
                if not known["parent"] and parent and parent not in ("Thing", cname) and cname not in [parent, *onto.ancestors(parent)]:
                    if parent not in onto.classes:
                        onto.add_class(parent, source="import")
                    known["parent"] = parent
                known["definition"] = known["definition"] or cdef.get("definition") or ""
        for rname, rdef in (contrib.get("relations") or {}).items():
            if rname not in onto.relationships:
                onto.add_relationship(rname, rdef.get("domain") or "Thing", rdef.get("range") or "Thing", inverse=rdef.get("inverse"), definition=rdef.get("definition") or "", source="import")
        remap: dict[str, str] = {}
        for e in contrib["entities"]:
            if e["type"] not in onto.classes:
                onto.add_class(e["type"], source="import", definition="")
            eid = e["id"]
            if onto.is_a(e["type"], "Organization"):
                keys = [k for k in {e.get("key") or "", O.normalize_name(e["name"]), *(O.normalize_name(s) for s in e.get("synonyms") or [])} if k]
                eid = next((org_key[k] for k in keys if k in org_key), eid)
                for k in keys:
                    org_key.setdefault(k, eid)
            remap[e["id"]] = eid
            cur = ents.get(eid)
            if cur is None:
                cur = ents[eid] = {"id": eid, "type": e["type"], "name": e["name"], "props": {}, "synonyms": [], "sourceModules": [], "confidence": None, "stub": bool(e.get("stub"))}
                stats[module]["entities"] += 1
            elif cur["type"] != e["type"] and onto.is_a(e["type"], cur["type"]):
                cur["type"] = e["type"]   # the more specific class wins; the id keeps the class it was first created under
            if not e.get("stub"):
                cur["stub"] = False
            for k, v in (e.get("props") or {}).items():
                if k not in cur["props"] or (src["kind"] == "case" and k not in ("description",)):
                    cur["props"][k] = v
            for s in [e["name"], *(e.get("synonyms") or [])]:
                if s and s != cur["name"] and s not in cur["synonyms"]:
                    cur["synonyms"].append(s)
            if module not in cur["sourceModules"]:
                cur["sourceModules"].append(module)
            if _conf(e.get("confidence")) is not None:
                cur["confidence"] = max(cur["confidence"] or 0, _conf(e["confidence"]))
            add_support(esup, eid, e.get("support") or [])
        for t in contrib["triples"]:
            s, p, o = remap.get(t["s"], t["s"]), t["p"], remap.get(t["o"], t["o"])
            for end in (s, o):
                if end not in ents:   # a link to something no source defines: kept as a stub, the best target for enrichment
                    ents[end] = {"id": end, "type": O.pascal(end.split("/")[0]) if "/" in end else "Thing", "name": end.split("/")[-1].replace("-", " "), "props": {}, "synonyms": [],
                                 "sourceModules": [module], "confidence": None, "stub": True}
            if s == o:
                continue
            if p not in onto.relationships:
                onto.add_relationship(p, "Thing", "Thing", source="import")
            if not onto.fits(p, ents[s]["type"], ents[o]["type"]):
                if onto.fits(p, ents[o]["type"], ents[s]["type"]):
                    repairs.append({"predicate": p, "from": [s, o], "to": [o, s], "why": "the other direction fits the relationship's domain and range", "source": module})
                    s, o = o, s
                else:
                    invalid.append({"subject": s, "predicate": p, "object": o, "why": f"{ents[s]['type']} -> {ents[o]['type']} does not fit {onto.relationships[p]['domain']} -> {onto.relationships[p]['range']}", "source": module})
                    t = {**t, "props": {**t["props"], "importedRelation": p}}
                    p = "relatedTo"
            if onto.relationships[p].get("symmetric") and o < s:
                s, o = o, s
            cur_t = trips.get((s, p, o))
            if cur_t is None:
                cur_t = trips[(s, p, o)] = {"subject": s, "predicate": p, "object": o, "props": {}, "sourceModule": module, "confidence": None}
                stats[module]["triples"] += 1
            for k, v in t["props"].items():
                if k in ("case", "basis") and cur_t["props"].get(k) and v != cur_t["props"][k]:
                    seen = [x.strip() for x in str(cur_t["props"][k]).split(";")]
                    cur_t["props"][k] = "; ".join([*seen, str(v)][-6:]) if str(v) not in seen else cur_t["props"][k]
                else:
                    cur_t["props"][k] = v
            if _conf(t.get("confidence")) is not None:
                cur_t["confidence"] = max(cur_t["confidence"] or 0, _conf(t["confidence"]))
            add_support(tsup, f"{s}|{p}|{o}", t.get("support") or [])
        documents += contrib.get("documents") or []
        texts.update(contrib.get("texts") or {})

    # what the cases add up to: how often a party or product was met, and cases that quote the same reference number
    cases_of: dict[str, list[str]] = defaultdict(list)
    for (s, p, o) in trips:
        if p in ("caseInvolvesOrganization", "caseConcernsProduct", "caseHasIdentifier"):
            cases_of[o].append(s)
    for eid, cs in cases_of.items():
        e = ents[eid]
        when = sorted(str(ents[c]["props"].get("assessedAt") or "")[:10] for c in cs if ents[c]["props"].get("assessedAt"))
        e["props"]["seenInCases"] = len(set(cs))
        if when:
            e["props"]["firstSeen"], e["props"]["lastSeen"] = when[0], when[-1]
        if not e["props"].get("description") and e["type"] in ("Organization", "Product"):
            roles = sorted({ents[o]["name"] for (s, p, o) in trips if s == eid and p == "organizationActsAs"})
            e["props"]["description"] = (f"Named as {', '.join(roles).lower()} in " if roles else "Named in ") + f"{len(set(cs))} case(s): {', '.join(sorted({ents[c]['name'] for c in cs})[:4])}."
        if e["type"] == "Identifier" and len(set(cs)) > 1:
            cs2 = sorted(set(cs))
            for i, x in enumerate(cs2):
                for y in cs2[i + 1:]:
                    trips[(x, "sharesIdentifierWith", y)] = {"subject": x, "predicate": "sharesIdentifierWith", "object": y, "props": {"identifier": e["name"]}, "sourceModule": "case", "confidence": None}
                    add_support(tsup, f"{x}|sharesIdentifierWith|{y}", [{"citation": {"kind": "inferred", "text": f"both cases quote {e['name']}"}, "section": "memory", "how": "inferred"}])
    for e in ents.values():
        # knowledgeLevel: the levels that know the entity, written as KB Forge writes it: a list of its level ids (industry, domain, coforge,
        # customer), the level the entity is shown at first. graphLevel: how deep it sits when the graph is drilled down. What the accelerator,
        # the use cases and the cases contributed is placed by its class. What only an added knowledge base knows sits at the level chosen for
        # that knowledge base, else at the level KB Forge recorded on the entity itself (a combined graph says it entity by entity), and keeps
        # the depth it came with. No level at all: added knowledge.
        came = O.kb_forge_levels(e["props"].get("knowledgeLevel"))
        if _added(e):
            home = next((placed[m] for m in e["sourceModules"] if m in placed), "")
        else:
            home = onto.level(e["type"]) or "customer"
            if onto.depth(e["type"]):
                e["props"]["graphLevel"] = onto.depth(e["type"])
        first = [O.KB_FORGE_ID[home]] if home else []
        e["props"]["knowledgeLevel"] = first + [x for x in came if x not in first]
    return {"entities": ents, "triples": trips, "citations": cits, "entity_support": dict(esup), "triple_support": dict(tsup), "documents": documents, "texts": texts,
            "invalid": invalid, "repairs": repairs, "module_stats": stats, "ontology": onto}


def _added(e: dict[str, Any]) -> bool:
    """Known only from imported knowledge: no use case declares it and no case has met it."""
    return bool(e.get("sourceModules")) and all(str(m).startswith("import:") for m in e["sourceModules"])


def level_of(e: dict[str, Any]) -> str:
    """industry, domain, solution or customer; 'added' for knowledge that was added without a level and that no case has touched."""
    got = O.kb_forge_levels(e["props"].get("knowledgeLevel"))   # stored in KB Forge's ids; the first is the level it is shown at
    lv = O.KB_FORGE_LEVEL.get(got[0]) if got else None
    return lv if lv in LEVEL_ORDER else "added"


def depth_of(e: dict[str, Any]) -> int:
    try:
        return int(e["props"].get("graphLevel"))
    except (TypeError, ValueError):
        return 99


def verify(g: dict[str, Any]) -> dict[str, Any]:
    """Every document citation checked against the text it cites, with no model; then where each entity and link comes from."""
    ents, cits, texts = g["entities"], g["citations"], g["texts"]
    stats = Counter()

    def page_text(cit: dict[str, Any], wide: bool = False) -> str | None:
        pages = texts.get(cit.get("document") or "")
        if pages is None:
            return None
        m = re.match(r"p\.(\d+)", cit.get("locator") or "")
        if m and not wide and 0 < int(m.group(1)) <= len(pages):
            return _squash(pages[int(m.group(1)) - 1])
        return _squash(" ".join(pages))

    def named(e: dict[str, Any], text: str) -> str:
        for n in [e["name"], *e.get("synonyms", [])]:
            n = _squash(re.sub(r"\(.*?\)", " ", n))
            if n and n in text:
                return "named"
        words = [w for w in _squash(re.sub(r"\(.*?\)", " ", e["name"])).split() if len(w) > 2]
        return "paraphrased" if words and sum(1 for w in words if w in text) / len(words) >= 2 / 3 else "missing"

    def origin(sups: list[dict[str, Any]]) -> tuple[str, bool, bool]:
        kinds = {cits[s["citation"]]["kind"] for s in sups}
        checks = [s.get("check") for s in sups if cits[s["citation"]]["kind"] == "document"]
        para = bool(checks) and not any(c in ("named", "quoted", "read") for c in checks) and "paraphrased" in checks
        verbatim = "quoted" in checks
        if "document" in kinds:
            if any(c in ("named", "quoted", "read", "paraphrased", "unchecked") for c in checks):
                return "document", para, verbatim
            return ("unverified", False, False) if kinds == {"document"} else (_first_origin(kinds - {"document"}), False, False)
        return _first_origin(kinds), False, False

    e_origin, t_origin = {}, {}
    for eid, sups in g["entity_support"].items():
        for s in sups:
            cit = cits[s["citation"]]
            if cit["kind"] != "document":
                continue
            text = page_text(cit)
            if text is None:
                s["check"] = "unchecked"
            else:
                quote = _squash(cit.get("quote"))
                got = named(ents[eid], text)
                if got == "missing" and ents[eid]["type"] in ("CaseFinding", "Identifier", "Product"):
                    got = "quoted" if quote and quote in text else named(ents[eid], page_text(cit, wide=True) or "")
                if got == "missing" and quote and quote in text:
                    got = "quoted"
                if got == "missing" and not quote:
                    got = "unchecked"   # the citation names a document but no line of it: there is nothing to look for
                s["check"] = got
            stats[s["check"]] += 1
            stats["checked_entities"] += 1
    for key, sups in g["triple_support"].items():
        s_id, _, o_id = key.split("|")
        for s in sups:
            cit = cits[s["citation"]]
            if cit["kind"] != "document":
                continue
            text = page_text(cit)
            if text is None:
                s["check"] = "unchecked"
            else:
                quote = _squash(cit.get("quote"))
                if quote and quote in text:
                    s["check"] = "quoted"
                else:
                    whole = page_text(cit, wide=True) or ""
                    s["check"] = "read" if any(named(ents[x], whole) != "missing" for x in (s_id, o_id) if ents[x]["type"] not in ("Case", "SourceDocument", "CaseFinding")) else ("unchecked" if not quote else "missing")
            stats[s["check"]] += 1
            stats["checked_relationships"] += 1
    counts = {"entities": Counter(), "relationships": Counter(), "paraphrased": 0, "verbatim": 0}
    for eid in ents:
        o, para, verb = origin(g["entity_support"].get(eid) or [])
        e_origin[eid] = o
        counts["entities"][o] += 1
        counts["paraphrased"] += para
    for (s, p, o_) in g["triples"]:
        key = f"{s}|{p}|{o_}"
        o, para, verb = origin(g["triple_support"].get(key) or [])
        t_origin[key] = o
        counts["relationships"][o] += 1
        counts["verbatim"] += verb
    g["origins"] = {"entities": e_origin, "triples": t_origin}
    g["verification"] = {"version": 2, "verified_at": now(), "anchor": "", "stats": {k: stats.get(k, 0) for k in ("checked_entities", "checked_relationships", "named", "paraphrased", "missing", "unchecked", "quoted", "read")},
                         "origins": {"entities": dict(counts["entities"]), "relationships": dict(counts["relationships"]), "paraphrased": counts["paraphrased"], "verbatim": counts["verbatim"]}}
    return g["verification"]


def _first_origin(kinds: set[str]) -> str:
    for kind, origin in (("record", "system"), ("profile", "settings"), ("web", "web"), ("decision", "decision"), ("import", "imported"), ("inferred", "inferred")):
        if kind in kinds:
            return origin
    return "unknown"


def quality(g: dict[str, Any]) -> dict[str, Any]:
    """KB Forge's quality score, with one component changed: where it asks a model how well the graph answers its
    competency questions, this graph reports the share of entities and links whose evidence was found (15%)."""
    ents, trips, onto = g["entities"], g["triples"], g["ontology"]
    n, m = len(ents), len(trips)
    if not n:
        return {"score": 0.0, "components": {}, "issues": {}}
    adj: dict[str, set[str]] = defaultdict(set)
    for (s, _, o) in trips:
        adj[s].add(o)
        adj[o].add(s)
    seen: set[str] = set()
    biggest = 0
    for start in ents:
        if start in seen:
            continue
        size, todo = 0, [start]
        seen.add(start)
        while todo:
            cur = todo.pop()
            size += 1
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    todo.append(nb)
        biggest = max(biggest, size)
    stubs = [e["id"] for e in ents.values() if e["stub"]]
    described = sum(1 for e in ents.values() if e["props"].get("description"))
    own_classes = [c for c in onto.classes.values() if c["source"] != "import"]
    own_rels = [r for r in onto.relationships.values() if r["source"] != "import" and r["name"] != "relatedTo"]
    used_c = {e["type"] for e in ents.values()} | {a for e in ents.values() for a in onto.ancestors(e["type"])}
    used_r = {p for (_, p, _) in trips}
    origins = g.get("origins") or {"entities": {}, "triples": {}}
    backed = sum(1 for o in list(origins["entities"].values()) + list(origins["triples"].values()) if o not in ("unverified", "unknown"))
    fallbacks = sum(1 for (_, p, _) in trips if p == "relatedTo")
    comp = {"link_density": min(1.0, (m / n) / 4), "stub_freedom": 1 - len(stubs) / n, "connectedness": biggest / n, "description_coverage": described / n,
            "ontology_coverage": (sum(1 for c in own_classes if c["name"] in used_c) / max(1, len(own_classes)) + sum(1 for r in own_rels if r["name"] in used_r) / max(1, len(own_rels))) / 2,
            "validity": 1 - min(1.0, (len(g["invalid"]) + fallbacks) / max(1, m)), "evidence_coverage": backed / max(1, n + m)}
    weights = {"link_density": 20, "stub_freedom": 15, "connectedness": 10, "description_coverage": 15, "ontology_coverage": 15, "validity": 10, "evidence_coverage": 15}
    return {"score": round(sum(comp[k] * w for k, w in weights.items()), 1), "components": {k: round(v, 3) for k, v in comp.items()}, "weights": weights,
            "issues": {"stubs": stubs[:50], "undescribed": [e["id"] for e in ents.values() if not e["props"].get("description")][:50], "invalid_triples": len(g["invalid"]),
                       "relatedTo_fallbacks": fallbacks, "unverified": [k for k, o in {**origins["entities"], **origins["triples"]}.items() if o == "unverified"][:50]}}


# ------------------------------------------------------------------------------------------------ the store
class KnowledgeBase:
    def __init__(self, root: str | Path, name: str = "Workspace knowledge", owner: str = "This workspace"):
        self.root = Path(root)
        self.name = name
        self.owner = owner   # the organisation whose cases the workspace holds: the head of the customer level
        with _guard:
            self._lock = _locks.setdefault(str(self.root.resolve()), threading.RLock())
        self._cache: tuple[float, dict[str, Any]] | None = None

    # ---- sources
    def _src(self, kind: str) -> Path:
        return self.root / "sources" / kind

    def put_source(self, kind: str, sid: str, data: dict[str, Any]) -> None:
        self._write(self._src(kind) / f"{O.slugify(sid, 120)}.json", json.dumps(data, ensure_ascii=False))

    def drop_source(self, kind: str, sid: str) -> bool:
        path = self._src(kind) / f"{O.slugify(sid, 120)}.json"
        if not path.exists():
            return False
        path.rename(path.with_suffix(".removed"))   # kept beside, never deleted: an import taken out can be put back
        return True

    def sources(self, kind: str) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self._src(kind).glob("*.json")) if self._src(kind).is_dir() else []:
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return out

    def imports(self) -> list[dict[str, Any]]:
        return [{**s["source"], "entities": len(s["entities"]), "relationships": len(s["triples"]), "level_name": O.LEVELS.get(s["source"].get("placed") or "", "Each entity at its own level" if s["source"].get("own_levels") else "No level yet")} for s in self.sources("imports")]

    def add_import(self, data: bytes, filename: str, label: str = "", level: str = "") -> dict[str, Any]:
        """Add a knowledge base built elsewhere. It sits at the level given, else at the level it was built for in KB Forge (industry, domain,
        Coforge experience -> solution, customer); a graph that says neither is kept as added knowledge until a level is chosen."""
        g = read_graph(data, filename)
        label = (label or g["meta"].get("project") or Path(filename).stem or "import").strip()[:80]
        slug = O.slugify(label, 60)
        contrib = import_contribution(g, slug, label)
        placed = level if level in LEVEL_ORDER else O.KB_FORGE_LEVEL.get(str(g["meta"].get("level") or "").lower(), "")
        own = sum(1 for e in contrib["entities"] if O.kb_forge_levels((e.get("props") or {}).get("knowledgeLevel")))   # a combined graph: each entity says its own level
        contrib["source"].update(file=filename, app=g["meta"].get("app"), imported_at=now(), level=g["meta"].get("level"), placed=placed, own_levels=own)
        self.put_source("imports", slug, contrib)
        return {**contrib["source"], "entities": len(contrib["entities"]), "relationships": len(contrib["triples"])}

    def aliases(self) -> dict[str, str]:
        """Other names of organisations that imported knowledge states, as {name key: the organisation's name key}. The resolver links a
        document that uses one of them to the organisation. Only imports count: a name the agents themselves once linked is not fed back."""
        from . import values as V

        base = O.load()
        out: dict[str, str] = {}
        for src in self.sources("imports"):
            parents = {k: (v or {}).get("parent") for k, v in (src.get("classes") or {}).items()}

            def is_org(t: str | None, seen: tuple[str, ...] = ()) -> bool:
                return bool(t) and t not in seen and (t == "Organization" or base.is_a(t, "Organization") or is_org(parents.get(t), (*seen, t)))

            for e in src["entities"]:
                canon = V.party_key(e["name"])
                if canon and is_org(e["type"]):
                    for syn in e.get("synonyms") or []:
                        key = V.party_key(syn)
                        if key and key != canon:
                            out[key] = canon
        return out

    # ---- building
    def rebuild(self, profiles: list[Profile]) -> dict[str, Any]:
        with self._lock:
            contribs = [foundation_contribution(profiles), *(profile_contribution(p) for p in profiles)]
            contribs += sorted(self.sources("cases"), key=lambda s: (s["source"].get("at") or "", s["source"]["id"]))
            contribs += self.sources("imports")
            g = build(contribs)
            ver = verify(g)
            q = quality(g)
            onto: O.Ontology = g["ontology"]
            ents = sorted(g["entities"].values(), key=lambda e: e["id"])
            trips = sorted(g["triples"].values(), key=lambda t: (t["subject"], t["predicate"], t["object"]))
            index = {"entities": len(ents), "triples": len(trips), "stubs": sum(1 for e in ents if e["stub"]),
                     "byType": dict(Counter(e["type"] for e in ents).most_common()), "byPredicate": dict(Counter(t["predicate"] for t in trips).most_common()),
                     "byLevel": dict(Counter(level_of(e) for e in ents)), "built_at": now(), "build": BUILD}
            prov = {"version": 1, "stats": {"entities": len(ents), "relationships": len(trips), "citations": len(g["citations"]), "documents": len(g["documents"]),
                                           "entities_document_backed": sum(1 for o in g["origins"]["entities"].values() if o == "document"),
                                           "relationships_document_backed": sum(1 for o in g["origins"]["triples"].values() if o == "document")},
                    "documents": g["documents"], "web_sources": [c for c in g["citations"].values() if c["kind"] == "web"], "activities": [],
                    "citations": list(g["citations"].values()), "entity_support": g["entity_support"], "triple_support": g["triple_support"],
                    "meta": {"job_id": _hash(str(self.root)), "model": "none (built in code)", "built_by": f"DocuInsights {__version__}"}, "verification": ver, "origins": g["origins"]}
            files = {"graph/entities.jsonl": "\n".join(json.dumps(e, ensure_ascii=False) for e in ents) + "\n",
                     "graph/triples.jsonl": "\n".join(json.dumps(t, ensure_ascii=False) for t in trips) + ("\n" if trips else ""),
                     "graph/index.json": json.dumps(index, indent=1), "graph/module_stats.json": json.dumps(g["module_stats"], indent=1),
                     "graph/provenance.json": json.dumps(prov, ensure_ascii=False), "graph/invalid_triples.json": json.dumps(g["invalid"], indent=1),
                     "graph/structure_repairs.json": json.dumps(g["repairs"], indent=1),
                     "graph/verification.json": json.dumps({"version": 2, "summary": ver}, indent=1),
                     "ontology/ontology_merged.json": json.dumps(onto.merged(), ensure_ascii=False, indent=1),
                     "ontology/custom/docuinsights.json": json.dumps(onto.extension(), ensure_ascii=False, indent=1),
                     "quality/metrics.json": json.dumps(q, indent=1)}
            for rel, text in files.items():
                self._write(self.root / rel, text)
            manifest = {"kbforge": {"schemaVersion": SCHEMA, "generatedAt": now()},
                        "job": {"job_id": prov["meta"]["job_id"], "kb_type": "domain", "namespace": "https://docuinsights.local/kb/" + O.slugify(self.name), "company_name": "", "sub_industry": "",
                                "industry": "", "subject_name": self.name, "display_name": self.name, "created_at": now(), "model": "none", "version": __version__, "market": "b2b",
                                "built_by": {"app": "DocuInsights", "version": __version__}, "_quality_score": q["score"]},
                        "metrics": {"entities": len(ents), "relationships": len(trips), "quality": q["score"]}, "stages": [],
                        "files": [{"path": rel, "bytes": len(text.encode("utf-8")), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()} for rel, text in sorted(files.items())]}
            self._write(self.root / "manifest.json", json.dumps(manifest, indent=1))
            self._cache = None
            return {**index, "quality": q["score"], "verification": ver}

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    # ---- reading
    def built(self) -> bool:
        """Built, and by this version's rules. A knowledge base an earlier version built (other levels, no company at the head of the cases)
        counts as not built: the first use rebuilds it from its sources, which are kept."""
        try:
            return json.loads((self.root / "graph" / "index.json").read_text(encoding="utf-8")).get("build") == BUILD and (self.root / "graph" / "entities.jsonl").exists()
        except (OSError, ValueError):
            return False

    def load(self) -> dict[str, Any]:
        with self._lock:
            path = self.root / "graph" / "provenance.json"
            if not path.exists():
                return {"entities": {}, "triples": [], "provenance": {"citations": [], "entity_support": {}, "triple_support": {}, "origins": {"entities": {}, "triples": {}}, "verification": {}, "stats": {}, "documents": []},
                        "index": {"entities": 0, "triples": 0, "stubs": 0, "byType": {}, "byPredicate": {}, "byLevel": {}}, "quality": {"score": 0, "components": {}}, "ontology": O.load().merged()}
            stamp = path.stat().st_mtime
            if self._cache and self._cache[0] == stamp:
                return self._cache[1]
            read = lambda rel: json.loads((self.root / rel).read_text(encoding="utf-8"))  # noqa: E731
            lines = lambda rel: [json.loads(x) for x in (self.root / rel).read_text(encoding="utf-8").splitlines() if x.strip()]  # noqa: E731
            data = {"entities": {e["id"]: e for e in lines("graph/entities.jsonl")}, "triples": lines("graph/triples.jsonl"), "provenance": read("graph/provenance.json"),
                    "index": read("graph/index.json"), "quality": read("quality/metrics.json"), "ontology": read("ontology/ontology_merged.json")}
            self._cache = (stamp, data)
            return data

    def overview(self) -> dict[str, Any]:
        d = self.load()
        prov, onto = d["provenance"], d["ontology"]
        class_level = {c["name"]: c.get("graphLevel") for c in onto["classes"]}
        top = sorted((e for e in d["entities"].values() if e["type"] in ("Organization", "Product")), key=lambda e: -(e["props"].get("seenInCases") or 0))[:8]
        return {"name": self.name, "built": self.built(), "index": d["index"], "quality": d["quality"], "verification": prov.get("verification") or {}, "stats": prov.get("stats") or {},
                "origin_words": ORIGIN_WORDS, "levels": self.levels(d), "classes": [{"name": c["name"], "parent": c.get("parent"), "definition": c.get("definition"), "level": c.get("knowledgeLevel"), "depth": class_level.get(c["name"]), "source": c.get("source"),
                                                                           "count": d["index"]["byType"].get(c["name"], 0)} for c in onto["classes"]],
                "relationships": [{"name": r["name"], "domain": r["domain"], "range": r["range"], "definition": r.get("definition"), "source": r.get("source"), "count": d["index"]["byPredicate"].get(r["name"], 0)}
                                  for r in onto["relationships"]],
                "sources": {"cases": len(self.sources("cases")), "imports": self.imports(), "documents": len(prov.get("documents") or [])},
                "known": [{"id": e["id"], "type": e["type"], "name": e["name"], "cases": e["props"].get("seenInCases") or 0} for e in top if e["props"].get("seenInCases")],
                "format": {"name": "KB Forge knowledge base", "schemaVersion": SCHEMA}}

    def levels(self, d: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """The four levels as boxes: how much each knows, and the entities that head it."""
        d = d or self.load()
        out = []
        for key in (*LEVEL_ORDER, "added"):
            members = [e for e in d["entities"].values() if level_of(e) == key]
            if key == "added" and not members:
                continue
            top = min((depth_of(e) for e in members), default=99)
            heads = [e for e in members if depth_of(e) == top] if top < 99 else []
            out.append({"id": key, "name": O.LEVELS.get(key, "Added knowledge"), "say": O.LEVEL_SAYS.get(key, "Knowledge that was added without a level. Choose a level for it, or let a case meet it."),
                        "entities": len(members), "heads": len(heads), "classes": Counter(e["type"] for e in members).most_common(8)})
        return out

    def level_map(self, open_levels: list[str] | None = None, drilled: list[str] | None = None, cap: int = 30) -> dict[str, Any]:
        """The scene of the level map: the heads of every open level, and under each drilled entity what sits below it. Drilling only ever goes
        down: from an industry to its use cases, from a use case to its documents, rules and cases, from a case to what it holds."""
        d = self.load()
        ents, origins = d["entities"], d["provenance"].get("origins") or {"entities": {}, "triples": {}}
        adj: dict[str, set[str]] = defaultdict(set)
        for t in d["triples"]:
            adj[t["subject"]].add(t["object"])
            adj[t["object"]].add(t["subject"])
        order = {k: i for i, k in enumerate((*LEVEL_ORDER, "added"))}

        def below(eid: str) -> list[str]:
            e = ents[eid]
            kids = [n for n in adj[eid] if depth_of(ents[n]) > depth_of(e) or (depth_of(ents[n]) == depth_of(e) == 99 and order[level_of(ents[n])] > order[level_of(e)])]
            return sorted(kids, key=lambda n: (depth_of(ents[n]), ents[n]["type"], -len(adj[n]), ents[n]["name"]))

        scene: dict[str, str | None] = {}   # entity -> the entity it was drilled from
        for key in open_levels or []:
            members = [e for e in ents.values() if level_of(e) == key]
            top = min((depth_of(e) for e in members), default=99)
            heads = [e for e in members if depth_of(e) == top] if top < 99 else sorted(members, key=lambda e: -len(adj[e["id"]]))
            for e in sorted(heads, key=lambda e: (-len(adj[e["id"]]), e["name"]))[:cap]:
                scene.setdefault(e["id"], None)
        more: dict[str, int] = {}
        for eid in drilled or []:
            if eid not in ents:
                continue
            scene.setdefault(eid, None)
            kids = below(eid)
            for k in kids[:cap]:
                scene.setdefault(k, eid)
            more[eid] = max(0, len(kids) - cap)
        nodes = [{"id": eid, "type": ents[eid]["type"], "name": ents[eid]["name"], "level": level_of(ents[eid]), "depth": depth_of(ents[eid]), "origin": origins["entities"].get(eid, "unknown"),
                  "stub": ents[eid]["stub"], "below": len(below(eid)), "from": parent, "drilled": eid in (drilled or []), "more": more.get(eid, 0)} for eid, parent in scene.items()]
        links = [{"s": t["subject"], "p": t["predicate"], "o": t["object"]} for t in d["triples"] if t["subject"] in scene and t["object"] in scene]
        return {"levels": self.levels(d), "nodes": nodes, "links": links, "open": list(open_levels or []), "drilled": [x for x in drilled or [] if x in ents]}

    def grounding(self, use_case: str, classes: list[str], cap: int = 500) -> dict[str, Any]:
        """What the harness hands an agent from the graph before it runs: the nodes of the classes its contract names, for the case's use case
        (its kinds of document, its rules, its references), and for the workspace's own classes everything known so far."""
        d = self.load()
        ents = d["entities"]
        uc = O.entity_id("UseCase", use_case)
        near: set[str] = set()
        for t in d["triples"]:
            if uc in (t["subject"], t["object"]):
                near.add(t["object"] if t["subject"] == uc else t["subject"])
        for t in d["triples"]:   # one step further for what hangs under a use case's own nodes: the lines of its references
            if t["subject"] in near and ents[t["object"]]["type"] == "ReferenceEntry":
                near.add(t["object"])
        wide = {"Organization", "Product"}   # the workspace's knowledge is not tied to one use case
        got = [e for e in ents.values() if e["type"] in classes and (e["id"] in near or e["type"] in wide) and not e["stub"]][:cap]
        return {"nodes": len(got), "by_class": dict(Counter(e["type"] for e in got)), "by_level": dict(Counter(level_of(e) for e in got)), "ids": [e["id"] for e in got[:40]]}

    def signals(self, profile: Profile) -> dict[str, list[str]]:
        """Other names of a use case's kinds of document that added knowledge states: the classifier reads them as extra signals."""
        ents = self.load()["entities"]
        out: dict[str, list[str]] = {}
        for t in profile.types.values():
            e = ents.get(O.entity_id("Document", t.get("name") or t["id"]))
            if e and any(str(m).startswith("import:") for m in e["sourceModules"]):
                have = {str(x).lower() for x in t.get("signals") or []} | {str(t.get("name") or "").lower()}
                extra = [x.lower() for x in e["synonyms"] if len(x) > 3 and x.lower() not in have]
                if extra:
                    out[t["id"]] = extra[:12]
        return out

    def subgraph(self, *, levels: list[str] | None = None, types: list[str] | None = None, focus: str | None = None, limit: int = 220) -> dict[str, Any]:
        d = self.load()
        ents, origins = d["entities"], d["provenance"].get("origins") or {"entities": {}, "triples": {}}
        if focus and focus in ents:
            keep = {focus}
            for t in d["triples"]:
                if t["subject"] == focus:
                    keep.add(t["object"])
                elif t["object"] == focus:
                    keep.add(t["subject"])
        else:
            keep = {eid for eid, e in ents.items() if (not levels or level_of(e) in levels) and (not types or e["type"] in types)}
        degree = Counter()
        for t in d["triples"]:
            if t["subject"] in keep and t["object"] in keep:
                degree[t["subject"]] += 1
                degree[t["object"]] += 1
        chosen = set(sorted(keep, key=lambda x: (x != focus, -degree[x], x))[:limit])
        links = [{"s": t["subject"], "p": t["predicate"], "o": t["object"], "origin": origins["triples"].get(f"{t['subject']}|{t['predicate']}|{t['object']}", "unknown")}
                 for t in d["triples"] if t["subject"] in chosen and t["object"] in chosen]
        return {"nodes": [{"id": eid, "type": ents[eid]["type"], "name": ents[eid]["name"], "level": level_of(ents[eid]), "origin": origins["entities"].get(eid, "unknown"),
                           "degree": degree[eid], "stub": ents[eid]["stub"]} for eid in sorted(chosen)], "links": links, "total": len(keep), "shown": len(chosen), "focus": focus}

    def entity(self, eid: str) -> dict[str, Any]:
        d = self.load()
        e = d["entities"].get(eid)
        if e is None:
            raise KeyError(f"no entity '{eid}' in the knowledge base")
        prov = d["provenance"]
        cits = {c["id"]: c for c in prov["citations"]}
        origins = prov.get("origins") or {"entities": {}, "triples": {}}
        why = lambda sups: [{**cits.get(s["citation"], {}), "section": s.get("section"), "how": s.get("how"), "check": s.get("check")} for s in sups or []]  # noqa: E731
        links = []
        for t in d["triples"]:
            if eid in (t["subject"], t["object"]):
                other = t["object"] if t["subject"] == eid else t["subject"]
                key = f"{t['subject']}|{t['predicate']}|{t['object']}"
                links.append({"direction": "out" if t["subject"] == eid else "in", "predicate": t["predicate"], "other": other, "other_name": d["entities"][other]["name"], "other_type": d["entities"][other]["type"],
                              "props": t["props"], "origin": origins["triples"].get(key, "unknown"), "support": why(prov["triple_support"].get(key))[:3]})
        cls = next((c for c in d["ontology"]["classes"] if c["name"] == e["type"]), {})
        return {"entity": e, "level": level_of(e), "also_at": [O.KB_FORGE_LEVEL[x] for x in O.kb_forge_levels(e["props"].get("knowledgeLevel"))[1:]],
                "class": {"name": e["type"], "parent": cls.get("parent"), "definition": cls.get("definition")}, "origin": origins["entities"].get(eid, "unknown"),
                "support": why(prov["entity_support"].get(eid)), "links": sorted(links, key=lambda x: (x["predicate"], x["other_name"]))}

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = O.normalize_name(query)
        if not q:
            return []
        hits = []
        for e in self.load()["entities"].values():
            names = [O.normalize_name(e["name"]), *(O.normalize_name(s) for s in e.get("synonyms") or [])]
            score = max((3 if n == q else 2 if n.startswith(q) else 1 if q in n else 0) for n in names)
            if not score and q in O.normalize_name(e["props"].get("description")):
                score = 0.5
            if score:
                hits.append((score, e))
        return [{"id": e["id"], "type": e["type"], "name": e["name"], "description": (e["props"].get("description") or "")[:160], "cases": e["props"].get("seenInCases")}
                for _, e in sorted(hits, key=lambda x: (-x[0], x[1]["name"]))[:limit]]

    def property_graph(self) -> dict[str, Any]:
        """The graph as KB Forge's own viewer and its Neo4j script read it: nodes {id, labels, props}, rels {id, type, from, to, props}."""
        d = self.load()
        parents = {c["name"]: c.get("parent") for c in d["ontology"]["classes"]}
        origins = d["provenance"].get("origins") or {"entities": {}, "triples": {}}

        def labels(cls: str) -> list[str]:
            out, cur = [cls], parents.get(cls)
            while cur and cur not in out:
                out.append(cur)
                cur = parents.get(cur)
            return [*out, "Entity"]

        nodes = [{"id": e["id"], "labels": labels(e["type"]), "props": {"name": e["name"], **e["props"], "synonyms": e["synonyms"], "origin": origins["entities"].get(e["id"], "unknown"), "stub": e["stub"]}}
                 for e in d["entities"].values()]
        rels = []
        for t in d["triples"]:
            key = f"{t['subject']}|{t['predicate']}|{t['object']}"
            sup = d["provenance"]["triple_support"].get(key) or []
            rels.append({"id": key, "type": O.screaming_snake(t["predicate"]), "from": t["subject"], "to": t["object"],
                         "props": {"relation": t["predicate"], **t["props"], "origin": origins["triples"].get(key, "unknown"), "citationIds": [s["citation"] for s in sup]}})
        return {"nodes": nodes, "rels": rels}

    def export_zip(self) -> bytes:
        """The knowledge base as KB Forge imports it (Import a graph -> a KB Forge knowledge base .zip), with a Neo4j script and a plain JSON graph beside it."""
        d = self.load()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(self.root.rglob("*")):
                rel = p.relative_to(self.root).as_posix()
                if p.is_file() and not rel.startswith("sources/") and not rel.startswith("memory/") and not rel.endswith(".tmp"):
                    z.write(p, rel)
            pg = self.property_graph()
            z.writestr("neo4j/knowledge_graph.cypher", _cypher(pg))
            z.writestr("import/graph.json", json.dumps({"app": "DocuInsights", "project": self.name, "exported_at": now(),
                                                        "nodes": [{"id": e["id"], "type": e["type"], "name": e["name"], "description": e["props"].get("description", ""), "aliases": e["synonyms"],
                                                                   "props": {k: v for k, v in e["props"].items() if k != "description"}} for e in d["entities"].values()],
                                                        "edges": [{"from": t["subject"], "to": t["object"], "relation": t["predicate"]} for t in d["triples"]],
                                                        "ontology": {"classes": [{"name": c["name"], "parent": c.get("parent"), "description": c.get("definition")} for c in d["ontology"]["classes"]],
                                                                     "relations": [{"name": r["name"], "domain": r["domain"], "range": r["range"], "description": r.get("definition")} for r in d["ontology"]["relationships"]]}},
                                                       ensure_ascii=False))
            z.writestr("README.md", _readme(self.name, d))
        return buf.getvalue()


def _cypher(pg: dict[str, Any]) -> str:
    def lit(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, list):
            return "[" + ", ".join(lit(x) for x in v if isinstance(x, (str, int, float, bool))) + "]"
        return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ") + "'"

    out = ["// DocuInsights knowledge base. Paste into Neo4j Browser or AuraDB Query. Everything is MERGEd on id.", "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE;"]
    for n in pg["nodes"]:
        props = ", ".join(f"n.`{k}` = {lit(v)}" for k, v in n["props"].items() if v is not None and not isinstance(v, dict))
        out.append(f"MERGE (n:Entity {{id: {lit(n['id'])}}}) SET n:{':'.join('`' + x + '`' for x in n['labels'])}" + (f", {props}" if props else "") + ";")
    for r in pg["rels"]:
        props = ", ".join(f"`{k}`: {lit(v)}" for k, v in r["props"].items() if v is not None and not isinstance(v, dict))
        out.append(f"MATCH (a:Entity {{id: {lit(r['from'])}}}), (b:Entity {{id: {lit(r['to'])}}}) MERGE (a)-[:`{r['type']}` {{{props}}}]->(b);")
    return "\n".join(out) + "\n"


def _readme(name: str, d: dict[str, Any]) -> str:
    idx, q = d["index"], d["quality"]
    return (f"# {name}\n\nA knowledge base written by DocuInsights {__version__} in the KB Forge knowledge-base layout (schema {SCHEMA}).\n\n"
            f"* {idx['entities']} entities, {idx['triples']} relationships, quality score {q.get('score')}\n"
            "* `graph/entities.jsonl` and `graph/triples.jsonl` are the source of truth; `graph/provenance.json` holds what supports each of them\n"
            "* `ontology/ontology_merged.json` is the ontology; `ontology/custom/docuinsights.json` is only what it adds to KB Forge's own\n"
            "* `neo4j/knowledge_graph.cypher` loads the graph into Neo4j; `import/graph.json` is the same graph as plain nodes and edges\n\n"
            "To open it in KB Forge: Knowledge bases -> Import a graph -> upload this zip.\n\n"
            "The quality score follows KB Forge's formula except its last component: where KB Forge asks a model how well the graph answers its competency questions, "
            "this graph reports the share of entities and links whose evidence was found (15%).\n")
