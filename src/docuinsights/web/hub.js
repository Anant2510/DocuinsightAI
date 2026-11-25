/* DocuInsights workbench: one page over the case API. No framework and no external script: views are functions of the
   case JSON, redrawn when it changes. Everything a screen shows comes from the API; nothing is computed here. */
(function () {
  "use strict";
  const root = document.getElementById("app"), BASE = root.dataset.base || "";
  const S = { cfg: null, cases: [], c: null, view: "home", sel: {}, chat: false, chatLog: [], cf: null, draft: null, fb: null, timer: null, filter: { status: "attention", family: "all" }, layers: { document: true, entity: true, reference: true, reasoning: false, assertion: false }, k: { ov: null, g: null, m: null, e: null, view: "map", open: ["industry", "domain", "solution", "customer"], drill: [], levels: ["industry", "domain"], hits: null, q: "", place: "" }, pf: null,
    orch: { t: null, playing: false, speed: 1, auto: false, sel: null, timer: null } };

  // ---------------------------------------------------------------------------------------------- helpers
  const SVG = new Set(["svg", "g", "line", "circle", "text", "title", "rect", "path"]);
  function h(tag, attrs) {
    const el = document.createElementNS(SVG.has(tag) ? "http://www.w3.org/2000/svg" : "http://www.w3.org/1999/xhtml", tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v); else if (k === "class") el.setAttribute("class", v); else if (k === "value" && "value" in el) el.value = v; else el.setAttribute(k, v === true ? "" : v);
    }
    for (let i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, kid) { if (kid === null || kid === undefined || kid === false) return; if (Array.isArray(kid)) kid.forEach((k) => add(el, k)); else el.appendChild(kid.nodeType ? kid : document.createTextNode(String(kid))); }
  // Who is asked for a credential is decided by the page, before the first call: on its own this installation's API key and nothing else
  // is sent (a host's token left in this browser by another application on the same address is not); mounted in a host, the host's token.
  const KEYED = root.dataset.auth !== "host";
  let ownKey = "";
  const token = () => { try { return KEYED ? ownKey || sessionStorage.getItem("docuinsights.key") || "" : localStorage.getItem("cxnova.shop.admin") || localStorage.getItem("cxnova.shop.token") || ""; } catch (e) { return KEYED ? ownKey : ""; } };
  async function api(path, body, method) {
    const headers = {}; const t = token(); if (t) headers.Authorization = "Bearer " + t;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(BASE + "/api/" + path, { method: method || (body !== undefined ? "POST" : "GET"), headers, body: body !== undefined ? JSON.stringify(body) : undefined });
    let data = null; try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) { const err = new Error((data && data.detail) || res.status + " " + res.statusText); err.status = res.status; throw err; }
    return data;
  }
  function toast(msg) { const t = h("div", { class: "toast", role: "status" }, msg); document.body.appendChild(t); setTimeout(() => t.remove(), 4200); }
  const run = (fn) => async (e) => { if (e && e.preventDefault) e.preventDefault(); try { await fn(e); } catch (err) { if (err.status === 401) return signIn(err.message); toast(err.message); } };
  const pill = (status, label) => h("span", { class: "pill " + (status || "") }, label || status);
  const when = (ts) => ts ? new Date(ts).toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  const prof = () => S.cfg.profiles.find((p) => p.id === (S.c ? S.c.profile : (S.sel.profile || S.cfg.profiles[0].id)));
  const typeName = (id) => { const t = prof().document_types.find((x) => x.id === id); return t ? t.name : (id || "Unclassified"); };
  const A = () => (S.c && S.c.assessment) || null;
  const F = (pred) => (A() ? A().findings.filter(pred) : []);
  const section = (title, lead) => [h("div", { class: "page-h" }, h("h1", null, title)), lead ? h("p", { class: "lead" }, lead) : null];
  function cardOf(title) { const c = h("div", { class: "card" }, title ? h("h3", null, title) : null); for (let i = 1; i < arguments.length; i++) add(c, arguments[i]); return c; }
  const kv = (pairs) => h("dl", { class: "kv" }, pairs.filter((p) => p && p[1] !== undefined && p[1] !== null && p[1] !== "").map(([k, v]) => [h("dt", null, k), h("dd", null, v)]));
  const steps = (list) => (list && list.length ? h("ul", { class: "steps" }, list.filter(Boolean).map((s) => h("li", null, s))) : null);
  function form(title, fields, submit) {
    return new Promise((resolve) => {
      const vals = {}; let box;
      const close = (v) => { box.remove(); resolve(v); };
      const inputs = fields.map((f) => {
        let el;
        if (f.options) el = h("select", { onchange: (e) => (vals[f.k] = e.target.value) }, f.options.map((o) => h("option", { value: o[0], selected: o[0] === f.value }, o[1])));
        else if (f.type === "textarea") el = h("textarea", { oninput: (e) => (vals[f.k] = e.target.value) });
        else el = h("input", { type: f.type === "date" ? "date" : f.type === "password" ? "password" : "text", autocomplete: f.type === "password" ? "off" : null, value: f.value || "", placeholder: f.placeholder || "", oninput: (e) => (vals[f.k] = e.target.value) });
        vals[f.k] = f.value || (f.options ? f.options[0][0] : "");
        return h("label", { class: "f" }, h("span", null, f.label), el);
      });
      box = h("div", { class: "modal", onclick: (e) => { if (e.target === box) close(null); } }, h("div", { role: "dialog", "aria-label": title },
        h("form", { class: "stack", onsubmit: (e) => { e.preventDefault(); close(vals); } }, h("h3", { style: "font-size:16px" }, title), inputs,
          h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit" }, submit || "Save"), h("button", { class: "btn", type: "button", onclick: () => close(null) }, "Cancel")))));
      document.body.appendChild(box); const first = box.querySelector("input,select,textarea"); if (first) first.focus();
    });
  }
  let asking = false;
  async function signIn(message) {
    if (!KEYED) { toast("Sign in to the host portal first, then reload this page. " + (message || "")); return; }
    if (asking) return;   // several calls can fail at once: one question
    asking = true;
    const tried = !!token();
    ownKey = ""; try { sessionStorage.removeItem("docuinsights.key"); } catch (e) { /* private window */ }
    const v = await form("This installation needs its API key", [{ k: "key", type: "password", label: tried ? "That key was not accepted. Enter the API key of this installation." : "API key", placeholder: "API key" }], "Continue");
    asking = false;
    if (v && v.key) { ownKey = v.key.trim(); try { sessionStorage.setItem("docuinsights.key", ownKey); } catch (e) { /* private window: kept for this page only */ } start(); }
  }

  // ---------------------------------------------------------------------------------------------- data
  async function start() {
    try { S.cfg = await api("config"); S.cases = await api("cases"); } catch (err) { if (err.status === 401) { root.replaceChildren(h("p", { class: "boot" }, "Waiting for a key…")); return signIn(err.message); } root.replaceChildren(h("p", { class: "boot" }, err.message)); return; }
    render();
  }
  async function open(ref, view) { clearInterval(S.orch.timer); S.orch = { t: null, playing: false, speed: S.orch.speed || 1, auto: !!S.orch.auto, sel: null, timer: null, ticks: 0 }; S.c = await api("cases/" + encodeURIComponent(ref)); S.view = view || (A() ? "summary" : "monitor"); S.sel = {}; S.cf = null; S.draft = null; S.chatLog = (S.c.chat || []).flatMap((m) => [{ r: "u", t: m.question }, { r: "a", t: m.answer, no: !m.grounded }]); watch(); render(); }
  function setCase(c, view) { S.c = c; if (view) S.view = view; watch(); render(); }
  function watch() {
    clearTimeout(S.timer);
    if (!S.c || (S.c.progress || {}).state !== "running") return;
    S.timer = setTimeout(async () => { try { const c = await api("cases/" + encodeURIComponent(S.c.reference)); S.orch.ticks = (S.orch.ticks || 0) + 1; S.c = c; render(); watch(); } catch (e) { /* retry on the next tick */ watch(); } }, 700);
  }
  const go = (view) => () => { if (view !== "monitor") { clearInterval(S.orch.timer); S.orch.playing = false; } S.view = view; render(); window.scrollTo(0, 0); };
  function openSource(s) { if (!s.doc || s.doc === "case") return; S.view = "documents"; S.sel.doc = s.doc; S.sel.line = s.page ? { page: s.page, line: s.line } : null; render(); }

  // ---------------------------------------------------------------------------------------------- shell
  const TOP = [["home", "Home"], ["cases", "Cases"], ["knowledge", "Knowledge"], ["agents", "Agents"], ["platform", "How it is governed"]];
  const mapQuery = () => "open=" + S.k.open.join(",") + S.k.drill.map((d) => "&drill=" + encodeURIComponent(d)).join("");
  const top = (view) => run(async () => {   // a screen of the workspace (no case open): load what it shows, then draw it
    clearTimeout(S.timer); clearInterval(S.orch.timer); S.orch.playing = false; S.c = null; S.sel = {};
    if (view === "home" || view === "cases") S.cases = await api("cases");
    if (view === "knowledge") { S.k.ov = await api("knowledge"); S.k.m = await api("knowledge/map?" + mapQuery());
      if (!S.k.touched && !S.k.drill.length) { S.k.drill = S.k.m.levels.filter((l) => l.heads === 1).map((l) => (S.k.m.nodes.find((n) => n.level === l.id && !n.from) || {}).id).filter(Boolean); if (S.k.drill.length) S.k.m = await api("knowledge/map?" + mapQuery()); } S.k.g = S.k.view === "network" ? await api("knowledge/graph?levels=" + S.k.levels.join(",")) : null; S.k.e = null; S.k.hits = null; }
    if (view === "platform") S.pf = await api("platform");
    S.view = view; render(); window.scrollTo(0, 0);
  });
  function render() {
    const p = prof(), a = A(), running = S.c && (S.c.progress || {}).state === "running";
    const bar = h("header", { class: "top" },
      h("button", { class: "brand", onclick: top("home") }, h("img", { src: BASE + "/static/mark.svg", alt: "" }), h("b", null, S.cfg.product)),
      h("nav", { class: "tabs", "aria-label": "Workspace" }, TOP.map(([id, label]) => h("button", { "aria-current": String(!S.c && (S.view === id || (id === "cases" && S.view === "new"))), onclick: top(id) }, label))),
      S.c ? h("span", { class: "ws" }, p.brand.workspace || p.name, p.brand.client_label ? " · " + p.brand.client_label : "") : null,
      h("span", { class: "right" }), h("span", { class: "tag", title: "The model used for reading and narrative. Rules and the recommendation are code." }, S.cfg.model.offline ? "No model: patterns and rules" : "Model: " + S.cfg.model.model + (S.cfg.model.status ? " · " + S.cfg.model.status : "")),
      h("span", { class: "tag" }, "Repository: " + S.cfg.repository.kind), S.cfg.links.portal ? h("a", { class: "tag", href: S.cfg.links.portal, style: "text-decoration:none" }, "CX Nova portal") : null,
      h("span", { class: "tag demo" }, "Demonstration · synthetic data"));
    const views = { home, cases, new: newCase, agents, knowledge, platform, summary, documents, graph, evidence, consistency, reference, policy, provenance, whatif, monitor, decision, audit };
    const main = h("main", { class: "main" });
    if (S.c && !a && !["monitor", "documents"].includes(S.view)) S.view = "monitor";
    add(main, (views[S.view] || home)());
    const shell = h("div", { class: "shell" + (S.c ? "" : " wide") }, S.c ? rail(running) : null, main);
    root.replaceChildren(...[bar, shell, S.c && a ? chat() : null].filter(Boolean));
  }
  function rail(running) {
    const a = A(), count = (pred) => F(pred).length, n = (v, cls) => (v ? h("span", { class: "n " + (cls || "") }, v) : null);
    const item = (id, label, badge) => h("button", { "aria-current": String(S.view === id), onclick: go(id) }, label, badge);
    const st = (f) => ["fail", "missing", "review"].includes(f.status);
    return h("nav", { class: "rail", "aria-label": "Case" },
      h("div", { class: "case" }, h("div", { class: "ref" }, S.c.reference), h("div", { class: "st" }, running ? "Assessing…" : S.c.status), S.c.sample ? h("div", { class: "st" }, "Sample: " + S.c.sample.title) : null),
      h("h4", null, "Case"), item("summary", "Intelligence summary"), item("documents", "Documents and classification", n(S.c.documents.filter((d) => !d.removed && d.classification && !d.classification.agrees && !d.review).length, "warn")),
      item("evidence", "Evidence completeness", n(count((f) => f.family === "evidence" && f.status === "missing"), "bad")),
      item("consistency", "Cross-document consistency", n(count((f) => f.agent === "contradiction" && st(f)), "bad")),
      prof().reference_sources.length ? item("reference", "Classification assessment", n(count((f) => f.agent === "reference" && f.status === "review"), "warn")) : null,
      item("policy", "Policy and temporal checks", n(count((f) => f.agent === "policy" && st(f)), "bad")),
      h("h4", null, "Explain"), item("graph", "Entity relationship graph"), item("provenance", "Reasoning and provenance"), item("whatif", "Counterfactual simulator"),
      h("h4", null, "Operate"), item("monitor", "Agent orchestration", running ? h("span", { class: "spin right" }) : null), item("decision", "Decision workspace", n(a && !S.c.decision ? 1 : 0, "warn")), item("audit", "Feedback and audit"));
  }

  // ---------------------------------------------------------------------------------------------- home, new case, agents
  const tryIt = (p, s) => run(async () => { const c = await api("samples", { profile: p.id, sample: s.id }); S.cases = await api("cases"); S.orch = { t: null, playing: false, speed: 1, auto: true, sel: null, timer: null }; open(c.reference, "monitor"); });
  const outcomePill = (c) => (c.label ? pill({ proceed: "pass", review: "fail", request_evidence: "review" }[c.outcome], c.label) : "–");
  function home() {
    const how = [["Put the documents in", "A case is a handful of documents and a few facts about it. PDFs, scans or text."],
      ["Agents read and link them", "Each document is named, its facts are lifted with the page and line they came from, and the same company or reference number is joined across documents."],
      ["Rules check them", "Is anything missing? Do the dates and amounts hold? Do the documents agree with each other? These checks are code, never a model's opinion."],
      ["A person decides", "You get one of three recommendations with its reasons. Every reason opens the line it rests on. Nothing is decided for you."]];
    const base = [["Agent contracts", "Every agent has a written contract: what it needs, what it promises, what it must never do.", "agents"],
      ["Agent harness", "One harness runs every agent, checks its contract before and after, and records the run.", "platform"],
      ["Shared memory", "Agents leave notes for each other, and the workspace recognises what an earlier case already held.", "platform"],
      ["Knowledge graph", "Everything learned is one graph that grows with every case, kept in the KB Forge format.", "knowledge"],
      ["Evidence provenance", "Every conclusion points to a line of a document, and every action is in a tamper-evident ledger.", "platform"],
      ["Throttling", "Model calls are rate limited and budgeted per agent. At the limit an agent falls back; it does not fail.", "platform"]];
    return [h("div", { class: "hero" }, h("h1", null, "Give it the documents. Get back a recommendation you can check."),
        h("p", null, S.cfg.product + " reads a set of documents, links what they say, checks them against your rules, and tells a person what to do next, with the line behind every conclusion."),
        h("div", { class: "row" }, h("button", { class: "btn accent", onclick: () => document.getElementById("usecases").scrollIntoView({ behavior: "smooth" }) }, "Try a use case"), h("button", { class: "btn", onclick: go("new") }, "Use my own documents"))),
      h("h2", { class: "sub" }, "How it works"),
      h("div", { class: "grid g4" }, how.map(([t, d], i) => h("div", { class: "how" }, h("span", { class: "no" }, i + 1), h("h3", null, t), h("p", null, d)))),
      h("h2", { class: "sub", id: "usecases" }, "Pick a use case"),
      h("p", { class: "lead" }, "The same agents run every one of them. A use case is a configuration: the kinds of document, the evidence it asks for and its rules. Each comes with invented sample cases to try."),
      h("div", { class: "grid g3", style: "align-items:start" }, S.cfg.profiles.map((p) => h("div", { class: "uc" }, h("div", { class: "row" }, p.sector ? h("span", { class: "sector" }, p.sector) : null),
        h("h3", null, p.name), h("p", null, p.plain || p.description), h("div", { class: "small muted" }, p.document_types.length + " kinds of document · " + p.rules.length + " rules · " + (p.consistency || []).length + " cross-checks"),
        h("div", { class: "samples" }, p.samples.map((s) => h("button", { class: "sample", onclick: tryIt(p, s), title: s.story }, h("b", null, s.title), h("span", null, s.story), h("i", null, "Try it →")))),
        h("button", { class: "btn sm ghost", onclick: () => { S.sel.draft = { profile: p.id, reference: "", fields: {}, files: [] }; go("new")(); } }, "Use my own documents"))),
        h("div", { class: "uc own" }, h("div", { class: "row" }, h("span", { class: "sector" }, "Any industry")), h("h3", null, "Your use case"),
          h("p", null, "Claims, onboarding, lending, procurement, compliance: anything that arrives as a set of documents to check."), h("p", { class: "small muted" }, "A new use case is one configuration file. No code changes, no new agents."))),
      h("h2", { class: "sub" }, "What every agent runs on"),
      h("div", { class: "grid g3" }, base.map(([t, d, v]) => h("button", { class: "found", onclick: top(v) }, h("h3", null, t), h("p", null, d)))),
      S.cases.length ? [h("h2", { class: "sub" }, "Recent cases"), cardOf(null, h("table", null, h("tbody", null, S.cases.slice(0, 5).map((c) => h("tr", { class: "click", onclick: run(() => open(c.reference)) }, h("td", { class: "mono" }, c.reference),
        h("td", null, (S.cfg.profiles.find((p) => p.id === c.profile) || {}).name || c.profile), h("td", null, outcomePill(c)), h("td", { class: "small muted" }, when(c.assessed_at)))))), h("button", { class: "btn sm ghost", style: "margin-top:6px", onclick: top("cases") }, "All cases"))] : null];
  }
  function cases() {
    const by = (o) => S.cases.filter((c) => c.outcome === o).length;
    return [section("Cases", "Every case in this workspace. Open one, or start a new one."),
      h("div", { class: "grid g4", style: "margin-bottom:16px" }, [["Cases", S.cases.length], ["Ready", by("proceed")], ["Something to request", by("request_evidence")], ["Referred to a person", by("review")]].map(([l, v]) => h("div", { class: "tile" }, h("b", null, v), h("span", null, l)))),
      h("div", { class: "row", style: "margin-bottom:14px" }, h("button", { class: "btn primary", onclick: go("new") }, "Create a case"), h("button", { class: "btn", onclick: top("home") }, "Try a sample")),
      cardOf(null, S.cases.length ? h("table", null, h("thead", null, h("tr", null, ["Reference", "Use case", "Documents", "Recommendation", "Status", "Assessed"].map((x) => h("th", null, x)))),
        h("tbody", null, S.cases.map((c) => h("tr", { class: "click", onclick: run(() => open(c.reference)) }, h("td", { class: "mono" }, c.reference), h("td", null, (S.cfg.profiles.find((p) => p.id === c.profile) || {}).name || c.profile), h("td", null, c.documents),
          h("td", null, outcomePill(c)), h("td", null, c.status), h("td", { class: "small muted" }, when(c.assessed_at)))))) : h("p", { class: "muted" }, "No cases yet. Try a sample from the home page, or create a case with your own documents."))];
  }
  function newCase() {
    const d = S.sel.draft || (S.sel.draft = { profile: S.cfg.profiles[0].id, reference: "", fields: {}, files: [] });
    S.sel.profile = d.profile; const p = prof();
    const pick = async (files) => { for (const f of files) { const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.onerror = rej; r.readAsDataURL(f); }); d.files.push({ name: f.name, size: f.size, category: "", content_base64: b64 }); } render(); };
    const drop = h("div", { class: "drop", tabindex: 0, onclick: () => fileInput.click(), ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); }, ondragleave: () => drop.classList.remove("over"), ondrop: (e) => { e.preventDefault(); pick(e.dataTransfer.files); } },
      "Drop the evidence package here, or click to choose files", h("div", { class: "small" }, "PDF, PNG, JPEG or text, up to 15 MB each"));
    const fileInput = h("input", { type: "file", multiple: true, accept: ".pdf,.png,.jpg,.jpeg,.txt", style: "display:none", onchange: (e) => pick(e.target.files) });
    return [section("Create a case", "Register the case, give the case facts the rules need, and upload the evidence package. Each file is kept as an immutable version with its hash."),
      h("form", { class: "stack", onsubmit: run(async () => { const c = await api("cases", { reference: d.reference, profile: d.profile, fields: d.fields, documents: d.files, assess: true }); S.sel.draft = null; S.cases = await api("cases"); open(c.reference, "monitor"); }) },
        cardOf("Case", h("div", { class: "grid g3" }, h("label", { class: "f" }, h("span", null, "Use case"), h("select", { onchange: (e) => { d.profile = e.target.value; d.fields = {}; render(); } }, S.cfg.profiles.map((x) => h("option", { value: x.id, selected: x.id === d.profile }, x.name)))),
          h("label", { class: "f" }, h("span", null, p.case.reference_label || "Case reference"), h("input", { type: "text", required: true, value: d.reference, placeholder: p.case.reference_example || "", oninput: (e) => (d.reference = e.target.value.trim()) })),
          (p.case.fields || []).map((f) => h("label", { class: "f" }, h("span", null, f.name), h("input", { type: f.type === "date" ? "date" : "text", value: d.fields[f.id] || f.default || "", oninput: (e) => (d.fields[f.id] = e.target.value) }))))),
        cardOf("Evidence package", drop, fileInput, d.files.length ? h("table", { style: "margin-top:10px" }, h("thead", null, h("tr", null, ["File", "Size", "Uploaded as", ""].map((x) => h("th", null, x)))), h("tbody", null, d.files.map((f, i) => h("tr", null, h("td", null, f.name), h("td", { class: "small muted" }, Math.round(f.size / 1024) + " KB"),
          h("td", null, h("select", { onchange: (e) => (f.category = e.target.value) }, h("option", { value: "" }, "Other documents"), p.document_types.map((t) => h("option", { value: t.id, selected: f.category === t.id }, t.name)))), h("td", null, h("button", { class: "btn sm ghost", type: "button", onclick: () => { d.files.splice(i, 1); render(); } }, "Remove")))))) : null),
        h("div", { class: "row" }, h("button", { class: "btn primary", type: "submit", disabled: !d.files.length }, "Create and assess"), h("button", { class: "btn", type: "button", onclick: top("cases") }, "Cancel")))];
  }
  function agents() {
    const list = (title, items, cls) => (items && items.length ? h("div", { class: "clause " + (cls || "") }, h("h4", null, title), h("ul", null, items.map((x) => h("li", null, x)))) : null);
    return [section("The agents and their contracts", "One agent per job. Each has a contract the harness enforces on every run: what it needs before it starts, what it promises when it ends, what it must never do, and what it may spend. Nothing that decides may use a model."),
      h("div", { class: "grid g2" }, S.cfg.agents.map((a) => { const c = a.contract; return h("div", { class: "card contract" }, h("div", { class: "row" }, h("h3", { style: "margin:0" }, a.name), h("span", { class: "pill plain right" }, c.model.use === "none" ? "code only" : "may use a model")),
        h("p", { style: "margin:6px 0 10px" }, c.purpose),
        list("Needs before it starts", c.needs.map((n) => n.text)), list("Promises when it ends", c.promises.map((p) => p.text), "ok"), list("Never", c.never.map((n) => n.charAt(0).toUpperCase() + n.slice(1) + "."), "no"),
        h("div", { class: "small muted", style: "margin-top:8px" }, c.spend + " If it fails: " + c.on_failure_text.charAt(0).toLowerCase() + c.on_failure_text.slice(1) + " Contract v" + c.version + ".")); }))];
  }

  // ---------------------------------------------------------------------------------------------- knowledge
  const KCOL = { IndustrySegment: "#2c62c9", ExperienceDomain: "#0f5c3a", UseCase: "#1b7f52", Document: "#4a9c74", PolicyRule: "#8fbfa6", Role: "#c3d9cd", ReferenceSource: "#c79a1a", ReferenceEntry: "#e0c063", Accelerator: "#c4511a", SoftwareAgent: "#ee6c2b",
    Company: "#5a3794", Organization: "#7a4fb5", Product: "#a887d6", Case: "#3d2a6b", SourceDocument: "#8fa9d8", Identifier: "#b9a3dc", CaseFinding: "#c9c2d8" };
  const ORIGIN_PILL = { document: "pass", system: "info", settings: "info", web: "info", imported: "review", inferred: "", decision: "pass", unverified: "fail", unknown: "" };
  let kKey = "", kPos = null;
  function spread(nodes, links, W, H) {   // Fruchterman-Reingold with a deterministic start, as on the case graph
    const pos = {}, n0 = nodes.length || 1, k = Math.sqrt((W * H) / n0) * 0.7;
    nodes.forEach((n, i) => { const t = i * 2.399963, r = Math.sqrt((i + 0.5) / n0) * Math.min(W, H) * 0.46; pos[n.id] = { x: W / 2 + r * Math.cos(t) * 1.5, y: H / 2 + r * Math.sin(t) }; });
    const its = nodes.length > 160 ? 140 : 260;
    for (let it = 0; it < its; it++) {
      const f = {}, temp = 34 * (1 - it / its) + 0.6; nodes.forEach((n) => (f[n.id] = { x: 0, y: 0 }));
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) { const a = pos[nodes[i].id], b = pos[nodes[j].id], dx = a.x - b.x || 0.01, dy = a.y - b.y || 0.01, d = Math.max(Math.sqrt(dx * dx + dy * dy), 4), rp = (k * k) / d; f[nodes[i].id].x += (dx / d) * rp; f[nodes[i].id].y += (dy / d) * rp; f[nodes[j].id].x -= (dx / d) * rp; f[nodes[j].id].y -= (dy / d) * rp; }
      links.forEach((e) => { const a = pos[e.s], b = pos[e.o], dx = a.x - b.x, dy = a.y - b.y, d = Math.max(Math.sqrt(dx * dx + dy * dy), 4), at = (d * d) / k; f[e.s].x -= (dx / d) * at; f[e.s].y -= (dy / d) * at; f[e.o].x += (dx / d) * at; f[e.o].y += (dy / d) * at; });
      nodes.forEach((n) => { const p = pos[n.id], v = f[n.id], m = Math.sqrt(v.x * v.x + v.y * v.y) || 1; p.x += (v.x / m) * Math.min(m, temp) + (W / 2 - p.x) * 0.012; p.y += (v.y / m) * Math.min(m, temp) + (H / 2 - p.y) * 0.02; p.x = Math.min(W - 150, Math.max(24, p.x)); p.y = Math.min(H - 18, Math.max(18, p.y)); });
    }
    return pos;
  }
  const kEntity = (id) => run(async () => { S.k.e = await api("knowledge/entity?id=" + encodeURIComponent(id)); render(); });
  const kGraph = (query) => run(async () => { S.k.g = await api("knowledge/graph?" + query); render(); });
  const kMap = () => run(async () => { S.k.m = await api("knowledge/map?" + mapQuery()); render(); });
  const words = (name) => name.replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase();
  const LCOL = { industry: "#2c62c9", domain: "#1b7f52", solution: "#ee6c2b", customer: "#7a4fb5", added: "#7a8496" };
  const LVL = { industry: "Industry", domain: "Domain", solution: "Solution", customer: "Customer", added: "Added" };
  function levelMap() {   // KB Forge's level map: the levels as boxes, stacked top-down, each level's band to its right; drilling only goes down
    const m = S.k.m, W = 940, BOX = 168, X0 = BOX + 22, LAB = 104, PER = 4, COL = (W - X0 - LAB - 10) / PER, ROW = 36, sel = S.k.e ? S.k.e.entity.id : null, pos = {}, bands = [];
    let y = 8;
    m.levels.forEach((lv) => {
      const nodes = m.nodes.filter((n) => n.level === lv.id).sort((a, b) => a.depth - b.depth || a.type.localeCompare(b.type) || (a.from || "").localeCompare(b.from || "") || a.name.localeCompare(b.name));
      let row = -1, col = 0, kind = null; const rows = [];
      nodes.forEach((n) => { const k = n.depth + ":" + n.type; if (k !== kind) { row++; col = 0; kind = k; rows.push({ row, type: n.type }); } else if (col >= PER) { row++; col = 0; } pos[n.id] = { x: X0 + LAB + 10 + col * COL, y: y + 26 + row * ROW }; col++; });
      const heads = nodes.filter((n) => !n.from).length, rest = m.open.includes(lv.id) && lv.heads > heads ? lv.heads - heads : 0;   // a level shows its best connected heads; the rest are a search away
      const hgt = Math.max(74, 26 + (row + 1) * ROW + 4 + (rest ? 14 : 0));
      bands.push({ lv, y, hgt, nodes, rows, rest, heads, open: m.open.includes(lv.id) }); y += hgt + 10;
    });
    const H = y, near = new Set(m.links.filter((l) => l.s === sel || l.o === sel).flatMap((l) => [l.s, l.o]));
    const toggle = (id) => { S.k.touched = true; S.k.open = S.k.open.includes(id) ? S.k.open.filter((x) => x !== id) : [...S.k.open, id]; kMap()(); };
    const drill = (n) => run(async () => { S.k.touched = true; S.k.drill = S.k.drill.includes(n.id) ? S.k.drill.filter((x) => x !== n.id) : n.below ? [...S.k.drill, n.id] : S.k.drill; S.k.e = await api("knowledge/entity?id=" + encodeURIComponent(n.id)); S.k.m = await api("knowledge/map?" + mapQuery()); render(); });
    const curve = (a, b) => "M" + a.x + "," + a.y + " C" + a.x + "," + (a.y + b.y) / 2 + " " + b.x + "," + (a.y + b.y) / 2 + " " + b.x + "," + b.y;
    const cut = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
    return h("svg", { class: "graph lmap", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "The knowledge graph by level" },
      bands.map((b) => h("g", null, h("rect", { x: X0 - 6, y: b.y, width: W - X0 + 2, height: b.hgt, rx: 10, fill: LCOL[b.lv.id], opacity: 0.06 }),
        h("g", { class: "lbox", onclick: () => toggle(b.lv.id) }, h("rect", { x: 4, y: b.y, width: BOX, height: b.hgt, rx: 10, fill: "#fff", stroke: LCOL[b.lv.id], "stroke-width": b.open ? 2 : 1.2 }), h("rect", { x: 4, y: b.y, width: 6, height: b.hgt, rx: 3, fill: LCOL[b.lv.id] }),
          h("text", { x: 22, y: b.y + 25, class: "lname" }, b.lv.name), h("text", { x: 22, y: b.y + 43, class: "lsub" }, b.lv.entities.toLocaleString() + " entities · " + b.lv.heads + " at its head"),
          h("text", { x: 22, y: b.y + 60, class: "lsub", fill: LCOL[b.lv.id] }, b.open ? "− close this level" : "+ open this level"), h("title", null, b.lv.say)),
        b.rows.map((r) => h("text", { x: X0 + 6, y: b.y + 30 + r.row * ROW, class: "lrow" }, cut(words(r.type), 18))),
        b.rest ? h("text", { x: X0 + 6, y: b.y + b.hgt - 7, class: "lsub" }, "The " + b.heads + " best connected of " + b.lv.heads.toLocaleString() + " at the head of this level. Search for any other.") : null,
        !b.nodes.length ? h("text", { x: X0 + 12, y: b.y + 41, class: "lsub" }, b.lv.entities ? "Closed. Click the box to open it." : "Nothing at this level yet." + (b.lv.id === "customer" ? " It fills as cases are assessed." : "")) : null)),
      m.links.filter((l) => pos[l.s] && pos[l.o]).map((l) => { const tree = m.nodes.some((n) => (n.id === l.s && n.from === l.o) || (n.id === l.o && n.from === l.s)), hot = l.s === sel || l.o === sel;
        return h("path", { d: curve(pos[l.s], pos[l.o]), fill: "none", stroke: hot ? "#ee6c2b" : "#9aa3b2", "stroke-width": hot ? 1.6 : 1, opacity: hot ? 0.95 : tree ? 0.5 : 0.13, "stroke-dasharray": tree || hot ? "" : "3 3" }, h("title", null, words(l.p))); }),
      m.nodes.map((n) => h("g", { class: "nd" + (n.id === sel ? " sel" : ""), transform: "translate(" + pos[n.id].x + "," + pos[n.id].y + ")", onclick: drill(n) },
        h("rect", { x: -11, y: -13, width: COL - 6, height: 30, rx: 6, fill: "#fff", opacity: n.id === sel ? 0.95 : 0.001 }),
        n.drilled ? h("circle", { r: 10.5, fill: "none", stroke: LCOL[n.level], "stroke-width": 1.5 }) : null,
        h("circle", { r: 6.5, fill: KCOL[n.type] || LCOL[n.level], stroke: "#fff", "stroke-width": 1.5, opacity: sel && !near.has(n.id) && n.id !== sel ? 0.5 : 1, "stroke-dasharray": n.stub ? "2 2" : "" }),
        h("text", { x: 14, y: n.below || n.more ? 1 : 4 }, cut(n.name, 22)), n.more ? h("text", { x: 14, y: 13, class: "plus" }, n.more + " more below, not shown") : n.below ? h("text", { x: 14, y: 13, class: "plus" }, n.drilled ? "− " + n.below + " shown below" : "+ " + n.below + " below") : null,
        h("title", null, words(n.type) + ": " + n.name + (n.below ? " · " + n.below + " below it" : "")))));
  }
  function knowledge() {
    const ov = S.k.ov, e = S.k.e, idx = ov.index, ver = ov.verification || {}, st = ver.stats || {}, W = 1100, H = 600, map = S.k.view === "map", g = S.k.g;
    const checked = (st.checked_entities || 0) + (st.checked_relationships || 0), found = checked - (st.missing || 0) - (st.unchecked || 0), levelName = Object.fromEntries(ov.levels.map((l) => [l.id, l.name]));
    let svg;
    if (map) svg = levelMap();
    else {
      const key = g.nodes.length + ":" + g.links.length + ":" + (g.focus || "") + ":" + S.k.levels.join("");
      if (key !== kKey) { kPos = spread(g.nodes, g.links, W, H); kKey = key; }
      const sel = e ? e.entity.id : g.focus, near = new Set(g.links.filter((l) => l.s === sel || l.o === sel).flatMap((l) => [l.s, l.o]));
      svg = h("svg", { class: "graph", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Knowledge graph" },
        g.links.map((l) => h("line", { x1: kPos[l.s].x, y1: kPos[l.s].y, x2: kPos[l.o].x, y2: kPos[l.o].y, class: l.s === sel || l.o === sel ? "hot" : "" }, h("title", null, words(l.p)))),
        g.nodes.map((n) => h("g", { class: "nd" + (n.id === sel ? " sel" : ""), transform: "translate(" + kPos[n.id].x + "," + kPos[n.id].y + ")", onclick: kEntity(n.id) },
          h("circle", { r: n.type === "UseCase" ? 10 : Math.min(9, 4.5 + Math.sqrt(n.degree)), fill: KCOL[n.type] || LCOL[n.level] || "#7a8496", stroke: "#fff", "stroke-width": 1.5, opacity: sel && !near.has(n.id) && n.id !== sel ? 0.45 : 1 }),
          g.nodes.length < 70 || n.type === "UseCase" || n.degree > 9 || n.id === sel || near.has(n.id) ? h("text", { x: 11, y: 4 }, n.name.length > 30 ? n.name.slice(0, 29) + "…" : n.name) : null, h("title", null, n.type + ": " + n.name))));
    }
    const origins = Object.entries((ver.origins || {}).entities || {}).sort((a, b) => b[1] - a[1]), total = origins.reduce((t, x) => t + x[1], 0) || 1;
    const fileIn = h("input", { type: "file", accept: ".zip,.json,.html,.htm", style: "display:none", onchange: run(async (ev) => { const f = ev.target.files[0]; if (!f) return;
      const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.onerror = rej; r.readAsDataURL(f); });
      const out = await api("knowledge/imports", { name: f.name, content_base64: b64, level: S.k.place }); toast("Added " + out.import.label + ": " + out.import.entities + " entities, " + out.import.relationships + " relationships, " + (levelName[out.import.placed] ? "at the " + levelName[out.import.placed] + " level" : out.import.own_levels ? "each entity at the level it was built for" : "with no level yet: choose one and add it again")); top("knowledge")(); }) });
    const download = run(async () => { const res = await fetch(BASE + "/api/knowledge/export", { headers: token() ? { Authorization: "Bearer " + token() } : {} }); if (!res.ok) throw new Error("The export failed (" + res.status + ")");
      const url = URL.createObjectURL(await res.blob()), a = h("a", { href: url, download: "docuinsights-knowledge-base.zip" }); document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000); });
    const panel = e ? cardOf(null, h("div", { class: "row" }, pill("plain", words(e.entity.type)), h("span", { class: "pill plain", style: "color:" + (LCOL[e.level] || "#5d6779") }, (levelName[e.level] || "Added knowledge") + " level" + ((e.also_at || []).length ? ", also " + e.also_at.map((x) => (levelName[x] || x).toLowerCase()).join(", ") : "")), pill(ORIGIN_PILL[e.origin] || "", ov.origin_words[e.origin] || e.origin)),
        h("p", { style: "font-weight:650;font-size:15px;margin:8px 0 4px;overflow-wrap:anywhere" }, e.entity.name), e.entity.props.description ? h("p", { class: "small" }, e.entity.props.description) : null,
        e.class.definition ? h("p", { class: "small muted", style: "margin-top:4px" }, words(e.entity.type).replace(/^./, (c) => c.toUpperCase()) + ": " + e.class.definition) : null,
        e.entity.synonyms.length ? h("div", { class: "chips", style: "margin-top:8px" }, h("span", { class: "small muted" }, "Also known as"), e.entity.synonyms.map((x) => h("span", { class: "chip" }, x))) : null,
        kv(Object.entries(e.entity.props).filter(([k, v]) => !["description", "graphLevel", "knowledgeLevel", "knowledgeSpace", "knowledgeSpaceId", "graphLevelIn"].includes(k) && v !== null && (typeof v !== "object" || Array.isArray(v))).map(([k, v]) => [words(k), Array.isArray(v) ? v.join("; ") : String(v)])),
        h("h3", { style: "margin-top:12px" }, "Where this came from"), e.support.length ? e.support.slice(0, 4).map((c) => h("div", { class: "src", style: "margin-bottom:4px;cursor:default" }, h("div", { class: "row" }, h("b", null, c.fileName || c.source || c.system || c.app || c.kind), h("span", { class: "muted" }, [c.locator, c.case].filter(Boolean).join(" · ")),
          c.check ? h("span", { class: "right" }, pill({ named: "pass", quoted: "pass", read: "pass", paraphrased: "review", missing: "fail" }[c.check] || "", c.check)) : null), c.quote ? h("q", null, c.quote) : h("span", { class: "muted" }, c.text || ""))) : h("p", { class: "small muted" }, "No source recorded."),
        e.support.length > 4 ? h("p", { class: "small muted" }, "and " + (e.support.length - 4) + " more") : null,
        h("h3", { style: "margin-top:12px" }, "Links (" + e.links.length + ")"), e.links.slice(0, 14).map((l) => h("div", { class: "src", style: "margin-bottom:4px", onclick: kEntity(l.other) }, h("span", { class: "muted" }, l.direction === "out" ? words(l.predicate) + " → " : "← " + words(l.predicate) + " "), l.other_name)),
        e.links.length > 14 ? h("p", { class: "small muted" }, "and " + (e.links.length - 14) + " more") : null,
        h("div", { class: "row", style: "margin-top:10px" }, h("button", { class: "btn sm", onclick: run(async () => { S.k.view = "network"; S.k.g = await api("knowledge/graph?focus=" + encodeURIComponent(e.entity.id)); render(); }) }, "Show this and its links as a network")))
      : cardOf("How to read it", h("p", { class: "small" }, "Four levels, top to bottom, as KB Forge lays knowledge out: the industries, what each use case asks for, the accelerator's agents, and the workspace with its cases."),
          h("p", { class: "small muted", style: "margin-top:6px" }, "Click a dot to open what is below it and to see what it is and where it came from. Click it again to close it. Click a level's box to open or close the level."),
          ov.known.length ? [h("h3", { style: "margin-top:12px" }, "Met most often"), ov.known.map((x) => h("div", { class: "src", style: "margin-bottom:4px", onclick: kEntity(x.id) }, x.name, h("span", { class: "muted" }, " · " + x.cases + " case(s)")))] : null);
    const seg = (id, label) => h("button", { "aria-pressed": String(S.k.view === id), onclick: run(async () => { S.k.view = id; if (id === "network" && !S.k.g) S.k.g = await api("knowledge/graph?levels=" + S.k.levels.join(",")); render(); }) }, label);
    return [section("Knowledge", "Everything this workspace has learned, as one graph in KB Forge's format: four levels, from the industry down to each case. It grows with every case that is assessed and every knowledge base you add, and each thing in it points to where it came from."),
      h("div", { class: "grid g4", style: "margin-bottom:14px" }, [[idx.entities.toLocaleString(), "things known"], [idx.triples.toLocaleString(), "links between them"], [ov.quality.score, "quality score, out of 100"], [checked ? Math.round((100 * found) / checked) + "%" : "–", "of " + checked + " citations found in the text"]].map(([v, l]) => h("div", { class: "tile" }, h("b", null, v), h("span", null, l)))),
      h("div", { class: "row", style: "margin-bottom:10px" }, h("div", { class: "seg" }, seg("map", "Level map"), seg("network", "Network")),
        map ? [h("button", { class: "btn sm", onclick: () => { S.k.touched = true; S.k.open = ov.levels.map((l) => l.id); S.k.drill = []; S.k.e = null; kMap()(); } }, "Back to the four levels"), S.k.drill.length ? h("span", { class: "small muted" }, S.k.drill.length + " opened") : null]
          : [h("div", { class: "seg" }, ov.levels.map((lv) => h("button", { "aria-pressed": String(S.k.levels.includes(lv.id) && !g.focus), onclick: () => { S.k.levels = S.k.levels.includes(lv.id) ? S.k.levels.filter((x) => x !== lv.id) : [...S.k.levels, lv.id]; if (!S.k.levels.length) S.k.levels = [lv.id]; kGraph("levels=" + S.k.levels.join(","))(); } }, lv.name))),
            g.focus ? h("button", { class: "btn sm", onclick: kGraph("levels=" + S.k.levels.join(",")) }, "Back to the whole graph") : null],
        h("form", { class: "row", style: "flex:1;min-width:260px;flex-wrap:nowrap", onsubmit: run(async (ev) => { S.k.hits = S.k.q.trim() ? await api("knowledge/search?q=" + encodeURIComponent(S.k.q)) : null; render(); }) }, h("input", { type: "text", placeholder: "Search a company, a product, a rule, a reference number…", value: S.k.q, oninput: (ev) => (S.k.q = ev.target.value) }), h("button", { class: "btn sm", type: "submit", style: "flex:none" }, "Search")),
        !map ? h("span", { class: "small muted" }, g.shown + (g.shown < g.total ? " of " + g.total.toLocaleString() + " (the best connected)" : "") + " shown · " + g.links.length + " links") : null),
      S.k.hits ? cardOf(S.k.hits.length ? "Found" : "Nothing found", S.k.hits.map((x) => h("div", { class: "src", style: "margin-bottom:4px", onclick: kEntity(x.id) }, h("b", null, x.name), h("span", { class: "muted" }, " · " + words(x.type) + (x.cases ? " · " + x.cases + " case(s)" : "")), x.description ? h("div", { class: "muted" }, x.description) : null)), h("div", { style: "height:4px" })) : null,
      h("div", { class: "split", style: "grid-template-columns:minmax(0,3fr) minmax(0,1.15fr);margin-top:10px" }, h("div", null, svg, h("div", { class: "chips small", style: "margin-top:8px" }, [...new Set((map ? S.k.m.nodes : g.nodes).map((n) => n.type))].map((t) => h("span", { class: "row", style: "gap:5px;margin-right:8px" }, h("span", { style: "width:10px;height:10px;border-radius:50%;display:inline-block;background:" + (KCOL[t] || "#7a8496") }), words(t))))), panel),
      h("div", { class: "grid g2", style: "margin-top:14px" },
        cardOf("Where the knowledge comes from", h("p", { class: "small muted", style: "margin-bottom:8px" }, "Every build checks each document citation against the text it cites, with no model. " + (st.missing ? st.missing + " could not be found." : "None is missing.")),
          origins.map(([o, n]) => h("div", { class: "barrow" }, h("span", null, ov.origin_words[o] || o), h("div", { class: "bar" }, h("i", { style: "width:" + Math.max(2, (100 * n) / total) + "%" })), h("b", null, n)))),
        cardOf("Knowledge bases", h("p", { class: "small muted", style: "margin-bottom:8px" }, "Kept in the " + ov.format.name + " layout (schema " + ov.format.schemaVersion + "). Add a knowledge base built in KB Forge: it sits at the level it was built for (industry, domain, delivery experience, customer), or the one you choose. Download this one to open it in KB Forge."),
          h("table", null, h("tbody", null, h("tr", null, h("td", null, h("b", null, "The accelerator and its use cases"), h("div", { class: "small muted" }, S.cfg.profiles.length + " use case(s), " + S.cfg.agents.length + " agents under contract")), h("td", { class: "small muted" }, "built in"), h("td", null)),
            h("tr", null, h("td", null, h("b", null, "Cases"), h("div", { class: "small muted" }, ov.sources.cases + " assessed case(s), " + ov.sources.documents + " document(s)")), h("td", { class: "small muted" }, "learned"), h("td", null)),
            ov.sources.imports.map((i) => h("tr", null, h("td", null, h("b", null, i.label), h("div", { class: "small muted" }, i.entities.toLocaleString() + " entities, " + i.relationships.toLocaleString() + " relationships · " + (i.app || "file") + " · " + when(i.imported_at))), h("td", { class: "small" }, i.level_name),
              h("td", null, h("button", { class: "btn sm ghost", onclick: run(async () => { await api("knowledge/imports/" + encodeURIComponent(i.id) + "/remove", {}); top("knowledge")(); }) }, "Take out")))))),
          fileIn, h("div", { class: "row", style: "margin-top:10px" }, h("select", { style: "width:auto", "aria-label": "Level", onchange: (ev) => (S.k.place = ev.target.value) }, [["", "Level: as built"], ["industry", "Industry"], ["domain", "Domain"], ["solution", "Solution"], ["customer", "Customer"]].map(([v, l]) => h("option", { value: v, selected: S.k.place === v }, l))),
            h("button", { class: "btn primary sm", onclick: () => fileIn.click() }, "Add a knowledge base"), h("button", { class: "btn sm", onclick: download }, "Download for KB Forge (.zip)")))),
      h("details", { class: "card", style: "margin-top:14px" }, h("summary", null, "The ontology: " + ov.classes.length + " kinds of thing, " + ov.relationships.length + " kinds of link"),
        h("table", { style: "margin-top:8px" }, h("thead", null, h("tr", null, ["Kind of thing", "Is a", "Level", "In the graph", "What counts as one"].map((x) => h("th", null, x)))), h("tbody", null, ov.classes.filter((c) => c.count || c.source !== "import").map((c) => h("tr", null, h("td", null, h("b", null, c.name)), h("td", { class: "small" }, c.parent || "–"), h("td", { class: "small" }, levelName[c.level] || "–"), h("td", { class: "mono small" }, c.count), h("td", { class: "small muted" }, c.definition))))),
        h("table", { style: "margin-top:14px" }, h("thead", null, h("tr", null, ["Kind of link", "From", "To", "In the graph", "Meaning"].map((x) => h("th", null, x)))), h("tbody", null, ov.relationships.filter((r) => r.count).map((r) => h("tr", null, h("td", null, h("b", null, r.name)), h("td", { class: "small" }, r.domain), h("td", { class: "small" }, r.range), h("td", { class: "mono small" }, r.count), h("td", { class: "small muted" }, r.definition))))))];
  }

  // ---------------------------------------------------------------------------------------------- how it is governed
  function platform() {
    const f = S.pf, c = f.contracts, m = f.memory, led = f.provenance.ledger, t = f.throttling, lim = t.model.limits, row = (k, v) => h("tr", null, h("td", { class: "small muted", style: "width:42%" }, k), h("td", null, v));
    return [section("How the agents are governed", "Six things every agent runs on, and how each stands in this workspace right now."),
      h("div", { class: "grid g2" },
        cardOf("Agent contracts", h("p", { class: "small muted", style: "margin-bottom:8px" }, "A contract says what an agent needs, what it promises, what it may change, what it may spend and what it must never do."),
          h("table", null, h("tbody", null, row("Agents under contract", c.agents), row("Checks the contracts name", c.checks), row("Agent runs so far", c.runs), row("Runs that kept their contract", h("span", null, c.kept + " ", pill(c.kept === c.runs ? "pass" : "fail", c.kept === c.runs ? "all" : c.runs - c.kept + " broken"))))),
          c.broken.map((b) => h("div", { class: "note", style: "margin-top:6px" }, h("b", null, b.case + " · " + b.agent + ": "), b.why.join("; "))), h("button", { class: "btn sm", style: "margin-top:10px", onclick: top("agents") }, "Read the contracts")),
        cardOf("Agent harness", h("p", { class: "small muted", style: "margin-bottom:8px" }, "The one place every agent runs. It never decides a case and never repairs an agent's output."),
          steps(["Before: checks what the agent needs; hands it only the model and the memory its contract allows.", "During: times the run; meters every model call against the agent's budget and the rate limit.", "After: checks every promise and that the agent changed only what it may; records the run on the case and in the ledger.", "A contract that is not kept is never silent: the case goes to a person."])),
        cardOf("Shared memory", h("p", { class: "small muted", style: "margin-bottom:8px" }, "What the agents keep for each other, at three distances. Only the orchestrator writes what outlives a case, and never from a model."),
          h("table", null, h("tbody", null, row("One run", "The note each agent leaves for the ones after it"), row("One case", "Its documents, the reviewer's corrections and decisions"), row("Workspace: what is known", m.semantic.entities + " things, " + m.semantic.relationships + " links (the knowledge graph)"),
            row("Workspace: what happened", m.episodes + " episode(s), one per assessed case"), row("Workspace: how to read", Object.values(m.procedural).reduce((n, x) => n + x.approved, 0) + " approved improvement(s), " + Object.values(m.procedural).reduce((n, x) => n + x.waiting, 0) + " waiting for a person"))),
          m.recent.length ? h("table", { style: "margin-top:8px" }, h("thead", null, h("tr", null, ["Remembered case", "Use case", "Outcome"].map((x) => h("th", null, x)))), h("tbody", null, m.recent.slice(0, 5).map((e) => h("tr", { class: "click", onclick: run(() => open(e.case)) }, h("td", { class: "mono small" }, e.case), h("td", { class: "small" }, e.use_case), h("td", null, outcomePill(e)))))) : null),
        cardOf("Evidence provenance", h("p", { class: "small muted", style: "margin-bottom:8px" }, "Every conclusion points to a line of a document. Every agent run, review and decision is one line in a ledger, each chained to the line before it."),
          h("table", null, h("tbody", null, row("Ledger entries", led.entries), row("Chain", led.ok ? pill("pass", "intact") : pill("fail", "broken at entry " + led.broken_at)), row("Latest fingerprint", h("span", { class: "mono small" }, led.head || "–")))),
          f.provenance.recent.length ? h("table", { style: "margin-top:8px" }, h("thead", null, h("tr", null, ["#", "Who", "What"].map((x) => h("th", null, x)))), h("tbody", null, f.provenance.recent.slice(0, 6).map((e) => h("tr", null, h("td", { class: "mono small" }, e.n), h("td", { class: "small" }, e.actor), h("td", { class: "small" }, e.summary, e.case ? h("span", { class: "muted" }, " · " + e.case) : null))))) : null),
        cardOf("Knowledge graph", h("p", { class: "small muted", style: "margin-bottom:8px" }, "What the workspace knows, as one graph in the KB Forge format, rebuilt from its sources after every case."),
          h("table", null, h("tbody", null, row("Things known", m.semantic.entities), row("Links between them", m.semantic.relationships))), h("button", { class: "btn sm", style: "margin-top:10px", onclick: top("knowledge") }, "Open the knowledge graph")),
        cardOf("Throttling", h("p", { class: "small muted", style: "margin-bottom:8px" }, "How fast the agents may call a model and how fast a caller may call the API. At a limit a call waits; past the wait the agent falls back to patterns and says so."),
          h("table", null, h("tbody", null, row("Model calls", t.model.describe + ", wait up to " + lim.max_wait_s + "s"), row("In the last minute", t.model.last_minute.calls + " call(s), " + t.model.last_minute.tokens.toLocaleString() + " tokens"),
            row("Since start", t.model.totals.calls + " call(s) · " + t.model.totals.waits + " waited · " + t.model.totals.shed + " not made"), row("Per agent, per run", "a budget of calls and tokens in each contract"),
            row("API", (t.api.requests_per_minute ? t.api.requests_per_minute + " requests a minute per caller" : "no limit") + " · " + t.api.totals.refused + " refused"), row("Assessments at once", t.assessments.max_at_once + " (running now: " + t.assessments.running + ")")))))];
  }

  // ---------------------------------------------------------------------------------------------- findings
  function findingCard(f, opts) {
    const o = opts || {}, v = f.verifier || {};
    return h("div", { class: "card", id: "f-" + f.id }, h("div", { class: "row" }, pill(f.status), h("b", null, f.title), f.blocked ? pill("fail", "blocked: unsupported") : null, h("span", { class: "right small muted mono" }, f.id)),
      h("p", { style: "margin:6px 0 8px" }, f.message), steps(f.reasoning),
      f.sources.length ? h("div", { class: "grid g2", style: "margin-top:10px" }, f.sources.map((s) => h("div", { class: "src", title: "Open the source", onclick: () => openSource(s) }, h("b", null, s.doc_name), " · ", s.field_name, s.page ? " · page " + s.page + (s.line ? ", line " + s.line : "") : "", h("q", null, s.snippet || String(s.value))))) : null,
      h("div", { class: "chips small muted", style: "margin-top:10px" }, f.rule ? h("span", { class: "chip", title: f.rule.note || "" }, "Rule " + f.rule.id + " v" + f.rule.version) : null,
        f.reference ? h("a", { class: "chip", href: f.reference.url, target: "_blank", rel: "noopener" }, "Reference as of " + (f.reference.as_of || "n/a") + " (" + f.reference.mode + ")") : null,
        h("span", { class: "chip" }, "Agent: " + f.agent), h("span", { class: "chip" }, "Sources verified " + (v.verified || 0) + "/" + (v.sources || 0)), f.requires_human ? h("span", { class: "chip" }, "Needs a person") : null,
        f.human ? pill(f.human.decision === "accept" ? "pass" : "review", f.human.decision + "ed by " + f.human.by) : null,
        f.graph_path.length ? h("button", { class: "btn sm ghost", onclick: () => { S.view = "graph"; S.sel.path = f.graph_path; S.sel.node = "F:" + f.id; S.layers.reasoning = true; S.layers.assertion = true; render(); } }, "Show graph path (" + f.graph_path.length + " nodes)") : null),
      o.review ? h("div", { class: "row", style: "margin-top:10px" }, h("button", { class: "btn sm", onclick: run(() => reviewFinding(f, "accept")) }, "Accept"), h("button", { class: "btn sm", onclick: run(() => reviewFinding(f, "flag")) }, "Flag")) : null);
  }
  async function reviewFinding(f, decision) { const v = await form((decision === "accept" ? "Accept" : "Flag") + ": " + f.title, [{ k: "reason", label: "Note for the audit trail", type: "textarea" }], decision === "accept" ? "Accept" : "Flag"); if (v) setCase(await api("cases/" + S.c.reference + "/review", { target: "finding", id: f.id, decision, reason: v.reason })); }
  function banner(rec) {
    return h("div", { class: "banner " + rec.outcome }, h("div", { class: "small muted" }, "Recommendation for the caseworker"), h("h2", null, rec.label), h("p", null, rec.description),
      rec.reasons.length ? h("ul", null, rec.reasons.map((r) => h("li", null, r))) : null, rec.requests.length ? h("p", null, h("b", null, "To request: "), rec.requests.join("; ")) : null,
      rec.caveats.length ? h("p", { class: "small" }, h("b", null, "Caveat: "), rec.caveats.join(" ")) : null, h("p", { class: "small muted" }, "Decided by: " + rec.decided_by + "."));
  }

  // ---------------------------------------------------------------------------------------------- case views
  function known(a) {
    const mem = a.findings.filter((f) => f.family === "memory" || f.family === "governance");
    return mem.length ? cardOf("What the workspace already knew", h("p", { class: "small muted", style: "margin-bottom:8px" }, "Recalled from earlier cases by the workspace's memory. Context for you; only a line marked for review affects the recommendation."),
      mem.map((f) => h("div", { class: "row", style: "align-items:flex-start;margin-bottom:6px" }, pill(f.status === "review" ? "review" : "info", f.status === "review" ? "for review" : "known"), h("div", { style: "flex:1" }, h("b", null, f.title), h("div", { class: "small" }, f.message))))) : null;
  }
  function summary() {
    const a = A(), c = (s) => a.findings.filter((f) => f.status === s).length, g = a.metrics.graph;
    return [section("Case intelligence summary", "What the package contains, what it supports and what stands in the way, composed from the findings."), h("div", { class: "stack" }, banner(a.recommendation),
      h("div", { class: "grid g4" }, [[S.c.documents.filter((d) => !d.removed).length, "documents, " + a.metrics.pages + " pages"], [c("pass"), "checks passed"], [c("fail") + c("missing") + c("review"), "need attention"], [g.nodes + " / " + g.edges, "graph nodes / edges"]].map(([v, l]) => h("div", { class: "tile" }, h("b", null, v), h("span", null, l)))),
      cardOf("Summary", h("p", null, a.summary), h("p", { class: "small muted", style: "margin-top:8px" }, "Assessment " + a.id + " · " + when(a.at) + " · trigger: " + a.trigger + " · profile v" + a.profile_version + " · vocabulary v" + a.overlay_version + " · " + a.metrics.duration_ms + " ms" + (a.contracts ? " · " + a.contracts.kept + " of " + a.contracts.runs + " agent contracts kept" : ""))),
      known(a),
      cardOf("Case facts", kv(prof().case.fields.map((f) => [f.name, S.c.fields[f.id]]))),
      cardOf("Parties and goods", h("table", null, h("thead", null, h("tr", null, ["Entity", "Kind", "Roles", "Mentioned in"].map((x) => h("th", null, x)))), h("tbody", null, a.entities.map((e) => h("tr", null, h("td", null, e.name), h("td", null, e.type), h("td", { class: "small" }, (e.roles || []).join(", ")),
        h("td", { class: "small muted" }, [...new Set(e.mentions.map((m) => m.doc_name))].join(", "))))))),
      h("div", null, h("h3", { style: "margin:6px 0 10px;font-size:15px" }, "Needs attention"), h("div", { class: "stack" }, a.findings.filter((f) => ["fail", "missing", "review"].includes(f.status)).map((f) => findingCard(f)), !a.findings.some((f) => ["fail", "missing", "review"].includes(f.status)) ? h("p", { class: "muted" }, "Nothing: every check passed.") : null)))];
  }
  function documents() {
    const docs = S.c.documents.filter((d) => !d.removed), p = prof();
    const sel = docs.find((d) => d.id === S.sel.doc) || docs[0];
    const cls = (d) => d.classification || {};
    const correct = async (d) => { const v = await form("Correct the classification of " + d.name, [{ k: "value", label: "Correct class", options: p.document_types.map((t) => [t.id, t.name]), value: cls(d).type || "" }, { k: "reason", label: "Why is this change needed? (kept in the audit trail)", type: "textarea" }], "Confirm change"); if (v) setCase(await api("cases/" + S.c.reference + "/review", { target: "classification", doc: d.id, decision: "correct", value: v.value, reason: v.reason })); };
    const table = h("table", null, h("thead", null, h("tr", null, ["File", "Uploaded as", "AI classification", "Confidence", "Read by", "Review"].map((x) => h("th", null, x)))), h("tbody", null, docs.map((d) => h("tr", { class: "click" + (sel && d.id === sel.id ? " sel" : ""), onclick: () => { S.sel.doc = d.id; S.sel.line = null; render(); } },
      h("td", null, h("b", null, d.name), d.current > 1 ? h("span", { class: "pill plain", style: "margin-left:6px" }, "v" + d.current) : null), h("td", null, p.document_types.some((t) => t.id === d.category) ? typeName(d.category) : "Other documents"),
      h("td", null, cls(d).version ? pill(cls(d).agrees ? "pass" : "review", typeName(cls(d).type)) : "–", d.effective_type && d.effective_type !== cls(d).type ? h("div", { class: "small" }, "corrected to ", h("b", null, typeName(d.effective_type))) : null),
      h("td", null, cls(d).confidence !== undefined ? Math.round(cls(d).confidence * 100) + "%" : "–"), h("td", { class: "small muted" }, (d.versions[d.current - 1].method || "–")),
      h("td", null, d.review ? pill("pass", d.review.decision === "approve" ? "approved" : "corrected") : cls(d).version ? h("span", { class: "row", style: "gap:6px" }, h("button", { class: "btn sm", onclick: run(async (e) => { e.stopPropagation(); setCase(await api("cases/" + S.c.reference + "/review", { target: "classification", doc: d.id, decision: "approve" })); }) }, "Approve"), h("button", { class: "btn sm", onclick: run((e) => { e.stopPropagation(); return correct(d); }) }, "Incorrect")) : "–")))));
    let detail = null;
    if (sel) {
      const ver = sel.versions[sel.current - 1], hit = S.sel.line, tdef = p.document_types.find((t) => t.id === (sel.effective_type || cls(sel).type)) || { fields: [] };
      const editField = async (f) => { const cur = (sel.fields || {})[f.id]; const v = await form("Correct " + f.name, [{ k: "value", label: "Value as it should read", value: cur ? cur.value : "" }, { k: "reason", label: "Reason (audit trail)", type: "textarea" }]); if (v) setCase(await api("cases/" + S.c.reference + "/review", { target: "field", doc: sel.id, field: f.id, value: v.value, reason: v.reason })); };
      const text = h("div", { class: "doc" }, (ver.pages || []).flatMap((page, pi) => page.split("\n").map((ln, li) => h("div", { class: hit && hit.page === pi + 1 && hit.line === li + 1 ? "hit" : "" }, h("i", null, li + 1), ln || " "))), !(ver.pages || []).length ? h("div", null, h("i", null, ""), ver.note || "Not read yet.") : null);
      detail = h("div", { class: "split", style: "margin-top:14px" },
        cardOf("Extracted fields · " + typeName(sel.effective_type || cls(sel).type), cls(sel).rationale ? h("p", { class: "small muted", style: "margin-bottom:8px" }, "Classified because: " + cls(sel).rationale) : null,
          h("table", null, h("tbody", null, tdef.fields.map((f) => { const x = (sel.fields || {})[f.id]; return h("tr", { class: "click", onclick: () => { if (x && x.anchor && x.anchor.page) { S.sel.line = x.anchor; render(); } } }, h("td", { class: "small muted", style: "width:34%" }, f.name, f.required ? " *" : ""), h("td", null, x && x.norm !== null ? x.value : h("span", { class: "muted" }, "not found"), x && x.alternative ? h("div", { class: "small muted" }, "pattern read: " + x.alternative.value) : null),
            h("td", { style: "white-space:nowrap" }, x && x.norm !== null ? pill(x.verified ? "pass" : "review", x.method === "human" ? "corrected" : x.verified ? "sourced" : "unverified") : f.required ? pill("missing", "absent") : null), h("td", null, h("button", { class: "btn sm ghost", onclick: run((e) => { e.stopPropagation(); return editField(f); }) }, "Edit"))); })))),
        h("div", null, h("div", { class: "row", style: "margin-bottom:8px" }, h("b", null, sel.name), h("span", { class: "small muted mono" }, "v" + sel.current + " · sha256 " + (ver.sha256 || "").slice(0, 12)),
          h("a", { class: "btn sm right", href: "#", onclick: run(async (e) => { const t = token(); const r = await fetch(BASE + "/api/cases/" + S.c.reference + "/documents/" + sel.id + "/file", { headers: t ? { Authorization: "Bearer " + t } : {} }); window.open(URL.createObjectURL(await r.blob()), "_blank", "noopener"); }) }, "Open the original")), text,
          ver.note ? h("p", { class: "small muted", style: "margin-top:6px" }, ver.note) : null));
    }
    const more = h("input", { type: "file", multiple: true, style: "display:none", onchange: run(async (e) => { const docsNew = []; for (const f of e.target.files) { const b64 = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.readAsDataURL(f); }); docsNew.push({ name: f.name, content_base64: b64 }); } setCase(await api("cases/" + S.c.reference + "/documents", { documents: docsNew, assess: true }), "monitor"); }) });
    return [section("Documents and classification", "Each file as it was uploaded beside what it actually is. Green means the classification agrees with the uploader's category; amber is a mismatch to check. A file uploaded again under the same name becomes a new version."),
      cardOf(null, table), h("div", { class: "row", style: "margin-top:10px" }, more, h("button", { class: "btn sm", onclick: () => more.click() }, "Add or amend documents"),
        S.c.sample && S.c.sample.amendments.length && A() ? h("button", { class: "btn sm accent", onclick: run(async () => setCase(await api("cases/" + S.c.reference + "/amendment", {}), "audit")) }, "Receive the amended document (" + S.c.sample.amendments[0].note + ")") : null), detail];
  }
  const listOf = (title, lead, pred, empty) => () => { const fs = F(pred); return [section(title, lead), h("div", { class: "stack" }, fs.length ? fs.map((f) => findingCard(f)) : h("p", { class: "muted" }, empty || "Nothing to show."))]; };
  const evidence = listOf("Evidence completeness", "Mandatory, conditional and alternative evidence for this use case, and how an absence was established.", (f) => f.family === "evidence");
  function consistency() {
    const fs = F((f) => f.agent === "contradiction");
    return [section("Cross-document consistency", "The same fact as each document states it. A discrepancy names the documents that disagree; a corroboration names how many agree."),
      cardOf(null, h("table", null, h("thead", null, h("tr", null, ["Check", "Result", "As stated in each document"].map((x) => h("th", null, x)))), h("tbody", null, fs.map((f) => h("tr", null, h("td", { style: "width:26%" }, h("b", null, f.title), h("div", { class: "small muted" }, f.rule.type)), h("td", { style: "width:14%" }, pill(f.status, { pass: "corroborated", fail: "discrepancy", review: "confirm", info: "single source" }[f.status])),
        h("td", null, f.sources.map((s) => h("div", { class: "src", style: "margin-bottom:4px", onclick: () => openSource(s) }, h("b", null, s.doc_name), ": ", String(s.value), (f.data.disagree || []).includes(s.doc) ? h("span", { class: "pill fail", style: "margin-left:6px" }, "differs") : null)), !f.sources.length ? h("span", { class: "muted" }, f.message) : null)))))),
      (A().unresolved || []).length ? cardOf("Possible entity matches", A().unresolved.map((m) => h("div", { class: "row", style: "margin-bottom:6px" }, h("span", null, m.reason + " (similarity " + m.similarity + ")"), matchButtons(m)))) : null];
  }
  const matchButtons = (m) => (m.decided ? pill("pass", m.decided === "same" ? "one party" : "two parties") : h("span", { class: "row right", style: "gap:6px" }, ["same", "different"].map((d) => h("button", { class: "btn sm", onclick: run(async () => { const v = await form(d === "same" ? "Confirm: one party" : "Confirm: two parties", [{ k: "reason", label: "Reason (audit trail)", type: "textarea" }], "Confirm"); if (v) setCase(await api("cases/" + S.c.reference + "/review", { target: "entity_match", id: m.id, decision: d, reason: v.reason })); }) }, d === "same" ? "Same party" : "Different"))));
  function reference() {
    const a = A();
    return [section("Classification assessment", "The reference content retrieved for the case's date, the line the product evidence supports, and the codes the documents state. The reference stays the authority; this is an aid for the caseworker."),
      h("div", { class: "stack" }, a.references.map((r) => {
        const rt = r.retrieval, res = r.result, path = new Set(res.path || []), alts = new Set((res.alternatives || []).map((x) => x.code)), depth = {};
        r.lines.forEach((n) => { depth[n.code] = n.parent && depth[n.parent] !== undefined ? depth[n.parent] + 1 : 0; });
        return [cardOf(rt.name, kv([["Address", h("a", { href: rt.url, target: "_blank", rel: "noopener" }, rt.url)], ["Requested as of", rt.requested_as_of], ["Retrieved", when(rt.retrieved_at) + " (" + rt.mode + ")"], ["Version", rt.version], ["Content hash", h("span", { class: "mono" }, (rt.result_hash || "").slice(0, 24))], ["Note", rt.note]])),
          F((f) => f.id === "REF-" + r.id + "-classification").map((f) => findingCard(f)),
          cardOf("Product characteristics used", Object.keys(r.characteristics).length ? h("table", null, h("tbody", null, Object.values(r.characteristics).map((c) => h("tr", null, h("td", { class: "muted small", style: "width:30%" }, c.name), h("td", null, String(c.raw)), h("td", null, c.unmapped ? pill("review", "not in the approved vocabulary") : c.value !== c.raw ? h("span", { class: "small muted" }, "read as " + c.value) : null))))) : h("p", { class: "muted" }, "No product evidence in the case.")),
          cardOf("Codes stated in the documents", r.declared.length ? h("table", null, h("tbody", null, r.declared.map((d) => h("tr", null, h("td", null, d.doc_name), h("td", { class: "mono" }, d.code), h("td", null, pill(d.relation === "equal" ? "pass" : "review", d.relation)))))) : h("p", { class: "muted" }, "No code is stated in any document.")),
          cardOf("Hierarchy as retrieved" + (rt.partial ? " (partial)" : ""), h("div", { class: "tree" }, r.lines.map((n) => h("div", { class: "ln" + (n.code === res.code && res.status === "supported" ? " cand" : path.has(n.code) ? " on" : alts.has(n.code) ? " alt" : "") }, h("span", { class: "mono" }, n.display), h("span", { style: "padding-left:" + depth[n.code] * 16 + "px" }, n.description), h("span", { class: "small muted" }, n.third_country_duty ? "duty " + n.third_country_duty : "")))))];
      })), F((f) => f.family === "commodity").map((f) => h("div", { style: "margin-top:14px" }, findingCard(f)))];
  }
  function policy() {
    const a = A(), hist = [...S.c.history, { id: a.id, at: a.at, trigger: a.trigger, label: a.recommendation.label, findings: Object.fromEntries(a.findings.map((f) => [f.id, { status: f.status, title: f.title }])), references: a.references.map((r) => ({ as_of: r.retrieval.requested_as_of, version: r.retrieval.version })), documents: a.documents }];
    return [section("Policy and temporal checks", "The deterministic rules, each with the calculation it performed and the version it ran under, and how the case has changed over time."),
      h("div", { class: "stack" }, F((f) => f.agent === "policy").map((f) => findingCard(f)),
        cardOf("What was known at each assessment", h("table", null, h("thead", null, h("tr", null, ["Assessment", "When", "Trigger", "Documents (version)", "Reference read for", "Outcome", "What changed"].map((x) => h("th", null, x)))), h("tbody", null, hist.map((x, i) => { const prev = hist[i - 1];
          const diff = prev ? Object.keys(x.findings).filter((k) => (prev.findings[k] || {}).status !== x.findings[k].status).map((k) => x.findings[k].title + ": " + ((prev.findings[k] || {}).status || "new") + " → " + x.findings[k].status) : [];
          return h("tr", null, h("td", { class: "mono" }, x.id), h("td", { class: "small" }, when(x.at)), h("td", null, x.trigger), h("td", { class: "small" }, (x.documents || []).map((d) => d.name + " v" + d.version).join(", ")), h("td", { class: "small" }, (x.references || []).map((r) => r.as_of + " (" + r.version + ")").join(", ")), h("td", null, x.label), h("td", { class: "small" }, prev ? (diff.length ? diff.map((t) => h("div", null, t)) : "no change") : "first assessment")); })))))];
  }
  function provenance() {
    const a = A(), fams = ["all", ...new Set(a.findings.map((f) => f.family))];
    const fs = a.findings.filter((f) => (S.filter.family === "all" || f.family === S.filter.family) && (S.filter.status === "all" || (S.filter.status === "attention" ? ["fail", "missing", "review"].includes(f.status) : f.status === S.filter.status)));
    const seg = (key, opts) => h("div", { class: "seg" }, opts.map((o) => h("button", { "aria-pressed": String(S.filter[key] === o), onclick: () => { S.filter[key] = o; render(); } }, o)));
    return [section("Reasoning and provenance explorer", "Every finding with what it rests on: the document, version, page and line; the rule and its version; the reference address and date; the agent; and the verifier's source coverage."),
      h("div", { class: "row", style: "margin-bottom:12px" }, seg("status", ["attention", "pass", "info", "all"]), seg("family", fams), h("span", { class: "small muted right" }, fs.length + " of " + a.findings.length + " findings")),
      h("div", { class: "stack" }, fs.map((f) => findingCard(f, { review: true })), !fs.length ? h("p", { class: "muted" }, "No finding matches this filter.") : null)];
  }
  function whatif() {
    const p = prof(), cf = S.cf;
    const fire = (sc) => run(async () => { let value; if (sc.ask) { const v = await form(sc.title, [{ k: "value", label: "New value", type: sc.ask, value: sc.value || "" }], "Run what-if"); if (!v) return; value = v.value || undefined; } S.cf = { pending: sc.title }; render(); S.cf = await api("cases/" + S.c.reference + "/counterfactual", { scenario: sc.id, value }); render(); });
    return [section("Counterfactual simulator", "Change one fact on a copy of the case and rerun the dependent checks. The case itself is not changed, and an assumed document is labelled as assumed."),
      h("div", { class: "grid g3" }, p.counterfactuals.map((sc) => h("div", { class: "card tight" }, h("b", null, sc.title), h("p", { class: "small muted", style: "margin:5px 0 10px;min-height:54px" }, sc.expect), h("button", { class: "btn sm", onclick: fire(sc) }, "Run")))),
      cf && cf.pending ? h("p", { style: "margin-top:16px" }, h("span", { class: "spin" }), " Rerunning: " + cf.pending) : null,
      cf && !cf.pending ? h("div", { class: "stack", style: "margin-top:16px" }, cardOf("Impact: " + cf.change, h("div", { class: "row", style: "margin-bottom:8px" }, pill("info", cf.before.label), "→", pill(cf.after.outcome === "proceed" ? "pass" : cf.after.outcome === "review" ? "fail" : "review", cf.after.label), h("span", { class: "small muted right" }, "reran " + cf.reran.length + " agents in " + cf.duration_ms + " ms")), steps(cf.explanation)),
        cf.moved.length ? cardOf("Findings that moved", h("table", null, h("thead", null, h("tr", null, ["Finding", "Before", "After", "Now"].map((x) => h("th", null, x)))), h("tbody", null, cf.moved.map((m) => h("tr", null, h("td", null, m.title), h("td", null, pill(m.before)), h("td", null, pill(m.after)), h("td", { class: "small" }, m.after_message)))))) : null,
        cf.draft ? cardOf("Draft the change would call for: " + cf.draft.subject, h("pre", { class: "mono", style: "white-space:pre-wrap;margin:0" }, cf.draft.body)) : null) : null];
  }
  // ---------------------------------------------------------------------------------------------- the orchestration board
  // One picture of an assessment: the process on top, the boss agent's plan under it, the agents the harness ran, and the two things they
  // all share (the knowledge graph and the shared memory). Every lane uses the same nine columns, so a step reads straight down.
  const OSTEPS = [["Case intake", ["intake"]], ["Document understanding", ["classify", "extract"]], ["Graph construction", ["resolve", "graph"]], ["Evidence validation", ["evidence"]],
    ["Reference and policy", ["reference", "policy"]], ["Checks and verification", ["consistency", "verify"]], ["Caseworker review", null], ["Decision and learning", null]];
  const OX = (i) => 140 + 107.5 * (i + 0.5);   // the middle of step i, in a drawing 1000 wide whose first 140 are the lane names
  const TRIGGER = { correction: "a person corrected it", amendment: "an amendment arrived", assessment: "asked again", regression: "regression run" };
  const short = (name) => String(name || "").replace(/ Agent$/, "");
  const ms = (v) => (v >= 1000 ? (v / 1000).toFixed(1) + " s" : (v >= 10 ? Math.round(v) : v) + " ms");
  function orchState() {
    const a = A(), pr = S.c.progress || {}, running = pr.state === "running", runs = running ? (S.c.live || { runs: [] }).runs : a ? a.runs : [];
    const decided = !!S.c.decision && !running && !!a && S.c.decision.assessment === a.id, total = runs.length + (decided ? 2 : 0);   // one beat per agent run, then the person's two steps once they happened
    const t = S.orch.t === null || S.orch.t > total ? total : S.orch.t, replay = t < total, seen = runs.slice(0, t), now = replay ? runs[t] : null;
    const doneStages = new Set(seen.map((r) => r.stage)), need = a ? a.findings.filter((f) => ["fail", "missing", "review"].includes(f.status)).length : 0;
    const passes = (S.c.history || []).length + (a ? 1 : 0), again = [...(S.c.history || []), ...(a ? [a] : [])].slice(1);
    const steps = OSTEPS.map(([title, st], i) => {
      if (st) { const mine = seen.filter((r) => st.includes(r.stage)), working = (now && st.includes(now.stage)) || (!replay && running && (st.includes(pr.stage) || (mine.length && !st.every((s) => doneStages.has(s)))));
        const state = pr.state === "failed" && !replay && st.includes(pr.stage) ? "failed" : st.every((s) => doneStages.has(s)) ? "done" : working ? "working" : "waiting";
        return { i, title, st, runs: mine, now: now && st.includes(now.stage) ? now : null, liveStage: !replay && running && st.includes(pr.stage) ? pr.stage : null, state }; }
      const at = t - runs.length, ready = !!a && !running && at >= 0;   // the person's steps: reached once every agent has run
      const state = !ready ? "waiting" : i === 6 ? (decided && at >= 1 ? "done" : "person") : decided && at >= 2 ? "done" : decided && at === 1 ? "person" : "waiting";
      return { i, title, st: null, runs: [], state };
    });
    return { a, pr, running, runs, decided, total, t, replay, seen, now, steps, need, passes, again, stepOf: (stage) => OSTEPS.findIndex(([, st]) => st && st.includes(stage)) };
  }
  function orchStatus(o) {
    if (o.pr.state === "failed" && !o.replay) return "Stopped at " + o.pr.stage + ": " + (o.pr.error || "");
    if (o.replay) return "Replay · beat " + (o.t + 1) + " of " + o.total + " · " + (o.now ? o.now.name + ": " + o.now.summary : o.t === o.runs.length ? "The boss agent hands the case to a person" : "A person decides; the workspace learns the outcome");
    if (o.running) { const ag = S.cfg.agents.find((x) => x.stage === o.pr.stage); return "Live · " + (ag ? ag.name + " is working" : "starting") + " · " + o.runs.length + " of " + S.cfg.stages.length + " agent runs done"; }
    if (!o.a) return "Not assessed yet. Assess the case to watch the agents work.";
    if (o.runs.length && !o.runs[0].plan) return "Assessed by an earlier version, which kept no plan and no hand-offs. Assess it again to see them.";
    return "Assessment " + o.a.id + " · " + o.runs.length + " agent runs in " + ms(o.a.metrics.duration_ms) + " · " + o.a.recommendation.label + (o.decided ? " · decided: " + S.c.status : " · waiting for a person");
  }
  function orchRefresh() {   // redraw the board in place: the slider keeps the pointer that is dragging it
    const o = orchState(), swap = (id, el) => { const old = document.getElementById(id); if (old) old.replaceWith(el); return !!old; };
    if (!swap("orch-body", orchBody(o))) return render();
    swap("orch-btns", orchButtons(o)); swap("orch-status", h("span", { id: "orch-status", class: "ostatus" }, orchStatus(o)));
    const r = document.getElementById("orch-range"); if (r) { r.max = o.total; if (document.activeElement !== r || S.orch.playing) r.value = o.t; }
  }
  function orchPlay(from) {
    clearInterval(S.orch.timer); const o = orchState(); if (!o.total) return;
    S.orch.t = from !== undefined ? from : o.replay ? o.t : 0; S.orch.playing = true;
    S.orch.timer = setInterval(() => { const n = orchState(); if (!S.c || S.view !== "monitor" || !document.getElementById("orch-body")) { clearInterval(S.orch.timer); S.orch.playing = false; return; }
      if (n.t + 1 >= n.total) { clearInterval(S.orch.timer); S.orch.playing = false; S.orch.t = null; } else S.orch.t = n.t + 1; orchRefresh(); }, 1100 / (S.orch.speed || 1));
    orchRefresh();
  }
  const orchStop = () => { clearInterval(S.orch.timer); S.orch.playing = false; };
  function orchButtons(o) {
    const live = S.orch.t === null || !o.replay;
    return h("span", { id: "orch-btns", class: "row", style: "gap:6px;flex-wrap:nowrap" },
      h("button", { class: "obtn" + (live ? " on" : ""), title: "Follow the assessment as it is now", onclick: () => { orchStop(); S.orch.t = null; orchRefresh(); } }, h("i", { class: "dot" + (o.running ? " pulse" : "") }), "Live"),
      h("button", { class: "obtn" + (S.orch.playing ? " on" : ""), disabled: !o.total, title: "Play the assessment back, one agent at a time", onclick: () => { if (S.orch.playing) { orchStop(); orchRefresh(); } else orchPlay(); } }, S.orch.playing ? "❚❚ Pause" : "▶ Replay"),
      h("button", { class: "obtn", title: "Replay speed", onclick: () => { S.orch.speed = { 1: 2, 2: 4, 4: 0.5, 0.5: 1 }[S.orch.speed || 1]; if (S.orch.playing) orchPlay(orchState().t); else orchRefresh(); } }, (S.orch.speed || 1) + "×"));
  }
  function orchestration() {
    const o = orchState();
    if (S.orch.auto && o.a && !o.running) { S.orch.auto = false; if ((S.orch.ticks || 0) < 5 && o.total) setTimeout(() => { if (S.c && S.view === "monitor") orchPlay(0); }, 60); }   // a sample that finished at once is played back once, so there is something to watch
    return h("div", { class: "card orch", id: "orch" },
      h("div", { class: "obar" }, orchButtons(o),
        h("input", { id: "orch-range", type: "range", min: 0, max: o.total, step: 1, value: o.t, "aria-label": "Position in the assessment", oninput: (ev) => { orchStop(); const v = +ev.target.value; S.orch.t = v >= orchState().total ? null : v; orchRefresh(); } }),
        h("span", { id: "orch-status", class: "ostatus" }, orchStatus(o)),
        o.a && !o.running && o.runs.length && !o.runs[0].plan ? h("button", { class: "btn sm", style: "flex:none", onclick: run(async () => setCase(await api("cases/" + S.c.reference + "/assess", {}))) }, "Assess again") : null),
      orchBody(o));
  }
  function orchBody(o) {
    const sel = S.orch.sel, pick = (s) => () => { S.orch.sel = sel && sel.kind === s.kind && sel.i === s.i && sel.id === s.id ? null : s; orchRefresh(); };
    const isSel = (s) => !!sel && sel.kind === s.kind && sel.i === s.i && sel.id === s.id;
    const lane = (name, say, cells, cls) => h("div", { class: "olane " + (cls || "") }, h("div", { class: "oname" }, h("b", null, name), say ? h("span", null, say) : null), cells);
    const col = (i) => "grid-column:" + (i + 2);
    // process layer, with what sent the case round again drawn above it
    const loops = Object.entries(o.again.reduce((m, x) => { m[x.trigger] = (m[x.trigger] || 0) + 1; return m; }, {}));
    const loopRow = loops.length ? h("div", { class: "oloops" }, h("svg", { viewBox: "0 0 1000 30", preserveAspectRatio: "none", "aria-hidden": "true" },
        loops.map((l, k) => { const x1 = OX(6) - k * 10, x0 = OX(0) + k * 10, top = 4 + k * 7; return [h("path", { d: "M" + x1 + ",30 C" + x1 + "," + top + " " + x0 + "," + top + " " + x0 + ",26", class: "loop" }), h("path", { d: "M" + (x0 - 3.5) + ",22 L" + x0 + ",29 L" + (x0 + 3.5) + ",22", class: "loop" })]; })),
      h("span", { class: "olooptxt", style: "left:" + (OX(3) / 10) + "%" }, "Loop back: " + loops.map(([tr, n]) => (TRIGGER[tr] || tr) + (n > 1 ? " ×" + n : "")).join(", ") + " · assessed " + o.passes + " times")) : null;
    const process = lane("Process layer", "what happens to a case", o.steps.map((s) => { const retries = s.runs.reduce((n, r) => n + (r.retries || 0), 0), took = s.runs.reduce((n, r) => n + r.duration_ms, 0);
      return h("button", { class: "ostep " + s.state + (isSel({ kind: "step", i: s.i }) ? " sel" : ""), style: col(s.i), onclick: pick({ kind: "step", i: s.i }), title: s.runs.map((r) => r.summary).join(" · ") },
        h("span", { class: "no" }, "0" + (s.i + 1)), h("b", null, s.title),
        h("span", { class: "st" }, s.state === "working" ? [h("span", { class: "spin" }), " working now"] : s.state === "person" ? "waits for a person" : s.state === "failed" ? "stopped" : s.state === "done" ? "done" + (s.st && o.passes > 1 ? " ×" + o.passes : "") + (s.st ? " · " + ms(Math.round(took * 10) / 10) : "") : "–", retries ? " · " + retries + " retry" : "")); }));
    // the boss agent: the orchestrator's plan for each step, and how far it got
    const boss = lane("Boss agent", "the orchestrator: plans, hands out, holds for people", o.steps.map((s) => { let head, sub, cls = s.state;
      if (s.st) { const all = [...s.runs, ...(s.now ? [s.now] : [])], tasks = all.reduce((n, r) => n + ((r.plan || {}).tasks || []).length, 0), done = s.runs.reduce((n, r) => n + ((r.plan || {}).done || 0), 0), by = (all[0] && all[0].plan && all[0].plan.by) || "";
        if (!all.length) { head = s.state === "working" ? "planning…" : "–"; sub = ""; if (s.state !== "working") cls = "waiting"; }
        else if (!all[0].plan) { head = "done"; sub = "plan not kept by the earlier version"; }
        else if (!tasks) { head = "no plan"; sub = "nothing to do here"; }
        else { head = done + "/" + tasks + " done"; sub = s.now ? "handing out " + (s.now.plan.tasks || []).length + " task(s)" : by ? "asked by " + by : ""; } }
      else if (s.i === 6) { head = s.state === "waiting" ? "–" : s.state === "done" ? "handed over" : "holds for a person"; sub = s.state === "waiting" ? "" : o.need + " finding(s) need a person"; }
      else { head = s.state === "done" ? "decision recorded" : s.state === "person" ? "waits for the decision" : "–"; sub = s.state === "done" ? "by " + S.c.decision.by : ""; }
      return h("button", { class: "oboss " + cls + (isSel({ kind: "step", i: s.i }) ? " sel" : ""), style: col(s.i), onclick: pick({ kind: "step", i: s.i }) }, head === "–" ? h("span", { class: "faint" }, "–") : h("span", null, h("span", { class: "who" }, "Boss · "), h("b", null, head)), sub ? h("span", { class: "sub" }, sub) : null); }));
    // harness -> agents: each run under its contract
    const chip = (r, live) => { const c = r.contract || {}, bad = c.kept === false, odd = !bad && r.status !== "ok", n = (c.promises || []).length, ok = (c.promises || []).filter((x) => x.ok).length;
      return h("button", { class: "oagent " + (live ? "working" : bad ? "bad" : odd ? "odd" : "ok") + (isSel({ kind: "run", id: r.id }) ? " sel" : ""), onclick: live ? null : pick({ kind: "run", id: r.id }), title: r.summary || "" },
        h("span", { class: "nm" }, live ? h("span", { class: "spin" }) : h("i", { class: "mark" }, bad ? "✕" : odd ? "!" : "✓"), short(r.name)),
        h("span", { class: "sub" }, live ? "running under its contract" : (bad ? (n - ok) + " of " + n + " promise(s) broken" : ok + "/" + n + " promises kept") + " · " + (r.model_calls ? r.model_calls + " model call(s)" : "code") + " · " + ms(r.duration_ms))); };
    const harness = lane("Harness → agents", "every agent runs under its contract", o.steps.map((s) => { let kids;
      if (s.st) { kids = s.runs.map((r) => chip(r)); if (s.now) kids.push(chip(s.now, true)); else if (s.liveStage) { const ag = S.cfg.agents.find((x) => x.stage === s.liveStage); if (ag) kids.push(chip({ id: "live", name: ag.name }, true)); } }
      else if (s.i === 6 && s.state !== "waiting") kids = [h("button", { class: "oagent person" + (isSel({ kind: "step", i: 6 }) ? " sel" : ""), onclick: pick({ kind: "step", i: 6 }) }, h("span", { class: "nm" }, h("i", { class: "mark" }, "☺"), "Caseworker"), h("span", { class: "sub" }, S.c.reviews.length + " review action(s)"))];
      else if (s.i === 7 && s.state !== "waiting") kids = [h("button", { class: "oagent " + (s.state === "done" ? "ok" : "person") + (isSel({ kind: "step", i: 7 }) ? " sel" : ""), onclick: pick({ kind: "step", i: 7 }) }, h("span", { class: "nm" }, h("i", { class: "mark" }, s.state === "done" ? "✓" : "☺"), "Caseworker"), h("span", { class: "sub" }, s.state === "done" ? S.c.status : "decides"))];
      return h("div", { class: "ocell", style: col(s.i) }, kids && kids.length ? kids : h("span", { class: "faint" }, "–")); }));
    // knowledge graph: what the harness handed each step from it, and what the case gave back
    const kn = (S.c.learned || {}).knowledge, afterRuns = !!o.a && !o.running && o.t >= o.runs.length && !!S.c.learned;
    const handed = o.steps.map((s) => { const ids = new Set(); let n = 0; const lv = {}; s.runs.forEach((r) => { const g = r.grounding; if (!g) return; (g.ids || []).forEach((x) => ids.add(x)); n = Math.max(n, g.nodes || 0); Object.entries(g.by_level || {}).forEach(([k, v]) => (lv[k] = Math.max(lv[k] || 0, v))); }); return { n: Math.max(n, ids.size), lv }; });
    const kgCells = o.steps.map((s) => { const g = handed[s.i], learned = s.i === 5 && afterRuns ? S.c.learned.entities : 0, out = s.i === 7 && s.state === "done";
      return h("button", { class: "ocount" + (isSel({ kind: "kg", i: s.i }) ? " sel" : ""), style: col(s.i), disabled: !g.n && !learned && !out, onclick: pick({ kind: "kg", i: s.i }) },
        g.n ? h("span", { class: "up", title: g.n + " graph node(s) handed to this step" }, "▲ " + g.n, h("span", { class: "lv" }, Object.keys(g.lv).map((k) => h("i", { style: "background:" + (LCOL[k] || "#7a8496"), title: (LVL[k] || k) + ": " + g.lv[k] })))) : null,
        learned ? h("span", { class: "down", title: learned + " node(s) of this case written back to the knowledge graph" }, "▼ " + learned + " learned") : null, out ? h("span", { class: "down", title: "The decision is written back to the knowledge graph" }, "▼ outcome") : null); });
    const kgBar = h("button", { class: "obarline kg" + (isSel({ kind: "kgbar" }) ? " sel" : ""), onclick: pick({ kind: "kgbar" }) }, h("b", null, "Knowledge graph"),
      kn ? h("span", null, kn.entities.toLocaleString() + " nodes · " + kn.relationships.toLocaleString() + " links · 4 levels") : h("span", null, "the workspace's graph · 4 levels"),
      kn && kn.levels ? h("span", { class: "lvls" }, ["industry", "domain", "solution", "customer", "added"].filter((k) => kn.levels[k]).map((k) => h("span", null, h("i", { style: "background:" + LCOL[k] }), LVL[k] + " " + kn.levels[k].toLocaleString()))) : null);
    const kg = h("div", { class: "olane kgl" }, h("div", { class: "oname" }, h("b", null, "Knowledge graph"), h("span", null, "▲ nodes handed · ▼ learned")), kgCells, h("div", { class: "ospan" }, kgBar));
    // shared memory: what each step read of what earlier steps left, and what it left itself
    const mem = o.steps.map((s) => ({ read: s.runs.reduce((n, r) => n + ((r.sections || {}).read || []).length + ((r.memory || {}).reads || []).length, 0), left: s.runs.reduce((n, r) => n + ((r.sections || {}).wrote || []).length + 1, 0) }));
    const arcs = {}; o.seen.forEach((r) => ((r.sections || {}).read || []).forEach((x) => (x.from || []).forEach((ag) => { const w = o.runs.find((y) => y.agent === ag), f = w ? o.stepOf(w.stage) : -1, to = o.stepOf(r.stage); if (f >= 0 && f < to) arcs[f + ">" + to] = (arcs[f + ">" + to] || 0) + 1; })));
    const recall = o.a && o.a.memory ? o.a.memory.recall || {} : {}, known = (recall.parties || []).length + (recall.identifiers || []).length, prior = o.seen.some((r) => ((r.memory || {}).reads || []).length), items = o.seen.length + new Set(o.seen.flatMap((r) => (r.sections || {}).wrote || [])).size;
    const hot = sel && sel.kind === "step" ? sel.i : sel && sel.kind === "mem" ? sel.i : sel && sel.kind === "run" ? o.stepOf((o.runs.find((r) => r.id === sel.id) || {}).stage) : o.now ? o.stepOf(o.now.stage) : -1;
    const memCells = o.steps.map((s) => h("button", { class: "ocount" + (isSel({ kind: "mem", i: s.i }) ? " sel" : ""), style: col(s.i), disabled: !mem[s.i].read && !mem[s.i].left, onclick: pick({ kind: "mem", i: s.i }) },
      mem[s.i].read ? h("span", { class: "up", title: "read from shared memory" }, "▲ " + mem[s.i].read + " read") : null, mem[s.i].left ? h("span", { class: "down", title: "left in shared memory" }, "▼ " + mem[s.i].left + " left") : null));
    const memBar = h("button", { class: "obarline mem" + (isSel({ kind: "membar" }) ? " sel" : ""), onclick: pick({ kind: "membar" }) }, h("b", null, "Shared memory"), h("span", null, items + " item(s)" + (items ? ": " + o.seen.length + " note(s), " + (items - o.seen.length) + " part(s) of the case file" : "")));
    const arcSvg = h("div", { class: "oarcs" }, h("svg", { viewBox: "0 0 1000 78", preserveAspectRatio: "none", "aria-hidden": "true" },
        Object.entries(arcs).map(([k, n]) => { const [f, to] = k.split(">").map(Number), x1 = OX(f) + 7, x2 = OX(to) - 7, d = Math.min(74, 16 + 11 * (to - f)), on = hot === f || hot === to;
          return [h("path", { d: "M" + x1 + ",1 C" + x1 + "," + d + " " + x2 + "," + d + " " + x2 + ",5", class: "arc" + (on ? " on" : "") }), h("path", { d: "M" + (x2 - 3.5) + ",8 L" + x2 + ",1 L" + (x2 + 3.5) + ",8", class: "arc head" + (on ? " on" : "") })]; }),
        prior && recall.episodes_searched ? [h("path", { d: "M60,40 C60,14 " + (OX(2) - 20) + ",40 " + (OX(2) - 16) + ",5", class: "arc prior" }), h("path", { d: "M" + (OX(2) - 19.5) + ",8 L" + (OX(2) - 16) + ",1 L" + (OX(2) - 12.5) + ",8", class: "arc head prior" })] : null),
      prior ? h("span", { class: "oprior" }, recall.episodes_searched ? "Before this case: " + recall.episodes_searched + " earlier case(s) searched, " + known + " thing(s) recognised" : "Before this case: no earlier case to recall yet") : null);
    const memory = h("div", { class: "olane meml" }, h("div", { class: "oname" }, h("b", null, "Shared memory"), h("span", null, "▲ read · ▼ left")), h("div", { class: "ospan" }, memBar), memCells, h("div", { class: "ospan" }, arcSvg));
    const legend = h("div", { class: "olegend" }, h("span", null, h("i", { class: "k working" }), "working now"), h("span", null, h("i", { class: "k person" }), "waits for a person"), h("span", null, h("i", { class: "k done" }), "done (×2: passes)"),
      h("span", null, h("i", { class: "k loop" }), "loop back: assessed again"), h("span", null, h("i", { class: "k arc" }), "read from shared memory"), h("span", null, h("i", { class: "k prior" }), "from earlier cases"), h("span", null, h("b", null, "Click anything for its detail")));
    return h("div", { id: "orch-body" }, h("div", { class: "oboard" }, loopRow, process, boss, harness, kg, memory), legend, sel ? orchDetail(o, sel) : null);
  }
  function orchDetail(o, sel) {
    const close = h("button", { class: "btn sm ghost right", onclick: () => { S.orch.sel = null; orchRefresh(); } }, "Close"), a = o.a;
    const toKnowledge = (id) => run(async () => { await top("knowledge")(); if (id) await kEntity(id)(); });
    const runBlock = (r) => { const c = r.contract || {}, g = r.grounding, sec = r.sections || {}, m = r.memory || {}, note = a && a.memory ? a.memory.working.find((n) => n.by === r.agent || n.key === r.stage + ".summary") : null;
      return h("div", { class: "orun" }, h("div", { class: "row" }, h("b", null, r.name), pill(r.status === "ok" ? "pass" : r.status === "failed" ? "fail" : "review", r.status), h("span", { class: "mono small muted" }, r.id), h("span", { class: "small muted" }, ms(r.duration_ms) + " · " + r.model + (r.prompt_version ? " · prompt " + r.prompt_version : ""))),
        h("p", { class: "small", style: "margin:4px 0 8px" }, r.summary), (r.notes || []).map((n) => h("p", { class: "small muted" }, n)),
        h("div", { class: "ogrid" },
          h("div", null, h("h4", null, "The boss agent's plan"), ((r.plan || {}).tasks || []).length ? h("ol", null, r.plan.tasks.map((t, k) => h("li", { class: k < r.plan.done ? "ok" : "" }, t))) : h("p", { class: "small muted" }, "No plan: nothing for this agent to do in this case."), h("p", { class: "small muted" }, "Asked by " + ((r.plan || {}).by || "–") + " · " + ((r.plan || {}).trigger || ""))),
          h("div", null, h("h4", null, "Contract " + (c.version ? "v" + c.version : "")), (c.needs || []).map((x) => h("div", { class: "ock " + (x.ok ? "ok" : "bad") }, h("i", null, x.ok ? "✓" : "✕"), h("span", null, h("b", null, "Needs: "), x.detail))), (c.promises || []).map((x) => h("div", { class: "ock " + (x.ok ? "ok" : "bad") }, h("i", null, x.ok ? "✓" : "✕"), h("span", null, x.text, h("span", { class: "muted" }, " " + x.detail)))),
            h("p", { class: "small muted" }, "If it fails: " + (c.on_failure || "–") + (r.budget && r.budget.max_calls ? " · model budget " + r.budget.calls + "/" + r.budget.max_calls + " calls" : "") + (r.throttle && r.throttle.waited_ms ? " · waited " + r.throttle.waited_ms + " ms" : ""))),
          h("div", null, h("h4", null, "Handed from the knowledge graph"), g && g.nodes ? [h("div", { class: "chips" }, Object.entries(g.by_class).map(([k, v]) => h("span", { class: "chip", style: "cursor:default" }, v + " " + words(k)))), h("div", { class: "chips", style: "margin-top:5px" }, Object.entries(g.by_level).map(([k, v]) => h("span", { class: "chip", style: "cursor:default;border-color:" + (LCOL[k] || "#ccc") }, (LVL[k] || k) + " level: " + v))),
              h("div", { class: "chips", style: "margin-top:5px" }, g.ids.slice(0, 6).map((id) => h("button", { class: "chip", onclick: toKnowledge(id), title: "Open it in the knowledge graph" }, id.split("/").pop().replace(/-/g, " ").slice(0, 34))), g.nodes > 6 ? h("span", { class: "small muted" }, "and " + (g.nodes - 6) + " more") : null)] : h("p", { class: "small muted" }, g ? "Its contract names graph nodes, and this use case has none of them yet." : "Its contract asks for nothing from the graph."),
            r.graph_writes && (r.graph_writes.nodes || r.graph_writes.edges) ? h("p", { class: "small muted", style: "margin-top:5px" }, "Wrote +" + r.graph_writes.nodes + " nodes, +" + r.graph_writes.edges + " links to the case graph.") : null),
          h("div", null, h("h4", null, "Shared memory"), (sec.read || []).map((x) => h("div", { class: "small" }, "▲ read ", h("b", null, x.section), (x.from || []).length ? " left by " + x.from.join(", ") : "")), (m.reads || []).map((x) => h("div", { class: "small" }, "▲ read ", h("b", null, x.replace("workspace:", "the workspace's ")))),
            (sec.wrote || []).map((x) => h("div", { class: "small" }, "▼ left ", h("b", null, x))), note ? h("div", { class: "small" }, "▼ left a note: ", h("span", { class: "muted" }, note.value)) : null, (m.refused || []).map((x) => h("div", { class: "small", style: "color:var(--bad)" }, "refused: " + x)),
            r.io ? h("p", { class: "mono small muted", style: "margin-top:5px" }, r.io.read.slice(0, 8) + " → " + r.io.wrote.slice(0, 8)) : null))); };
    let title, body;
    if (sel.kind === "run") { const r = o.runs.find((x) => x.id === sel.id); if (!r) return null; title = "Agent run"; body = runBlock(r); }
    else if (sel.kind === "kgbar") { const kn = (S.c.learned || {}).knowledge; title = "The knowledge graph and this case";
      body = [h("p", { class: "small" }, "The harness hands each agent only the graph nodes its contract names. When the assessment ends, the case is written back: its companies, products, reference numbers and findings, each with the line it came from."),
        kn ? kv([["In the graph now", kn.entities.toLocaleString() + " nodes, " + kn.relationships.toLocaleString() + " links"], ["By level", Object.entries(kn.levels || {}).map(([k, v]) => (LVL[k] || k) + " " + v).join(" · ")], ["This case gave", S.c.learned.entities + " nodes, " + S.c.learned.relationships + " links"], ["Learned at", when(S.c.learned.at)]]) : h("p", { class: "small muted" }, "This case has not been written to the graph yet."),
        h("button", { class: "btn sm", style: "margin-top:8px", onclick: toKnowledge() }, "Open the knowledge graph")]; }
    else if (sel.kind === "membar") { const rc = a && a.memory ? a.memory.recall || {} : {}; title = "Shared memory of this case";
      body = [h("p", { class: "small" }, "Agents never call each other. Each one reads what earlier agents left in the case file and leaves its own part and a note. The harness refuses a read or a write its contract does not allow."),
        a && a.memory ? h("table", { style: "margin-top:8px" }, h("tbody", null, a.memory.working.map((n) => h("tr", null, h("td", { class: "small mono", style: "width:150px" }, n.by), h("td", { class: "small" }, n.value))))) : null,
        (rc.parties || []).length + (rc.identifiers || []).length ? h("p", { class: "small", style: "margin-top:8px" }, h("b", null, "From earlier cases: "), [...(rc.parties || []).map((x) => x.name + " (" + x.count + " case(s))"), ...(rc.identifiers || []).map((x) => x.type + " " + x.value + " (" + x.count + ")")].join("; ")) : null]; }
    else { const s = o.steps[sel.i]; title = (sel.kind === "kg" ? "Knowledge graph · " : sel.kind === "mem" ? "Shared memory · " : "") + "0" + (s.i + 1) + " " + s.title;
      if (s.st) body = s.runs.length ? s.runs.map(runBlock) : h("p", { class: "small muted" }, s.state === "working" ? "Working now. Its detail appears when it finishes." : "Not reached yet.");
      else if (s.i === 6) body = [h("p", { class: "small" }, s.state === "waiting" ? "Not reached yet." : "The boss agent stops here: " + o.need + " finding(s) need a person. Nothing is decided by an agent."), S.c.reviews.length ? h("table", { style: "margin-top:8px" }, h("tbody", null, S.c.reviews.slice(-8).map((v) => h("tr", null, h("td", { class: "small muted", style: "width:130px" }, when(v.at)), h("td", { class: "small" }, v.by), h("td", { class: "small" }, v.summary || v.action || v.kind || ""))))) : null,
        o.again.length ? h("p", { class: "small muted", style: "margin-top:8px" }, "Assessed " + o.passes + " times: " + o.again.map((x) => x.id + " because " + (TRIGGER[x.trigger] || x.trigger)).join("; ") + ".") : null, s.state !== "waiting" ? h("button", { class: "btn sm", style: "margin-top:8px", onclick: go("decision") }, "Open the decision workspace") : null];
      else body = S.c.decision && s.state === "done" ? [kv([["Decision", S.c.status], ["By", S.c.decision.by], ["When", when(S.c.decision.at)], ["Differs from the recommendation", S.c.decision.override ? "yes" : "no"], ["Note", S.c.decision.note]]), h("p", { class: "small muted", style: "margin-top:6px" }, "The outcome is written to the knowledge graph and to the workspace's memory, so the next case that meets the same company or reference number is told.")] : h("p", { class: "small muted" }, "A person decides. Until then nothing is filed and nothing is learned as an outcome."); }
    return h("div", { class: "odetail" }, h("div", { class: "row", style: "margin-bottom:8px" }, h("h3", null, title), close), body);
  }

  function monitor() {
    const a = A(), pr = S.c.progress || {}, live = S.c.live || { stages: {}, runs: [] };
    const runs = pr.state === "running" ? live.runs : a ? a.runs : [];
    return [section("Agent orchestration", "Watch the case move. The boss agent plans each step, the harness runs each agent under its contract, and every agent works from the same knowledge graph and the same shared memory. Play it back, or click any part for its detail."),
      pr.state === "failed" ? h("div", { class: "banner review", style: "margin-bottom:14px" }, h("b", null, "The assessment stopped at " + pr.stage), h("p", null, pr.error)) : null,
      orchestration(), h("div", { style: "height:16px" }),
      cardOf("Agent runs", runs.length ? h("table", null, h("thead", null, h("tr", null, ["Run", "Agent", "Status", "Contract", "Time", "Model", "Prompt", "Tool calls", "Graph writes", "Tokens in / out"].map((x) => h("th", null, x)))), h("tbody", null, runs.map((r) => h("tr", null, h("td", { class: "mono small" }, r.id), h("td", null, h("b", null, r.name), h("div", { class: "small muted" }, r.summary)), h("td", null, pill(r.status === "ok" ? "pass" : r.status === "failed" ? "fail" : "review", r.status), (r.notes || []).map((n) => h("div", { class: "small muted" }, n))),
        h("td", null, r.contract ? [pill(r.contract.kept ? "pass" : "fail", r.contract.kept ? "kept" : "not kept"), h("div", { class: "small muted" }, r.contract.promises.length + " promise(s) checked" + (r.memory && r.memory.reads.length ? " · read " + r.memory.reads.join(", ") : "") + (r.throttle && r.throttle.waited_ms ? " · waited " + r.throttle.waited_ms + " ms" : "")), (r.contract.broken || []).map((b) => h("div", { class: "small", style: "color:var(--bad)" }, b))] : "–"),
        h("td", { class: "mono small" }, r.duration_ms + " ms"), h("td", { class: "small" }, r.model), h("td", { class: "small mono" }, r.prompt_version || "–"), h("td", { class: "small" }, (r.tool_calls || []).map((t) => h("div", null, t.tool + " · " + t.status)), !(r.tool_calls || []).length ? "–" : null), h("td", { class: "small mono" }, "+" + r.graph_writes.nodes + " / +" + r.graph_writes.edges), h("td", { class: "small mono" }, r.input_tokens + " / " + r.output_tokens))))) : h("p", { class: "muted" }, "No run yet.")),
      a ? h("p", { class: "small muted", style: "margin-top:10px" }, "End to end: " + a.metrics.duration_ms + " ms · " + a.metrics.model_calls + " model call(s) · " + a.metrics.rules + " rule(s) · " + a.metrics.pages + " page(s) · reads: " + a.model.provider + ".") : null,
      a && a.memory ? h("details", { class: "card", style: "margin-top:12px" }, h("summary", null, "Working memory: the note each agent left for the next (" + a.memory.working.length + ")"), h("table", { style: "margin-top:8px" }, h("tbody", null, a.memory.working.map((n) => h("tr", null, h("td", { class: "small mono", style: "width:150px" }, n.by), h("td", { class: "small" }, n.value)))))) : null,
      a ? h("details", { class: "card", style: "margin-top:12px", ontoggle: run(async (ev) => { if (ev.target.open && !S.sel.ledger) { S.sel.ledger = await api("ledger?limit=200&case=" + encodeURIComponent(S.c.reference)); render(); } }), open: !!S.sel.ledger }, h("summary", null, "Provenance ledger: every action on this case, chained"),
        S.sel.ledger ? [h("p", { class: "small muted", style: "margin:8px 0" }, "Chain of the whole workspace: ", S.sel.ledger.verify.ok ? pill("pass", "intact, " + S.sel.ledger.verify.entries + " entries") : pill("fail", "broken at entry " + S.sel.ledger.verify.broken_at)),
          h("table", null, h("thead", null, h("tr", null, ["#", "When", "Who", "What", "Fingerprint"].map((x) => h("th", null, x)))), h("tbody", null, S.sel.ledger.entries.slice().reverse().map((e) => h("tr", null, h("td", { class: "mono small" }, e.n), h("td", { class: "small muted" }, when(e.at)), h("td", { class: "small" }, e.actor), h("td", { class: "small" }, e.summary), h("td", { class: "mono small" }, e.hash.slice(0, 10))))))] : null) : null,
      !a && pr.state !== "running" ? h("button", { class: "btn primary", style: "margin-top:12px", onclick: run(async () => setCase(await api("cases/" + S.c.reference + "/assess", {}))) }, "Assess the case") : null];
  }
  function decision() {
    const a = A(), need = a.findings.filter((f) => ["fail", "missing", "review"].includes(f.status));
    const draft = (kind) => run(async () => { S.draft = await api("cases/" + S.c.reference + "/correspondence", { kind }); render(); });
    const decide = (d, label) => h("button", { class: "btn" + (d === "approve" ? " primary" : ""), onclick: run(async () => { const v = await form(label, [{ k: "note", label: "Note (required when it differs from the recommendation)", type: "textarea" }], label); if (v) setCase(await api("cases/" + S.c.reference + "/decision", { decision: d, note: v.note })); }) }, label);
    return [section("Decision workspace", "The caseworker decides. The recommendation and every finding are here to inspect, correct and overrule; a decision that differs from the recommendation needs a note."),
      h("div", { class: "stack" }, banner(a.recommendation),
        S.c.decision ? cardOf("Decision recorded", kv([["Decision", S.c.status], ["By", S.c.decision.by], ["When", when(S.c.decision.at)], ["On assessment", S.c.decision.assessment], ["Differs from recommendation", S.c.decision.override ? "yes" : "no"], ["Note", S.c.decision.note]])) : null,
        (a.unresolved || []).length ? cardOf("Possible entity matches to settle", a.unresolved.map((m) => h("div", { class: "row", style: "margin-bottom:6px" }, m.reason, matchButtons(m)))) : null,
        h("div", null, h("h3", { style: "margin:4px 0 10px;font-size:15px" }, "Findings that need a person (" + need.length + ")"), h("div", { class: "stack" }, need.map((f) => findingCard(f, { review: true })), !need.length ? h("p", { class: "muted" }, "None.") : null)),
        cardOf("Correspondence", h("div", { class: "row", style: "margin-bottom:10px" }, h("button", { class: "btn sm", onclick: draft("evidence_request") }, "Draft an evidence request"), h("button", { class: "btn sm", onclick: draft("decision_note") }, "Draft a decision note")),
          S.draft ? (S.draft.body ? [h("label", { class: "f" }, h("span", null, "Subject"), h("input", { type: "text", value: S.draft.subject })), h("label", { class: "f", style: "margin-top:8px" }, h("span", null, "Draft (" + S.draft.method + "). " + S.draft.note), h("textarea", { style: "min-height:190px", value: S.draft.body }))] : h("p", { class: "muted" }, S.draft.note)) : h("p", { class: "muted small" }, "A draft is written from the findings for you to edit. Nothing is sent from here.")),
        cardOf("Decide", h("div", { class: "row" }, decide("approve", "Approve"), decide("request_evidence", "Request evidence"), decide("escalate", "Escalate for review"), decide("reject", "Reject"))),
        cardOf("Content repository", h("p", { class: "small muted", style: "margin-bottom:8px" }, S.cfg.repository.name + ": " + S.cfg.repository.detail + (S.cfg.repository.note ? " " + S.cfg.repository.note : "")),
          S.c.filed ? kv([["Filed", when(S.c.filed.filed_at)], ["Documents", S.c.filed.documents.map((d) => d.name + " → " + d.repository_id).join("; ")]]) : null,
          h("button", { class: "btn sm", style: "margin-top:8px", onclick: run(async () => { await api("cases/" + S.c.reference + "/file", {}); toast("Filed to the repository"); open(S.c.reference, "decision"); }) }, S.c.filed ? "File again" : "File the case and its assessment")))];
  }
  function audit() {
    if (!S.fb || S.fb.profile !== S.c.profile) { api("feedback/" + S.c.profile).then((fb) => { S.fb = Object.assign(fb, { profile: S.c.profile }); render(); }).catch((e) => toast(e.message)); }
    const fb = S.fb && S.fb.profile === S.c.profile ? S.fb : null;
    const act = (p, decision, accept) => run(async () => { await api("feedback/" + S.c.profile + "/" + p.id, { decision, accept_changes: !!accept }); S.fb = null; render(); });
    const proposal = (p) => {
      const open = p.status === "proposed" || p.status === "held", r = p.regression;
      return h("div", { style: "padding:8px 0;border-bottom:1px solid var(--line)" },
        h("div", { class: "row" }, pill({ proposed: "info", approved: "pass", rejected: "", held: "review" }[p.status], p.status), h("b", null, p.summary)),
        h("div", { class: "small muted" }, p.kind + " · from case " + p.origin.case + " (" + p.origin.by + ")" + (p.overlay_version ? " · promoted as vocabulary v" + p.overlay_version : "")),
        r ? h("div", { class: "small", style: "margin-top:4px" }, "Regression on " + r.samples + " sample(s), " + r.checks + " checks: " + (r.passed ? "no change" : r.changed.length + " change(s): " + r.changed.join("; "))) : null,
        open ? h("div", { class: "row", style: "margin-top:6px" },
          p.status === "held" ? h("button", { class: "btn sm", onclick: act(p, "approve", true) }, "Accept the changes and approve") : h("button", { class: "btn sm", onclick: act(p, "approve") }, "Approve (runs regression)"),
          h("button", { class: "btn sm", onclick: act(p, "reject") }, "Reject")) : null);
    };
    const proposals = !fb ? h("p", { class: "muted" }, "Loading…") : fb.proposals.length ? fb.proposals.map(proposal) : h("p", { class: "muted small" }, "No proposals yet. Correct a classification or settle an entity match to produce one.");
    const versions = S.c.documents.flatMap((d) => d.versions.map((v) => h("tr", null, h("td", null, v.name || d.name, d.removed ? " (removed)" : ""), h("td", { class: "mono small" }, "v" + v.v + (v.v === d.current ? " current" : "")),
      h("td", { class: "mono small" }, (v.sha256 || "").slice(0, 12)), h("td", { class: "small muted" }, when(v.uploaded_at) + (v.note ? " · " + v.note : "")))));
    return [section("Feedback and audit history", "Every event on the case, each document version, and the improvement proposals that corrections produced. A proposal changes nothing until it is approved, and approval runs a regression on the bundled samples first."),
      h("div", { class: "split" }, cardOf("Audit trail", h("ul", { class: "timeline" }, [...S.c.events].reverse().map((e) => h("li", null, h("time", null, when(e.at) + " · " + e.by + " · " + e.kind), e.detail)))),
        h("div", { class: "stack" }, cardOf("Document versions", h("table", null, h("tbody", null, versions))), cardOf("Improvement proposals" + (fb ? " · vocabulary v" + fb.overlay.version : ""), proposals)))];
  }

  // ---------------------------------------------------------------------------------------------- graph
  const COLORS = { Case: "#0b1220", Document: "#4a6fb5", DocumentVersion: "#8fa9d8", EvidenceAssertion: "#c3ccd9", Party: "#ee6c2b", GoodsItem: "#1b7f52", ProductCharacteristic: "#79c3a1", Invoice: "#a8589e", Shipment: "#a8589e", Declaration: "#a8589e", ReferenceLine: "#c79a1a", RuleEvaluation: "#7a8496", Rule: "#b3bac6", Recommendation: "#b8342b" };
  let layoutKey = "", layout = null;
  function graph() {
    const g = A().graph, on = (n) => S.layers[n.layer] || n.layer === "case" || (S.sel.path || []).includes(n.id) || n.id === S.sel.node;
    const nodes = g.nodes.filter(on), ids = new Set(nodes.map((n) => n.id)), edges = g.edges.filter((e) => ids.has(e.from) && ids.has(e.to));
    if (!S.layers.assertion) {   // with the assertions folded away, a document is joined straight to what its facts mention
      const seen = new Set(edges.map((e) => e.from + ">" + e.to));
      g.edges.forEach((e) => { const doc = e.from.split(".")[0], key = doc + ">" + e.to; if ((e.type === "MENTIONS" || e.type === "SUPPORTS") && e.from.includes(".") && !ids.has(e.from) && ids.has(doc) && ids.has(e.to) && !seen.has(key)) { seen.add(key); edges.push({ from: doc, to: e.to, type: e.type + " (through its facts)" }); } });
    }
    const key = A().id + S.c.reference + nodes.length + ":" + edges.length, W = 1100, H = 600;
    if (key !== layoutKey) {
      // Fruchterman-Reingold: nodes repel, edges pull, the temperature cools; deterministic start so a case always draws the same
      const pos = {}, n0 = nodes.length || 1, k = Math.sqrt((W * H) / n0) * 0.72;
      nodes.forEach((n, i) => { const t = i * 2.399963, r = n.layer === "case" ? 0 : Math.sqrt((i + 0.5) / n0) * Math.min(W, H) * 0.46; pos[n.id] = { x: W / 2 + r * Math.cos(t) * 1.5, y: H / 2 + r * Math.sin(t) }; });
      for (let it = 0; it < 320; it++) {
        const f = {}, temp = 34 * (1 - it / 320) + 0.6; nodes.forEach((n) => (f[n.id] = { x: 0, y: 0 }));
        for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) { const a = pos[nodes[i].id], b = pos[nodes[j].id], dx = a.x - b.x || 0.01, dy = a.y - b.y || 0.01, d = Math.max(Math.sqrt(dx * dx + dy * dy), 4), rep = (k * k) / d; f[nodes[i].id].x += (dx / d) * rep; f[nodes[i].id].y += (dy / d) * rep; f[nodes[j].id].x -= (dx / d) * rep; f[nodes[j].id].y -= (dy / d) * rep; }
        edges.forEach((e) => { const a = pos[e.from], b = pos[e.to], dx = a.x - b.x, dy = a.y - b.y, d = Math.max(Math.sqrt(dx * dx + dy * dy), 4), att = (d * d) / k; f[e.from].x -= (dx / d) * att; f[e.from].y -= (dy / d) * att; f[e.to].x += (dx / d) * att; f[e.to].y += (dy / d) * att; });
        nodes.forEach((n) => { const p = pos[n.id], v = f[n.id], m = Math.sqrt(v.x * v.x + v.y * v.y) || 1; p.x += (v.x / m) * Math.min(m, temp) + (W / 2 - p.x) * 0.012; p.y += (v.y / m) * Math.min(m, temp) + (H / 2 - p.y) * 0.02; p.x = Math.min(W - 150, Math.max(24, p.x)); p.y = Math.min(H - 18, Math.max(18, p.y)); });
      }
      layoutKey = key; layout = pos;
    }
    const path = new Set(S.sel.path || []), hot = (e) => (path.has(e.from) || e.from === S.sel.node) && (path.has(e.to) || e.to === S.sel.node);
    const svg = h("svg", { class: "graph", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Case knowledge graph" },
      edges.map((e) => h("line", { x1: layout[e.from].x, y1: layout[e.from].y, x2: layout[e.to].x, y2: layout[e.to].y, class: hot(e) ? "hot" : "" }, h("title", null, e.type))),
      nodes.map((n) => h("g", { class: "nd" + (n.id === S.sel.node || path.has(n.id) ? " sel" : ""), transform: "translate(" + layout[n.id].x + "," + layout[n.id].y + ")", onclick: () => { S.sel.node = n.id; S.sel.path = null; render(); } },
        h("circle", { r: n.layer === "case" ? 11 : n.layer === "assertion" ? 4.5 : 7.5, fill: COLORS[n.type] || "#7a8496", stroke: "#fff", "stroke-width": 1.5 }), n.layer !== "assertion" || n.id === S.sel.node ? h("text", { x: 10, y: 4 }, n.label.length > 34 ? n.label.slice(0, 33) + "…" : n.label) : null, h("title", null, n.type + ": " + n.label))));
    const sel = g.nodes.find((n) => n.id === S.sel.node), nb = sel ? g.edges.filter((e) => e.from === sel.id || e.to === sel.id) : [], name = (id) => (g.nodes.find((n) => n.id === id) || {}).label || id;
    const types = [...new Set(nodes.map((n) => n.type))];
    return [section("Entity relationship graph", "The case as a graph: documents and versions, the facts taken from them, the parties, goods and references they share, the reference lines and the reasoning built on top. Click a node to see what it connects to."),
      h("div", { class: "row", style: "margin-bottom:10px" }, h("div", { class: "seg" }, [["document", "Documents"], ["entity", "Entities"], ["reference", "Reference"], ["reasoning", "Reasoning"], ["assertion", "Evidence assertions"]].map(([k, l]) => h("button", { "aria-pressed": String(!!S.layers[k]), onclick: () => { S.layers[k] = !S.layers[k]; render(); } }, l))),
        h("span", { class: "small muted right" }, nodes.length + " of " + g.nodes.length + " nodes · " + edges.length + " edges"), S.sel.path ? h("button", { class: "btn sm", onclick: () => { S.sel.path = null; render(); } }, "Clear path") : null),
      h("div", { class: "split", style: "grid-template-columns:minmax(0,2.4fr) minmax(0,1fr)" }, h("div", null, svg, h("div", { class: "chips small", style: "margin-top:8px" }, types.map((t) => h("span", { class: "row", style: "gap:5px;margin-right:8px" }, h("span", { style: "width:10px;height:10px;border-radius:50%;display:inline-block;background:" + (COLORS[t] || "#7a8496") }), t)))),
        cardOf(sel ? sel.type : "Select a node", sel ? [h("p", { style: "font-weight:650;margin-bottom:8px;overflow-wrap:anywhere" }, sel.label), kv(Object.entries(sel.props || {}).map(([k, v]) => [k.replace(/_/g, " "), String(v)])), h("h3", { style: "margin-top:12px" }, "Connections (" + nb.length + ")"),
          nb.slice(0, 30).map((e) => h("div", { class: "src", style: "margin-bottom:4px", onclick: () => { S.sel.node = e.from === sel.id ? e.to : e.from; const n = g.nodes.find((x) => x.id === S.sel.node); if (n) S.layers[n.layer] = true; render(); } }, h("span", { class: "muted" }, e.from === sel.id ? e.type + " → " : "← " + e.type + " "), name(e.from === sel.id ? e.to : e.from)))] : h("p", { class: "muted small" }, "Or open a finding and choose “Show graph path” to see the chain of evidence behind it.")))];
  }

  // ---------------------------------------------------------------------------------------------- assistant
  function chat() {
    if (!S.chat) return h("button", { class: "chatbtn", onclick: () => { S.chat = true; render(); } }, "Ask the case");
    const log = h("div", { class: "log" }, h("div", { class: "msg a" }, "Ask about this case. I answer from its documents and graph, cite what I used, and say so when they do not hold the answer."),
      S.chatLog.map((m) => h("div", { class: "msg " + m.r + (m.no ? " no" : "") }, m.t, m.src && m.src.length ? h("div", { class: "chips", style: "margin-top:6px" }, m.src.slice(0, 5).map((s) => h("span", { class: "chip", onclick: () => (s.doc ? openSource(s) : s.id ? (S.view = "provenance", S.filter = { status: "all", family: "all" }, render()) : null) }, s.doc_name ? s.doc_name + (s.page ? " p" + s.page + (s.line ? " l" + s.line : "") : "") : s.id || s.kind))) : null)));
    const input = h("input", { type: "text", placeholder: "Type your question", "aria-label": "Question" });
    setTimeout(() => { log.scrollTop = log.scrollHeight; input.focus(); }, 0);
    return h("div", { class: "chat", role: "dialog", "aria-label": "Case assistant" }, h("header", null, "Case assistant", h("button", { class: "right", style: "background:none;border:0;color:#fff;cursor:pointer", "aria-label": "Close", onclick: () => { S.chat = false; render(); } }, "✕")), log,
      h("form", { onsubmit: run(async () => { const q = input.value.trim(); if (!q) return; S.chatLog.push({ r: "u", t: q }); render(); const out = await api("cases/" + S.c.reference + "/ask", { question: q }); S.chatLog.push({ r: "a", t: out.answer, no: !out.grounded, src: out.sources }); render(); }) }, input, h("button", { class: "btn primary", type: "submit" }, "Send")));
  }

  start();
})();
