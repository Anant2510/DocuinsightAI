# DocuInsights

Give it the documents. Get back a recommendation you can check.

A case is a handful of documents and a few facts about it. Agents read the documents, lift their facts with the page
and line each came from, and link the same company or reference number across them. Rules that are code, never a
model's opinion, check that nothing is missing, that the dates and amounts hold and that the documents agree. A person
gets one of three recommendations, and every reason opens the line it rests on.

It names no customer and no industry. A use case is one configuration file (`src/docuinsights/profiles/*.yaml`): the
kinds of document, the evidence it asks for, its rules. Five ship, each with invented sample cases:

| Use case | Who runs it | What it checks |
| --- | --- | --- |
| `supplier_invoice` | Finance operations | an invoice against its purchase order and proof of receipt, and whether it was seen before |
| `insurance_claim` | Insurance | a claim against its policy: cover dates, notification, the amount, the names |
| `loan_application` | Banking and lending | what an applicant declared against the payslip, the statement and the employer's letter |
| `customs_claim` | Customs and trade | evidence, consistency, and a commodity code read from the tariff for the case's date |
| `trade_finance` | Trade finance | documents presented under a documentary credit against the credit's terms |

## What every agent runs on

| | What it is | Where |
| --- | --- | --- |
| Agent contracts | what each agent needs, promises, may change, may spend and must never do | `foundation/contracts.yaml`, `contracts.py` |
| Agent harness | the one place every agent runs; it enforces the contract and records the run | `harness.py` |
| Shared memory | the run's notes, the case, and what the workspace has learned from earlier cases | `memory.py` |
| Knowledge graph | one graph per workspace in the KB Forge knowledge-base layout; it grows with every case | `kb.py`, `foundation/ontology.yaml` |
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
has five screens: Home, Cases, Knowledge (everything learned, as a map of four levels: industry, domain, solution,
customer), Agents (their contracts) and How it is governed (contracts, memory, provenance, throttling as they stand).
Inside a case: summary, documents, evidence, consistency, rules, the graph, provenance, the what-if simulator, the
decision, and **Agent orchestration**: one board that shows the boss agent's plan, each agent run under its contract,
and what every step took from the knowledge graph and the shared memory. It follows a running assessment and plays a
finished one back.

## The knowledge base and KB Forge

Every assessed case adds to one knowledge graph per workspace, kept in the KB Forge knowledge-base layout
(`data/default/knowledge/`). To open it in KB Forge: **Knowledge > Download for KB Forge**, then in KB Forge
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

## On a server

[DEPLOY.md](DEPLOY.md) puts it on a Windows server as a service behind the machine's web server, reached from
anywhere at `https://<your server>/docuinsights/` with an API key: push this folder to GitHub, clone it on the server,
`deploy/windows/install.ps1`, `deploy/windows/service.ps1`, one web server rule. `deploy/windows/update.ps1` brings a
running installation up to date.

## Use it from another system

`POST /api/v1/cases` with `{reference, profile, fields, documents: [{name, category, content_base64}], wait: true}`
returns the assessment as JSON. `DOCUINSIGHTS_REPOSITORY=omnidocs` files assessed cases to NewgenONE OmniDocs.
Both, and what has not been verified against a live system, are described in [DOCUINSIGHTS.md](DOCUINSIGHTS.md).

## Tests

```bash
pip install -e ".[dev,server,pdf]"
python -m pytest
```

## One package, two homes

`src/docuinsights` is the same package the CX Nova Agent Orchestration Layer carries as its DocuInsights agent pack.
This folder is written by the layer repository's `scripts/export_docuinsights.py`. Change the accelerator in one of
the two and carry `src/docuinsights` (and `tests/test_docuinsights_engine.py`) across, so the copies do not drift.
