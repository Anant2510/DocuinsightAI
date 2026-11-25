# DocuInsights

Give it the documents. Get back a recommendation you can check.

In four sentences:

1. **Put the documents in.** A case is a handful of documents and a few facts about it.
2. **Agents read and link them.** Each document is named, its facts are lifted with the page and line they came from,
   and the same company or reference number is joined across documents.
3. **Rules check them.** Is anything missing, do the dates and amounts hold, do the documents agree? These checks are
   code, never a model's opinion.
4. **A person decides.** One of three recommendations with its reasons; every reason opens the line it rests on.

In full: DocuInsights classifies the documents, extracts facts with source anchors, resolves the parties, goods and
references the documents share, writes a case knowledge graph, checks the evidence the use case requires, retrieves
date-relevant reference content, runs deterministic rules, finds contradictions across documents, verifies that every
finding is supported by a source, and hands a caseworker a traceable recommendation. The caseworker reviews, corrects
and decides. Corrections become governed improvement proposals. A "what if" reruns the affected checks. What each case
teaches is kept: the workspace remembers it and its knowledge graph grows.

It is one engine with three ways in:

| Way in | What it is | Where |
| --- | --- | --- |
| Standalone accelerator | The workbench and its API, on its own | `python -m docuinsights serve` |
| CX Nova agent pack | Fifteen `di_*` agents and four flows on this layer; the workbench mounted at `/docuinsights` | `config/packs/docuinsights.yaml`, `src/caf/accelerators/docuinsights.py` |
| Behind another system | A REST surface to submit a package and read the assessment, and a repository connector | `/api/v1/cases`, `src/docuinsights/repository.py` |

The engine (`src/docuinsights`) imports nothing from this layer. The layer imports the engine.

## Generic by construction: profiles

Nothing in the engine names a customer or an industry. A use case is a **profile**, one YAML file under
`src/docuinsights/profiles/`:

| Section | What it declares |
| --- | --- |
| `case` | the case facts asked for at intake (dates, type, flags that switch conditional evidence on) |
| `document_types` | each type, the phrases that signal it, and its fields with their types and labels |
| `entities` | which fields are party mentions (and in which role), goods descriptions, references, product characteristics |
| `evidence` | mandatory, conditional (`when: case.<flag>`) and alternative (`any_of`) evidence |
| `reference_sources` | external references to retrieve for a date, and classification aids over a hierarchy |
| `rules` | deterministic rules: `date_interval`, `date_order`, `amounts_match`, `amount_limit`, `codes_consistent` |
| `consistency` | the same fact compared across documents, by kind: `party`, `number`, `text`, `ref` |
| `outcomes`, `correspondence`, `counterfactuals` | the wording of the three outcomes, letter templates, named what-if scenarios |
| `synonyms` | the governed vocabulary (the feedback loop proposes additions; nothing is added without approval) |
| `memory` | what the workspace's memory watches for: `duplicates: [Invoice]` sends a reference number another case already quotes to a person |
| `order`, `sector`, `plain` | where the use case sits in a list, who runs it, and what it does in one sentence anyone can read |
| `samples` | bundled synthetic cases |

Five profiles ship, to show the same engine on unrelated domains. The plainest comes first:

| Profile | Who runs it | What it checks | Samples |
| --- | --- | --- | --- |
| `supplier_invoice` | Finance operations | an invoice against its purchase order and proof of receipt (a three-way match); an invoice already seen | clean, mismatch, duplicate |
| `insurance_claim` | Insurance | a claim against its policy schedule: cover dates, notification, the amount, the names | clean, out_of_cover |
| `loan_application` | Banking and lending | what an applicant declared against the payslip, the bank statement and the employer's letter | clean, income_mismatch |
| `customs_claim` | Customs and trade | evidence, consistency, and a tariff heading read for the case's relevant date | review, positive, contradiction, temporal |
| `trade_finance` | Trade finance | a presentation under a documentary credit against the credit's terms | discrepant |

