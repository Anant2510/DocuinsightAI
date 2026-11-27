# DocuInsights

Give it the documents. Get back a recommendation you can check.

A case is a handful of documents and a few facts about it. Agents read the documents, lift their facts with the page
and line each came from, and link the same company or reference number across them. Rules that are code, never a
model's opinion, check that nothing is missing, that the dates and amounts hold and that the documents agree. A person
gets one of three recommendations, and every reason opens the line it rests on.

Every case is also checked three ways that do not depend on the use case: **integrity** (does each document hold
together on its own: its sums, its dates, the check digits of its account numbers, the same file twice, bank details
that changed since last time), **screening** (is any party, vessel or port on a watchlist) and **privacy** (what
personal data the package carries, masked in whatever leaves the system). It then lands in a **work queue** with a
priority and a due date, and leaves as a **decision record** that can be printed.

It names no customer and no industry. A use case is one configuration file (`src/docuinsights/profiles/*.yaml`): the
kinds of document, the evidence it asks for, its rules. Five ship, each with invented sample cases:

| Use case | Who runs it | What it checks |
| --- | --- | --- |
| `supplier_invoice` | Finance operations | an invoice against its purchase order and proof of receipt, and whether it was seen before |
| `insurance_claim` | Insurance | a claim against its policy and the policy record: in force, premium paid, cover dates, notification by region, the amount, the names |
| `loan_application` | Banking and lending | what an applicant declared against the payslip, the statement and the employer's letter |
| `customs_claim` | Customs and trade | evidence, consistency, and a commodity code read from the tariff for the case's date |
| `trade_finance` | Trade finance | documents presented under a documentary credit against the credit's terms |

## What every agent runs on

| | What it is | Where |
| --- | --- | --- |
| Agent contracts | what each agent needs, promises, may change, may spend and must never do | `foundation/contracts.yaml`, `contracts.py` |
| Agent harness | the one place every agent runs; it enforces the contract and records the run | `harness.py` |
| Shared memory | the run's notes, the case, and what the workspace has learned from earlier cases | `memory.py` |
| Knowledge graph | one graph per workspace in the KB Forge knowledge-base layout: what each industry works under, what each use case asks for, what every case taught. Every finding opens the exact node its rule rests on | `kb.py`, `foundation/ontology.yaml`, `foundation/knowledge/*.yaml` |
| Evidence provenance | every conclusion to a line of a document; every action in a chained ledger | `ledger.py` |
| Throttling | rate limits and per-agent budgets on model calls; a gate on the API | `throttle.py` |

Each is described in [DOCUINSIGHTS.md](DOCUINSIGHTS.md), with what has not been verified against a live system.

## Run it

```bash
./start.sh                       # macOS, Linux: makes .venv on the first run, then serves http://127.0.0.1:8090/
.\start.ps1                      # Windows
```

or by hand:

```bash
python3 -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[server,pdf]"
python -m docuinsights samples
python -m docuinsights assess --profile supplier_invoice --sample mismatch
python -m docuinsights serve --port 8090
```

Open the workbench and pick a use case on the home page: **Try it** on a sample runs it end to end. The top of the page
has nine screens: Home, Cases (the work queue: priority, queue, due date, who has it), Insights (how many cases go
straight through, how many need a person and why, how long a decision takes; counted from the case files), Knowledge
(everything known, explored as in KB Forge: four levels, industry, domain, solution, customer), Agents (their
contracts) and Governance (contracts, memory, provenance, throttling, watchlists as they stand). Three more are where
an installation makes the product its own: **Observability** (what the agents did and what it cost), **Rules** (read,
change, add, switch off and test the rules of a use case, or download the rules sheet, fill it in and import it; every
change is a version in the audit trail) and **Connectors** (where cases come in, the systems of record they are
checked against, and where the answer goes).
Inside a case: summary, documents, evidence, consistency, **screening, integrity and privacy**, rules, the graph,
provenance, the what-if simulator, the decision with its printable record, and **Agent orchestration**: one board
that shows the boss agent's plan, each agent run under its contract, and what every step took from the knowledge
graph and the shared memory. It follows a running assessment and plays a finished one back.

Documents can be PDF, Word, Excel, an email with its attachments, a web page, text, CSV or a scan.

## The knowledge base and KB Forge

One knowledge graph per workspace, kept in the KB Forge knowledge-base layout (`data/default/knowledge/`). It starts
with six curated knowledge bases (`src/docuinsights/foundation/knowledge/*.yaml`): five industries (finance
operations, insurance, banking and lending, customs and trade, trade finance) with their standards and articles,
processes, risks, controls, measures and terms, and the domain itself. Every rule of every use case is linked to the
article, control or term it rests on, and every assessed case adds to the graph.

* **Explore it as in KB Forge.** *Knowledge > Explore the graph* draws the graph the way KB Forge's Explore screen
  draws its level map: the levels as boxes on a spine, entities as circles in their level's colour with +N for what
  is still to open, a double-click to drill down into a tidy tree, Force / Layered / Radial layouts, the level bar,
  the trail, Scene & filters on the left and the inspector on the right.
* **Follow a finding to its reason.** A finding card names what its rule rests on; a click opens that exact node in
  the explorer, with the way down to it drawn, what it says, how it is cited and every case it was used on. Each node
  has a link of its own (`#/knowledge/<id>`) to send to someone.
