# ViraData Intelligence Dashboard — local implementation handoff

**Date:** 2026-10-18  
**Status:** Implementation brief; the full AI Copilot architecture package remains the design authority.  
**Target directory on Arash's home PC:** `D:\ViraData\11_Products\03_Reusable_Demos\Intelligence Dashboard - Demo`

## Verified local baseline

- A new project foundation has been created with React/TypeScript frontend, FastAPI backend, PostgreSQL 16 and Docker Compose.
- On the home PC, `docker compose ps` showed `web`, `api` and `db` running and healthy. The web page at `http://127.0.0.1:8080` and API health at `http://127.0.0.1:8000/health` were opened successfully by the owner.
- The previous Codex process had `spawn EPERM` for development mode, but `npm run build` succeeded. This has not been diagnosed as an application defect.
- The foundation is not the functional demo: login, dataset, semantic metrics, LLM integration and interactive reporting are future work.

## Product outcome

A customer receives an individual account, opens the demo on a phone, asks freely phrased Persian questions about the available synthetic business dataset and gets a responsive report with reviewed KPIs, charts, evidence-backed insights and drill-down to contributing rows. The assistant responds briefly to greetings; for general chat, web research, unrelated opinions or unsupported data requests, it clearly describes its scope or missing data. It does not invent a number, cause or source.

Build and test locally first. After customer scenarios and security checks pass, deploy the same application to a VPS at a demo subdomain with HTTPS. The VPS and AI provider have not been selected or purchased.

## Governing design already agreed

- The broader architecture is a modular monolith with a single stateful orchestrator, governed tools and evidence-first responses. Frontend: React/TypeScript; backend: FastAPI; separate synthetic PostgreSQL database. It is read-only decision support.
- Natural-language phrasing is open within the supported data domain. The model selects intent, approved measures, dimensions, periods and a report layout. The server validates those choices and runs approved semantic queries. Model-generated arbitrary SQL or executable UI code is outside the initial release.
- Financial figures come from deterministic computations and approved metric definitions. Carry exact decimal values and unit metadata; do not silently treat null as zero. Each numerical claim must point to the calculation and rows that support it.
- Rendering uses a reviewed registry of chart and KPI components. The model produces a validated visualization specification, not React code. For the first scenario, include KPI cards, line trend, bar comparison and a pie/donut only when composition is appropriate. Consider a profit-change waterfall/bridge for the finance scenario. Curate animations and source licenses, and check mobile touch, RTL, reduced motion and drill-down.
- Individual login, server-side authorization, account expiry or disablement, per-account usage limits and cost tracking are required before external access. No real customer data is used.
- The full architecture package has CT-01 through CT-10, an acceptance matrix and ADR decisions. Its status was `REVIEWED / SIGN-OFF PENDING` as of 2026-10-12. Do not claim that all ADRs or security decisions were formally approved. Record deviations and unresolved decisions explicitly.

## First shared synthetic finance scenario

The existing demo design uses one fictional company and one coherent dataset across assistant and dashboard. An executive asks: «برای مدیرعامل گزارشی از درآمد، هزینه و سود دو فصل اخیر بساز؛ تغییرات مهم را نشان بده.» The dashboard shows revenue, cost of goods sold, operating expense, operating profit, margin, monthly trend, a reconciled profit bridge, major expense changes and drill-down to underlying categories, cost centers and records.

Reference quarter A, in **billion tomans**: revenue 120, cost of goods sold 84, operating expense 18, operating profit 18. Quarter B: revenue 135, cost of goods sold 101, operating expense 24, operating profit 10. Therefore profit change is **+15 − 17 − 6 = −8**; operating margin goes from **15%** to approximately **7.407%**. These are design totals to be reproduced by synthetic line records, not independent hard-coded KPI answers.

Definitions: operating profit = revenue − cost of goods sold − operating expenses; operating margin = operating profit / revenue when revenue is nonzero. Define approved document status, returns and corrections, time zone, calendar, currency and allocation policy before calculating transactional totals. If the user asks why profit fell, distinguish the arithmetic contribution of revenue and costs from a causal explanation. A follow-up scenario may ask: «اگر هزینه حمل دو میلیارد کمتر بود، سود چه می‌شد؟» Display the modeled 12 billion separately from the observed 10 billion, with the assumption visible.

## Next bounded engineering sequence

1. Import the complete architecture source under `docs/reference/ai-copilot/`, preserving its directory structure, or explicitly record that only this brief is available. Read `README`, architecture, contract catalog, common types, semantic SQL, evidence response, security, acceptance, ADR and open-decisions files before implementing contracts. Do not fabricate missing contract fields.
2. Design the synthetic business grain and metric dictionary. Make a deterministic seed and independent golden checks so detail rows reconcile to monthly and quarterly totals, including the profit bridge. Keep business data separate from application accounts and runtime state.
3. Implement governed semantic query contracts and a validated report specification; add negative tests for unsupported measures, unauthorized data, null/zero and off-topic requests.
4. Integrate a replaceable LLM adapter that outputs structured intent/report choices; calculate and validate values server-side. Choose provider and spending cap from measured local tests.
5. Build the RTL responsive chart registry, account login, drill-down and feedback capture. Test representative mobile widths and actual touch behavior.
6. Rehearse the customer journey repeatedly, measure latency and cost, then size and buy hosting.

## Immediate Codex task

Keep the existing project and its passing container foundation. Start with a read-only inventory of files and the full architecture package available on the machine. If the full package is absent, use this brief for a **reviewable synthetic data and metric design proposal only**. Do not invent the detailed CT-01..CT-10 schemas. Report exact proposed tables, row grain, formulas, return/correction treatment, reconciliation equations, golden test cases, unresolved owner decisions and affected files. Do not implement the LLM or UI during that design task.

## Source references retained from earlier work

- `ViraData AI Copilot — Architecture v1.0`, `README.md`, dated 2026-10-12.
- `docs/architecture/00-reference-architecture.md` and `07-review-signoff.md`.
- `docs/contracts/00-catalog.md`; `docs/handoff/01-codex-task-specifications.md`; `docs/acceptance/01-acceptance-matrix.csv`.
- `ViraData_Demo_Selection_Finance_Profit_Cost.md`.
- `ViraData-Website-Content-v1.md`, demo content and truthful preview/live labels.

This brief reflects those reviewed extracts and the owner’s 2026-10-18 direction. It is not a substitute for the full contract package or a claim of production readiness.