A new use case (onboarding, procurement, compliance, grants, anything that arrives as a set of documents to check) is
a new file: no code changes and no new agents. Point
`DOCUINSIGHTS_PROFILES_DIR` at a folder to add profiles without touching the package. The rules, tolerances and
classification aids in the shipped profiles are **illustrative**: replace them with the approved policy of whoever
uses the profile.

## The agents

| Agent | Stage | Does | Model |
| --- | --- | --- | --- |
| Intake | 1 | registers the case, checks each file, keeps immutable versions with SHA-256, reads them into text | scans only |
| Classification | 2 | names each document, with confidence, beside the uploader's category | yes, verified against the profile's signals |
| Extraction | 2 | lifts declared fields with page, line and the line as printed; a value whose line cannot be found is marked unverified | yes, verified against the text |
| Entity Resolution | 3 | links repeated parties, goods, references; near-matches go to a person | no |
| Knowledge Graph | 4 | case, documents, versions, assertions, entities, provenance edges | no |
| Evidence Completeness | 5 | mandatory, conditional, alternative evidence; shows how an absence was established | no |
| Reference | 6 | retrieves reference content for a date with provenance; walks the hierarchy from stated characteristics | no |
| Policy | 6 | executes the rules and shows each calculation, under a rule version | no |
| Contradiction | 7 | compares the same fact across documents | no |
| Verification | 8 | source coverage per finding, blocks unsupported conclusions, aggregates the recommendation | no |
| Counterfactual | on demand | changes one fact on a copy, reruns, reports what moved | no |
| Correspondence | on demand | drafts an evidence request or decision note; a model may polish, every item must survive | optional |
| Feedback | on demand | turns corrections into proposals; approval runs a regression on the bundled samples | no |
| Case Assistant | on demand | answers from the graph and the documents, cites sources, declines what they do not hold | yes, grounded |
| Repository | on demand | files the case and its assessment metadata to the content repository | no |

The Case Orchestrator of the standalone accelerator is `docuinsights.pipeline`. On this layer the orchestrator is the
layer's own: the flow `di_case_assessment` runs one agent per stage.

**What a model never does:** an evidence decision, a date or value calculation, a comparison, a classification
conclusion, or the recommendation. Without a model (`offline`) the reading steps run on the profile's signals and
labels and every screen says so.

## The foundation under the agents

Six things every agent runs on, the same for every use case. The workbench shows how each stands under
**How it is governed**; `GET /api/platform` returns the same as JSON.

### Agent contracts

`src/docuinsights/foundation/contracts.yaml` holds one contract per agent (16, the orchestrator included):

| Clause | Meaning | Enforced |
| --- | --- | --- |
| `purpose` | what the agent is for, in one sentence | shown in the catalogue |
| `needs` | what must be true before it starts (documents read, facts extracted ...) | checked before the run; unmet, the agent does not run |
| `promises` | what is true when it ends (every value anchored or flagged, every rule result under a version ...) | checked after the run |
| `writes` | the parts of the case it may change | a change anywhere else breaks the contract |
| `never` | what it must not do | the model and memory clauses below enforce the ones that can be enforced |
| `model` | `none`, or `optional` with a tier and a budget of calls and tokens for one run | `none` hands the agent no model; a call past the budget is refused |
| `memory` | the memory scopes it may read and write | anything else is refused |
| `limits` | time allowed and retries | a longer run is reported |
| `on_failure` | `stop`, `degrade` or `escalate` | applied when the agent cannot start or fails |

Every clause that names a check has a function behind it in `contracts.py` (29 checks). A contract that is not kept
is never silent: it becomes a `governance` finding and the recommendation is a referral to a person, even when the
agent that broke it is the one that aggregates the recommendation. Nothing that decides may use a model: the
contracts of resolution, graph, evidence, reference, policy, contradiction, verification and the what-if say `none`.