* **Manage it.** *Knowledge > Manage* switches a curated knowledge base off and on, moves an added one to another
  level, and lists what was added by hand. To add a fact, open the node it belongs under and choose *Add under this*.
* **Add your own.** Put YAML files like the shipped ones in a folder and name it in `DOCUINSIGHTS_KNOWLEDGE_DIR`.

What the curated knowledge bases say is a short summary with its reference, written for this accelerator. It is not
the text of a standard: read the current text before relying on it.

To open the graph in KB Forge: **Knowledge > Download for KB Forge**, then in KB Forge
*Import a graph*. To bring knowledge the other way: **Knowledge > Add a knowledge base** takes a KB Forge
knowledge-base zip, a KB Forge graph page (.html) or a JSON file of nodes and edges. From the command line:

```bash
python -m docuinsights knowledge show
python -m docuinsights knowledge import ~/KBGraph/knowledge_bases/<a knowledge base folder>
python -m docuinsights knowledge export knowledge.zip
```

## Settings

Copy `.env.example` to `.env`. Without a model it runs on the profile's patterns and rules and says so on every
screen. To read with Claude set `DOCUINSIGHTS_MODEL_PROVIDER` to `anthropic` (with `ANTHROPIC_API_KEY`) or
`anthropic_foundry` (with `ANTHROPIC_FOUNDRY_API_KEY` and `ANTHROPIC_FOUNDRY_BASE_URL`). The model tiers use the same
names as the CX Nova layer (`FOUNDRY_DEPLOYMENT_FAST`, `_BALANCED` ...), so one set of lines serves both. The server
calls the model once at start and prints `ONLINE` or the reason it is not; `python -m docuinsights check` does the
same on its own. Set `DOCUINSIGHTS_API_KEY` before exposing the server beyond the machine it runs on; without a key
the API answers 127.0.0.1 only.

Behind a reverse proxy under a prefix: `./start.sh --root-path /docuinsights` and forward `/docuinsights/` to the port.

**Watchlists.** Out of the box screening runs against an invented demonstration list, and says so. Name your own
lists in `DOCUINSIGHTS_WATCHLISTS` (JSON or CSV files, or folders of them) and the invented one is no longer used.

**Telling another system.** Set `DOCUINSIGHTS_WEBHOOK_URL` and a small signed message is sent when a case is assessed
or decided (`DOCUINSIGHTS_WEBHOOK_SECRET` signs it). Personal data in it is masked.

**Your rules.** The limits that ship are sample values. On the **Rules** screen, change them, add your own, or
download the rules sheet for your claims or operations team to fill in and import it back. Set
`DOCUINSIGHTS_ADMIN_KEY` to keep those changes for whoever governs the workspace.

**Your systems of record.** The insurance use case checks each claim against a policy administration system. A
synthetic one (invented policies, United States and India) answers until you name your own with
`DOCUINSIGHTS_SYSTEM_POLICY_ADMIN_URL` and its neighbours, or an adapter. The **Connectors** screen shows what is
connected and tests a lookup.

## On a server

[DEPLOY.md](DEPLOY.md) puts it on a Windows server as a service behind the machine's web server, reached from
anywhere at `https://<your server>/docuinsights/` with an API key: push this folder to GitHub, clone it on the server,
`deploy/windows/install.ps1`, `deploy/windows/service.ps1`, one web server rule. `deploy/windows/update.ps1` brings a
running installation up to date.

## Use it from another system

`POST /api/v1/cases` with `{reference, profile, fields, documents: [{name, category, content_base64}], wait: true}`
returns the assessment as JSON: outcome, reasons, findings, triage, watchlist matches, personal data by kind, the
version of the rules it was made on and what each system of record answered. `POST /api/v1/cases/{reference}/decision`
writes back a decision a person made in your own system.
`GET /api/v1/cases/{reference}/record` is the decision record (`?mask=1` masks personal data), `GET /api/v1/insights`
the workspace's numbers, `GET /api/export/cases.csv` the work queue. `DOCUINSIGHTS_REPOSITORY=omnidocs` files assessed cases to NewgenONE OmniDocs.
Both, and what has not been verified against a live system, are described in [DOCUINSIGHTS.md](DOCUINSIGHTS.md).

## Tests

```bash
pip install -e ".[dev,server,pdf]"
python -m pytest
```

`tests/test_docuinsights_engine.py` proves the engine on the bundled cases. `tests/test_docuinsights_scenarios.py`
puts it through what an installation meets in practice (documents missing, blank, corrupt, filed twice or mislabelled;
other countries' number and date formats; other alphabets; hostile text; many cases at once; an API called wrongly)
and checks the same invariants after each. [DOCUINSIGHTS.md](DOCUINSIGHTS.md) lists the scenarios and what is not
covered.

## One package, two homes

`src/docuinsights` is the same package the CX Nova Agent Orchestration Layer carries as its DocuInsights agent pack.
This folder is written by the layer repository's `scripts/export_docuinsights.py`. Change the accelerator in one of
the two and carry `src/docuinsights` (and the two `tests/test_docuinsights_*.py` files) across, so the copies do not drift.