### Agent harness

`harness.py` is the one place an agent runs: the ten stage agents of an assessment and the on-demand ones (what-if,
correspondence, assistant, repository). Before the run it checks the needs and hands the agent a model it is allowed
to use and a memory handle that opens only the scopes of its contract. After the run it checks every promise and
that the agent changed only what it may, and records the run on the case (`runs[].contract`, `.budget`, `.throttle`,
`.memory`, `.io`) and in the ledger. It never decides a case and never repairs an agent's output.

### Orchestration, live

*Agent orchestration* in a case is one board, with the same eight columns in every lane, so a step reads straight down:

| Lane | What it shows | From |
| --- | --- | --- |
| Process layer | the eight steps of a case, the one working now, the ones waiting for a person, and a loop back when the case was assessed again | `progress`, `history[]` |
| Boss agent | the orchestrator's plan for each step and how far it got (`3/3 done`), who asked, where it holds for a person | `runs[].plan` |
| Harness → agents | each agent run under its contract: promises kept, model or code, time | `runs[].contract` |
| Knowledge graph | the graph nodes the harness handed each step (only the classes its contract names under `grounding`), by level, and what the case wrote back | `runs[].grounding`, `learned` |
| Shared memory | what each step read of what earlier steps left, and what it left; an arc from every writer to every reader; a dashed arc for what came from earlier cases | `runs[].sections`, `runs[].memory`, `assessment.memory` |

While an assessment runs the board follows it (*Live*). Afterwards *Replay* plays it back one agent at a time, the
slider moves to any point, and a click on any part opens its detail: the plan, every clause of the contract with the
result of its check, the nodes handed over, the reads and writes. A bundled sample finishes in milliseconds without a
model, so it is played back once when it opens. Nothing on the board is drawn from a script: every count is a field of
the run record, and the same record is in the ledger.

### Shared memory

| Scope | What it holds | Who writes it |
| --- | --- | --- |
| one run | the note each agent leaves for the ones after it (`assessment.memory.working`) | each agent, through the harness |
| one case | its documents, the reviewer's corrections and decisions | the case service |
| workspace, what is known | the knowledge graph (below) | the orchestrator, when an assessment ends or a person decides |
| workspace, what happened | one episode per assessed case: who was in it, which reference numbers it quoted, how it came out | the orchestrator |
| workspace, how to read | the vocabulary approved through governed feedback | a person's approval, after a regression run |

The entity resolution agent recalls the episodes that touch a new case. Parties met before are context for the
caseworker (`info`). A reference number another case already quotes is `info` too, unless the profile lists it under
`memory.duplicates`: then it is a `review` finding and the case goes to a person. That is a deterministic comparison,
not a model's judgement. A second copy of the same bundled sample is not reported as a duplicate.

### Knowledge graph

One graph per workspace, under `<data>/<tenant>/knowledge/`, written in the layout of a **KB Forge knowledge base**
(schema 1.0): `graph/entities.jsonl`, `graph/triples.jsonl`, `graph/index.json`, `graph/provenance.json`,
`graph/verification.json`, `ontology/ontology_merged.json`, `quality/metrics.json`, `manifest.json`. Identifiers are
`<class-slug>/<name-slug>`; classes are PascalCase under a KB Forge core class; relationships are camelCase with a
domain, a range and an inverse (`foundation/ontology.yaml`, in the format of a KB Forge custom ontology).

It has KB Forge's four levels. Every entity carries its level and how deep it sits when the graph is drilled into
(`graphLevel`), and every class of the ontology declares both. The level is stored exactly as KB Forge stores it:
`knowledgeLevel` is a list of KB Forge's level ids (`industry`, `domain`, `coforge`, `customer`), the first being the
level the entity is shown at, so KB Forge segregates this graph by level without any mapping. On screen and in the API
the third level is called Solution.

| Level | What is on it | Heads it |
| --- | --- | --- |
| **Industry** | the industry segments the use cases serve | `IndustrySegment` |
| **Domain** | the experience domain, its use cases, and what each asks for: kinds of document, roles, rules, reference sources and their entries | `ExperienceDomain` |
| **Solution** | the accelerator and its agents, each with its contract (KB Forge's third level, delivery experience) | `Accelerator` |
| **Customer** | the workspace (a `Company`), its cases, and what the cases hold: files, organisations, goods, reference numbers, findings. This is the level that grows | `Company` |

An imported knowledge base sits at the level it was built for, or the level chosen when it is added. A KB Forge
combined graph spans levels and records the level on every entity: each entity sits at its own (one known at several
levels sits at the first and says the others). Knowledge with no level at all is shown apart, as **added knowledge**.

The **Knowledge** screen opens on the **level map**, as KB Forge draws one: the four levels as boxes stacked top to
bottom, each with the entities at its head. A click on an entity opens what is below it, and drilling only goes down
(an industry opens its use cases, a use case its documents and rules, the workspace its cases, a case what it holds).
Inside a level each row is one kind of thing. *Network* shows the same graph as a force layout.
`GET /api/knowledge/map?open=industry,domain&drill=<entity id>` returns the scene.

The graph is never edited in place. It is rebuilt from its sources after every assessment, decision and import, so
nothing is lost and nothing is counted twice: the profiles, one contribution per assessed case
(`knowledge/sources/cases/`), and imported knowledge (`knowledge/sources/imports/`).

* **Evidence.** Every entity and link carries what supports it: a document citation (file, page and line, the quote),
  the case record, a profile declaration, a retrieved reference, an import, a person's decision, or an inference with
  its basis.
* **Verification.** Every build checks each document citation against the text it cites, with no model: `named`,
  `quoted`, `read`, `paraphrased`, `missing`, `unchecked`. From the checks each entity and link gets an origin
  (`document`, `system`, `settings`, `web`, `imported`, `inferred`, `decision`, `unverified`).
* **Quality.** The score follows KB Forge's formula (link density, stub freedom, connectedness, description coverage,
  ontology coverage, validity) with one component changed: where KB Forge asks a model how well the graph answers its
  competency questions, this graph reports the share of entities and links whose evidence was found (15%).
* **Out.** *Knowledge > Download for KB Forge* (or `python -m docuinsights knowledge export`) gives a zip of the
  knowledge base, with `neo4j/knowledge_graph.cypher` and `import/graph.json` beside it. In KB Forge: *Import a graph*.
* **In.** *Knowledge > Add a knowledge base* (or `knowledge import <path>`) takes a KB Forge knowledge-base zip or
  folder, a KB Forge graph page (.html) or a JSON file of nodes and edges. Its entities keep their ids and classes and
  are cited to the import; an organisation the cases already know is joined to it by name; classes and relationships
  the ontology lacks are added as extensions. Another name an imported knowledge base gives an organisation reaches
  the resolver, so a document that uses it is linked. An import can be taken out again; it is kept beside, not deleted.

**What has been checked against KB Forge, and what has not.** Out: the export was read by KB Forge 2.23's own import
code (its reader, its mapper and its graph build, run outside the app with the database stubbed): every entity kept
under the same id (444 of 444), `knowledgeLevel` kept as written, every class and relationship kept as it is, none of
this graph's links rejected or downgraded. Imported there as a domain, KB Forge adds a placement link of its own from
the domain to each of the 16 agents and keeps those as `relatedTo`: its `platformInDomain` is reserved for a
`Platform`. In: 43 real KB Forge sources were added to a trial workspace (22 knowledge-base folders, 2 zips, 19
combined-graph pages; 89,956 entity records and 254,883 links, which merge to 17,532 entities and 56,396 links): all
read, and every entity landed on one of the four levels (industry 5,995, domain 2,986, solution 8,395, customer 156),
731 of them known at more than one. 121 links (0.2%, all in combined-graph pages) do not fit the domain and range the
page's own ontology declares and are kept as `relatedTo` with their original name, as KB Forge does. With that much
knowledge the level map answers in 0.1 s and an assessment takes about 6 s, most of it the rebuild of the graph. Not
checked: an import through a running KB Forge (its job registration, its RDF, SHACL, GraphDB and Neo4j exports,
Explore and Ask on the result). The RDF, SHACL and GraphDB exports KB Forge writes are not written here.

Two naming rules follow from how KB Forge joins entities, and are kept for that reason: something that belongs to one
case alone is named `<name> — <case reference>` (KB Forge treats a bracketed qualifier as the same name), and the
class of a check's conclusion is `CaseFinding` (`Finding` means a research finding in other knowledge bases).

### Evidence provenance

Two layers. Inside a case, every finding carries its sources (document, version, page, line, the line as printed),
its rule and version, its reference citation and the verifier's coverage, as before. Across the workspace,
`<data>/<tenant>/ledger.jsonl` is an append-only ledger: one line per agent run (contract kept or not, fingerprints
of what it read and wrote), human review, decision, knowledge rebuild, import and governance decision. Each line holds
the hash of the line before it, so an edited, removed or inserted line breaks the chain from that point and
`GET /api/ledger` says where. It is evidence of what the system did. It is not a blockchain.

### Throttling

| Limit | Default | Setting |
| --- | --- | --- |
| model calls a minute, all agents | 60 | `DOCUINSIGHTS_MODEL_RPM` |
| model tokens a minute | off | `DOCUINSIGHTS_MODEL_TPM` |
| model calls in flight | 4 | `DOCUINSIGHTS_MODEL_CONCURRENCY` |
| how long a call waits for a slot | 20 s | `DOCUINSIGHTS_MODEL_MAX_WAIT_S` |
| model calls and tokens per agent per run | in each contract | `foundation/contracts.yaml` |
| API requests a minute per caller (standalone) | 600 | `DOCUINSIGHTS_API_RPM` |
| assessments running at once | 2 | `DOCUINSIGHTS_MAX_ASSESSMENTS` |

At a limit a model call waits. Past the wait it is not made: the agent falls back to the profile's patterns, the run
is marked degraded and says how many calls were not made. Nothing fails because the model is busy. On the CX Nova
layer the model limiter and the budgets apply; the API gate does not (the layer applies its own).

## Run it alone

```bash
pip install -e .            # in this repository; or build the standalone folder (below) and install that
python -m docuinsights samples
python -m docuinsights assess --profile supplier_invoice --sample mismatch
python -m docuinsights check                      # which model is configured, and whether it answers
python -m docuinsights knowledge show             # the workspace's knowledge base (also: import <path>, export <file.zip>)
python -m docuinsights serve --port 8090          # http://127.0.0.1:8090/
```

Settings are read from the environment or from a `.env` file in the folder it is started from. The server calls the
model once at start and prints `ONLINE`, or the reason it is not answering (it still serves, on patterns).

| Setting | Meaning |
| --- | --- |
| `DOCUINSIGHTS_DATA_DIR` | where cases, files and the feedback vocabulary are kept (default `./docuinsights-data`) |
| `DOCUINSIGHTS_MODEL_PROVIDER` | `offline` (default), `anthropic`, `anthropic_foundry` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_BASE_URL` | the model's credentials |
| `FOUNDRY_DEPLOYMENT_FAST`, `_BALANCED`, `_PRO`, `_COMPLEX` | the deployment behind each tier on Foundry, the same names the layer reads (defaults `claude-sonnet-5-5`, `claude-sonnet-5-5`, `claude-opus-5`, `claude-opus-5`). DocuInsights asks for `fast` to classify and `balanced` for everything else |
| `DOCUINSIGHTS_MODEL` | one model or deployment for every tier (`DOCUINSIGHTS_MODEL_FAST` ... override one tier) |
| `DOCUINSIGHTS_API_KEY` | required on every `/api` call when set; without it the API answers 127.0.0.1 only |
| `DOCUINSIGHTS_ROOT_PATH` | the prefix when it sits behind a reverse proxy (`/docuinsights`) |
| `DOCUINSIGHTS_REFERENCE_LIVE` | `1` reads reference sources live; otherwise the bundled snapshot is used and labelled |
| `DOCUINSIGHTS_REPOSITORY` | `local` (default) or `omnidocs` |
| `DOCUINSIGHTS_MODEL_RPM`, `_TPM`, `_CONCURRENCY`, `_MAX_WAIT_S`, `DOCUINSIGHTS_API_RPM`, `DOCUINSIGHTS_MAX_ASSESSMENTS` | throttling (see above); 0 switches a limit off |
| `DOCUINSIGHTS_KNOWLEDGE_NAME` | the name the knowledge base carries when it is exported |
| `DOCUINSIGHTS_WORKSPACE_NAME` | the name of the customer level in the knowledge graph (`This workspace`) |

To ship it as its own repository: `python scripts/export_docuinsights.py dist/docuinsights` writes a self-contained
project (the package, a `pyproject.toml`, a README, start scripts and the server kit below). The engine needs PyYAML
and certifi; `pdfplumber` or `pypdf` to read PDFs; `starlette` and `uvicorn` to serve.

**On a server.** The export carries `DEPLOY.md` and `deploy/windows/` (kept here in `deploy/docuinsights/`):
`install.ps1` (Python, `.venv`, a generated API key, the prefix and port, and the model settings of the layer on the
same machine), `service.ps1` (a Windows service on 127.0.0.1, behind the machine's web server) and `update.ps1`. The
result is the workbench at `https://<server>/docuinsights/` behind the key. `/health` is public and says only that the
server is up. With no key the API answers callers on the server itself, and a request that came through a reverse
proxy is never treated as local, so adding the proxy rule before the key does not open it.

## On the CX Nova layer

* The pack loads with the others (`CAF_PACKS_DISABLED=docuinsights` switches it off). `auto_route` is false: a case
  assessment runs when a caller or a flow names it.
* Flows: `di_case_assessment` (ten stages), `di_what_if`, `di_ask`, `di_assess_and_file`. Give `sample`
  (`supplier_invoice/mismatch`, `insurance_claim/out_of_cover`, `customs_claim/review`, ...) or `case_ref` (a case
  uploaded in the workbench). An agent run with neither works on `supplier_invoice/mismatch` and says so.
* The same harness, contracts, memory, ledger and knowledge base apply: each stage agent of a flow runs under its
  contract, and the verify step writes what the case taught the workspace. `di_graph` has a second action,
  `knowledge`, that looks a name up in the workspace's knowledge base (it needs no case).
  `di_intake` also takes a package: `reference`, `profile`, `fields` and `documents: [{name, category, content_base64}]`.
* The workbench is at `/docuinsights/` (behind the proxy: `/agentshop/docuinsights/`; on the CX Nova VM see
  `docs/DEPLOY_VM.md`, "DocuInsights on the VM"). It signs in with the portal's token or a customer key. An assessment started there runs as `di_case_assessment`, so it appears in the portal with
  its steps, model routes and cost. A customer needs the pack's agents in its subscription.
* Cases live under `<data>/docuinsights/<tenant>/`: `operator`, or `c-<customer id>`. One tenant cannot open
  another's case. The knowledge base, the episodes and the ledger are per tenant too: what one customer's cases
  teach is never visible to another.
* Every agent is also an MCP tool (`run_di_verifier`, `run_flow_di_case_assessment` ...) and an A2A skill, like any
  other agent of the layer.

## With NewgenONE

Three seams, in the order they are usually needed:

1. **Nothing connected.** Run a profile with its samples; the repository is the stand-in folder store.
2. **OmniDocs as the repository.** `DOCUINSIGHTS_REPOSITORY=omnidocs` with `OMNIDOCS_URL`, `OMNIDOCS_CABINET`,
   `OMNIDOCS_USER`, `OMNIDOCS_PASSWORD`, `OMNIDOCS_FOLDER_INDEX`, `OMNIDOCS_VOLUME_ID`, and optionally a data class
   (`OMNIDOCS_DATACLASS_INDEX`, `OMNIDOCS_DATACLASS_NAME`, `OMNIDOCS_FIELD_MAP`). Filing a case adds each document
   through `addDocumentJSON` with the case reference, document type, classification confidence, recommendation and
   assessment id as data-class fields.
3. **A NewgenONE process calls DocuInsights as a step.** `POST /api/v1/cases` with `{reference, profile, fields,
   documents: [{name, category, content_base64}], wait: true}` returns the assessment: outcome, reasons, what to
   request, each document's type and fields, every finding. `wait: false` answers 202; read
   `GET /api/v1/cases/{reference}`. On the layer the same work is `POST /flows/di_case_assessment/run`, or the MCP
   and A2A surfaces.

**Not yet verified against a live system.** The OmniDocs connector is written from the *NewgenONE OmniDocs 11.3 REST
Web Services Developer Guide* and has not been run against a cabinet: expect to adjust the request envelope in
`OmniDocsRepository._bdo` / `.add_document` on first contact. Folder creation and search are not used (documents go to
one configured folder). Whether a NewgenONE agent can call an external agent over MCP is for Newgen to confirm; the
REST call above does not depend on it.

## Reference sources

A reference (for the customs profile, a tariff heading) is retrieved as a recorded step: the address, the date it was
asked for, when it was retrieved, a hash of the content and its version are kept on every finding that used it.

* `DOCUINSIGHTS_REFERENCE_LIVE=1` reads the tariff's published API for the case's date. The parser was written without
  access to the service: check one live retrieval before relying on it. A failed live call falls back to the snapshot
  and says so.
* Otherwise the bundled snapshot is used: `src/docuinsights/reference/tariff_8482.json`, transcribed by hand from the
  heading page as shown for 2 October 2026, holding 11 of the heading's lines. Every screen labels it a snapshot, and
  the recommendation carries the caveat. Replace it before using a result.
* The classification aids in the profile (`reference_sources[].aids`) say how a product characteristic bears on each
  line. They are an aid written from the line descriptions; the tariff stays the authority. Where a needed
  characteristic is not stated, no classification is returned: the lines still possible are listed and targeted product
  evidence is requested.

## Sample data

Every company, reference, account and amount in `src/docuinsights/samples/` is invented.
`python scripts/build_docuinsights_samples.py` regenerates the documents (needs `reportlab`; `pdftoppm` for the one
scanned sample, which carries its transcription beside it so the demo runs without a model or an OCR engine).

## What is not built yet

* Reviewer decisions are recorded in the case's own audit trail and the ledger, not as the layer's held approvals.
* The knowledge base is files in the KB Forge layout with a Neo4j script; there is no graph database behind it, and
  it is rebuilt in full after each case (fine for thousands of entities, not for millions).
* A time limit in a contract is reported when it is passed; a running agent is not interrupted.
* Memory recalls by exact name key and exact reference number; there is no semantic (vector) recall.
* The ledger is one file per workspace on the same disk as the cases: it shows tampering, it does not prevent it.
* No malware scan at intake: the checks are type, size and signature.
* A scanned PDF with no text layer is not read yet. A scanned image (PNG, JPEG) is read by the model, or by Tesseract when it is installed.
* Source anchors are page and line, not coordinates on the page image.
* Tokens and cost appear on the layer's run records; the standalone monitor shows tokens per run, not money.
