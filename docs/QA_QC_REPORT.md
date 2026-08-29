# AML Operations Console — QA/QC Report

Hands-on audit of the FIN-07 AML Console (running stack, not code-only). Every
judgment below is backed by a run against the live application: API calls with
real role tokens, and a headless browser driving the built frontend. Fixes that
were applied are marked **FIXED** and re-verified.

## 1. Executive Summary

| | |
|---|---|
| Roles exercised | 5 (analyst, compliance_officer, mlro, auditor, admin) — one real demo account each |
| Route × role probes | 22 GET routes × 5 roles + 7 write routes × 5 roles (API), 12 direct-URL loads (browser) |
| Dashboards rendered & inspected | 5/5 (one per role) |
| AI investigations exercised | 1 seeded + 1 **live** (3 Gemini agents, verified grounding) |
| Automated tests after fixes | **API: 75 passed, 9 skipped**; RBAC unit: 52 passed; web `tsc` + `vite build` clean |

Defect counts (found this audit): **P0: 0 · P1: 1 · P2: 3 · P3: 1 · P4: 4.**
The P1 and all three P2s were fixed and re-verified. Net: no known unauthorized
data path remains open; the product is in good shape for a supervised demo.

**Headline findings**
- **Backend authorization is genuinely strong** — default-closed policy, every
  write correctly gated, auditor blocked from all mutations, only MLRO passes the
  approval gate, only admin passes user/settings, model inference denied to
  auditor/admin. Verified empirically, not from code.
- **One real broken-access-control (P1, IDOR)** — case *detail* and *network*
  ignored the analyst data-scope that the case *list* enforced. **Fixed.**
- **RBAC is spread across three parallel tables that had drifted** — this
  produced an auditor whose own menu led to 403 dead-ends. **Reconciled + fixed.**
- **AI agent grounding is excellent** — live output, evidence-linked claims, zero
  hallucinated references, correct AML hedging, geography treated as a statistical
  corridor rather than a FATF label.

## 2. Environment

| | |
|---|---|
| Frontend | React 18 + TypeScript (strict) + Vite, served as a built bundle by `fin07-web` (`:5173`) |
| Backend | FastAPI + SQLAlchemy + psycopg (`fin07-api` `:8000`), async worker (`fin07-worker`) |
| Database | PostgreSQL 16 — **`fin07_hi_medium`** (not `fin07`); Redis 7 queue |
| AI agent | Google Gemini (`gemini-3.1-flash-lite`), key present in the **worker** container; investigations run async via `fin07:jobs` |
| Browser | gstack headless browser, viewport 1440×900 |
| Auth | email + PBKDF2 (200k) → opaque session token in `sessionStorage`; 5 demo accounts, password `demo-password` |
| Test date | 2026-08-20 |
| Commit base | `develop` @ `b274b34` (working tree had the branch's uncommitted changes) |

Startup: all app containers healthy; no fatal errors. One benign runtime warning
(cytoscape wheel sensitivity) on the graph page.

### Route × Role matrix (verified live, after fixes)

`200` = allowed through the gate (endpoint may still 404 on a fake id); `403` = denied.

| Route (GET) | analyst | compliance | mlro | auditor | admin |
|---|---|---|---|---|---|
| `/alerts`, `/alerts/page` | 200 | 200 | 200 | **200*** | 403 |
| `/cases` | 200 | 200 | 200 | **200*** | 403 |
| `/transactions` | 200 | 200 | 200 | 200 | 403 |
| `/fc/graph` (network) | 200 | 200 | 200 | **200*** | 403 |
| `/fc/crypto`, `/fc/projects` | 200 | 200 | 200 | 403 | 403 |
| `/fc/agent-runs` (agents) | 200 | 200 | 200 | 200 | 403 |
| `/fc/benchmarks`,`/fc/data-quality`,`/fc/model-*` | 403 | 200 | 200 | 200 | 200 |
| `/sars` | 403 | 200 | 200 | 403 | 403 |
| `/audit` | 403 | 200 | 200 | 200 | 200 |
| `/users`, `/settings` | 403 | 403 | 403 | 403 | 200 |
| `/dashboard`,`/world`,`/queue`,`/status`,`/nav-counts` | 200 | 200 | 200 | 200 | 200 |

`*` auditor is **read-only** (all writes below still 403). `*` marks the routes
corrected this audit (were 403 before → menu led to a dead-end).

| Write (negative) | analyst | compliance | mlro | auditor | admin |
|---|---|---|---|---|---|
| `POST /alerts/{id}/investigate` | pass-gate | pass-gate | pass-gate | **403** | 403 |
| `POST /cases/{id}/investigate` | pass-gate | pass-gate | pass-gate | **403** | 403 |
| `POST /approvals/{id}/decision` | 403 | 403 | **pass-gate** | 403 | 403 |
| `PATCH /users/{id}` | 403 | 403 | 403 | 403 | **pass-gate** |
| `PUT /settings/{code}` | 403 | 403 | 403 | 403 | **pass-gate** |
| `POST /aml/bitcoin/predict` | pass-gate | pass-gate | pass-gate | **403** | 403 |

"pass-gate" = authorization allowed it through (then 422/404 on the empty test
body). This is the intended matrix: MLRO-only approval, admin-only user/settings,
auditor read-only everywhere, admin has no AML decision or inference authority.

## 3. Role Coverage

**MLRO** — Command-centre dashboard: enterprise risk posture (CRITICAL 90/100),
critical alerts (7,505 ≥80 unclosed), cases under investigation (737), SAR pending
(0, honest), typology distribution over the live open queue. Has Approvals nav;
is the only role that passes the approval-decision gate. No admin controls. **Pass.**

**Compliance Officer** — Work-queue dashboard: open alerts (10,004), high-risk
(7,505), cases in progress (737), SAR drafting (0). Prioritised "my work queue"
listing real alerts with typology + score. Can prepare SAR, cannot decide it
(gate 403). Correctly blocked from `/users` and `/settings`. **Pass.**

**Analyst** — Investigation-space dashboard: alerts queue, running sessions (0),
agent runs (200). Deepest investigation UX (graph + model explanation). Data-scope
= assigned; sees only their 6 assigned cases (after demo seed), 404 on others.
**Pass** (after AML-QA-003/004 fixes).

**Auditor** — Read-only audit/governance dashboard: real `audit_log` events,
model-branch counts, honest "no dedicated access-review endpoint yet" disclosures.
Now reaches Alerts/Cases/Network read-only (50 alert rows, **zero write buttons**),
blocked from Crypto, blocked from every mutation. **Pass** (after AML-QA-001 fix).

**Admin** — Platform dashboard: active/locked user counts, DB/Redis health, full
user table with roles + last-login. No access to any AML operational data (alerts,
cases, graph, crypto all 403) and no AML decision authority. **Pass.**

## 4. RBAC Results

**Backend (source of truth): strong.** `authz.POLICY` is default-closed
(`test_moi_route_deu_co_chinh_sach` proves every `/api/v1` route is declared).
The write-negative matrix above is exactly correct. Auditor cannot mutate
anything; admin cannot make AML decisions; only MLRO decides approvals.

**Data-scope: one P1 fixed.** The `assigned` scope was enforced on `/cases` (list)
but **not** on `/cases/{id}` or `/cases/{id}/network` — an object-level IDOR. Now
enforced via `_enforce_case_scope` (returns 404 to avoid leaking existence).
Verified: analyst opens own case/network → 200, any other → 404; compliance/mlro/
auditor (org-wide scope) unaffected.

**Frontend↔backend consistency: root cause found + reconciled.** Authorization
lived in **three** parallel tables that had drifted:
`permissions.py`/`useRbac` (permission-based), `authz.POLICY` (role-group), and
`config/nav.ts` `ROUTE_ROLES` (role-based, used by `AppLayout.canAccess`). The
`ROUTE_ROLES` layer runs *first* on direct navigation and still excluded auditor
from alerts/cases/network → the auditor's own menu items redirected to `/403`.
Reconciled all three (auditor read-only on alerts/cases/graph; `/users` and
`/settings` tightened to admin-only in `ROUTE_ROLES` to match the matrix).

### RBAC test matrix (as implemented & verified)

| Action | MLRO | Compliance | Analyst | Auditor | Admin |
|---|---|---|---|---|---|
| View executive dashboard | ✓ | ✗ | ✗ | ✗ | ✗ |
| View alerts / cases / graph | ✓ | ✓ | ✓ (cases: assigned) | **Read** | ✗ |
| Investigate alert / case | ✓ | ✓ | ✓ | ✗ | ✗ |
| Escalate case | ✓ | ✓ | ✓ | ✗ | ✗ |
| Prepare SAR | ✓ | ✓ | ✗ | ✗ | ✗ |
| Final AML decision (approve / decide SAR) | ✓ | ✗ | ✗ | ✗ | ✗ |
| Model inference (bitcoin) | ✓ | ✓ | ✓ | ✗ | ✗ |
| Audit log | ✓ | ✓ | ✗ | ✓ | ✓ |
| Manage users / system | ✗ | ✗ | ✗ | ✗ | ✓ |

## 5. UI/UX Results

All five dashboards render with **real endpoint data**, honest empty states
("No data" / "no endpoint yet"), and **no `Math.random`** fabrication. Console was
clean (no React key warnings, no unhandled rejections) on every dashboard.

Notable per-page issues are in the Defect List (§12); the fixed ones:
- Analyst dashboard mislabeled the org-wide alert total as "assigned to me"
  (AML-QA-004) — relabeled to an honest "open alerts / shared queue" with a scope
  note that distinguishes assignment-scoped **cases** from the shared **alert**
  queue.
- Nav alert badge rendered a raw 5-digit count `10004` (AML-QA-005) — capped to
  `999+`.

## 6. Graph QA

Tested on the analyst network view, "Mạng 01" (162 nodes / 238 edges, IBM dataset).

- **Readability: GOOD.** Force-directed layout; high-risk nodes rendered red
  (46 nodes ≥80) and clearly separable from the dark low-risk mass; node size
  encodes magnitude. The central money-flow path is highlighted with directional
  arrows. The suspicious cluster + money path are identifiable within a few
  seconds — meets the "3–5 second" bar.
- **Direction: GOOD.** Sender→receiver arrows on the highlighted flow; a legend
  distinguishes observed / inferred / money-in / money-out / reviewed edges.
- **Structural summary panel:** 12 paths, 8 cycles, 46 high-risk nodes, evidence
  coverage 100%, multi-currency flow totals (Brazil Real, UK Pound, USD, Euro),
  and an AI graph-narrative citing real account IDs and amounts. Honest zeros
  ("inference edges: 0").
- **Weaknesses:** minor label overlap in the dense centre at default zoom (labels
  are otherwise sensibly suppressed); one benign console warning (AML-QA-008).
- Interactions present (Overview/Flow/Evidence tabs, expand-1-hop, find-path,
  patterns, filters, timeline scrubber). Full interaction sweep not exhaustively
  clicked — see Limitations.

Rating: **GOOD** — communicates the money flow correctly; the one improvement is
collision-aware labelling in the dense core.

## 7. AI Agent QA

The "agent" is a **structured investigation agent** (Gemini structured output:
supervisor → explanation → evidence-critic), not a free-form chatbot. It runs on
a fixed alert/case snapshot; there is **no user-controlled prompt box**.

I triggered a **live** investigation (worker made 3 real Gemini calls, HTTP 200,
9.4s) and audited the freshly generated output:

| Test | Result | Evidence |
|---|---|---|
| Claims carry evidence references | ✓ | 13 claims, all with `evidence_refs` |
| **Hallucinated evidence** | **None** | 13 refs, 0 unresolved against the 5 evidence records |
| Fact vs inference separated | ✓ | typology match tagged `INFERENCE` conf 0.7; the rest `FACT` conf 1.0 |
| Risk score explained by real calculation | ✓ | decomposed: currency-change +100, partner-countries +40, cash +18 |
| AML language (no "is laundering") | ✓ | "nhận định của hệ thống… kết luận thuộc về chuyên viên" |
| Geography ≠ FATF label | ✓ | UK→Morocco framed as a corridor with a 0.63% suspicious base-rate "denominator the score uses" |
| Grounded transactions | ✓ | cites exact amounts/dates/dest accounts/tx-ids (e.g. 9912.59 GBP → MA:9387589639, tx 27458893) |

**Agent RBAC:** agent-run reads are gated (`/fc/agent-runs` → 403 for admin);
the agent only sees the snapshot's own evidence. Prompt-injection / "show me all
cases" tests (spec §33–34) are **not applicable** — there is no free-text channel
to inject into.

Rating: **grounding EXCELLENT · AML language EXCELLENT.** This is a genuine
strength of the product.

## 8. Chart QA

Validated the dashboard visualisations that carry data:
- MLRO/compliance typology distribution — counts match the live open alert queue
  (5,004 / 3,149 / 1,366 …); values are real, not decorative.
- Model-monitor series (`/fc/model-monitor`) returns real metrics (alert_rate,
  mean_score, scored_rows 6.75M) with drift status.
- Number formatting is consistent within dashboards (vi-VN `10.004`); the only
  inconsistency was the nav badge (`10004`, now `999+`).

Not every chart was semantically cross-checked against its API payload at the
pixel level (see Limitations); those inspected were faithful.

## 9. API / Network QA

- No failed/duplicate storms observed on dashboards; `/auth/me` is re-verified
  once on mount (by design). `/alerts/page` and `/nav-counts` returned 200.
- 401 handling: client dispatches an auth-expired event and clears the session
  (verified path exists). 403 handling on direct URL: `AppLayout` redirects to a
  styled `/403` page (now only for genuinely forbidden routes).
- No unauthorized data path remained open after fixes (IDOR closed).

## 10. Console Errors

Clean across all five dashboards, the alerts page, and the cases page. The only
console output is one benign cytoscape wheel-sensitivity warning on the graph
page (AML-QA-008). No React key warnings, hydration errors, or unhandled
rejections observed.

## 11. Performance Findings

- Live investigation end-to-end ≈ 9.4s (3 sequential LLM calls) — acceptable, and
  async (returns `QUEUED` immediately; UI is not blocked).
- Frontend bundle: `index` ~1.03 MB and `WorldPage` ~1.10 MB (gzip ~300 KB each) —
  Vite warns >500 KB. Not a demo blocker; code-splitting is a future optimisation.
- No graph freeze at 162 nodes; larger graphs not stress-tested.

## 12. Defect List

| ID | Sev | Role | Page/Area | Problem | Status |
|---|---|---|---|---|---|
| AML-QA-002 | **P1** | analyst | `/cases/{id}`, `/network` | Object-level IDOR: case detail + network ignored the `assigned` scope enforced on the list; analyst could read any case by guessing its id | **FIXED** |
| AML-QA-001 | **P2** | auditor | sidebar → alerts/cases/network | Three parallel RBAC tables drifted; auditor's own menu items redirected to a hostile `/403` "access denied" page | **FIXED** |
| AML-QA-003 | **P2** | analyst | `/cases` | No case had an assignee, so the (correct) analyst scope yielded an empty, un-demonstrable Cases workspace | **FIXED** (demo seed + script) |
| AML-QA-004 | **P2** | analyst | dashboard | Org-wide open-alert total (10,004) labeled "assigned to me / scope: assigned" — misrepresented an unenforced scope | **FIXED** |
| AML-QA-009 | P3 | all | `config/nav.ts` | `NAV[].roles` arrays are now vestigial (Sidebar filters by permission) and some disagree with the matrix — drift/confusion risk | Open (documented) |
| AML-QA-005 | P4 | all | sidebar badge | Alert badge rendered raw `10004`, overflowing the chip | **FIXED** (`999+`) |
| AML-QA-006 | P4 | all | `/fc/agent-runs` | List `step_count` = 0 while the run's trace has 25 events (field not populated) | Open (documented) |
| AML-QA-007 | P4 | all | `/403` page | Shows a frozen fake clock `2026-05-19 14:32:01 UTC` and a static request id | Open (documented) |
| AML-QA-008 | P4 | all | `/network` | Benign cytoscape "custom wheel sensitivity" console warning | Open (documented) |

## 13. Changes Made

| File | Reason | Change |
|---|---|---|
| `src/api/routes.py` | Close AML-QA-002 (IDOR) | Added `_enforce_case_scope`; `get_case` + `case_network` now resolve the user and 404 on out-of-scope cases for `assigned` roles |
| `src/api/authz.py` | Close AML-QA-001 (backend side) | Moved alerts/cases/graph **read** endpoints from `INVESTIGATION` → `INVESTIGATION_READ` (adds auditor read); investigate/crypto stay auditor-free |
| `web/src/config/nav.ts` | Close AML-QA-001 (frontend gate) | `ROUTE_ROLES`: added auditor to alerts/cases/network; tightened `/users` and `/settings` to admin-only |
| `web/src/pages/dashboard/AnalystDashboard.tsx` (nay đã gộp vào [`DashboardPage.tsx`](../web/src/pages/DashboardPage.tsx)) | Close AML-QA-004 | Honest labels: "open alerts / shared queue"; scope note distinguishes assignment-scoped cases from shared alerts |
| `web/src/components/layout/Sidebar.tsx` | Close AML-QA-005 | Badge caps at `999+` |
| `tests/test_api/test_authz.py` | Cover the new matrix | Auditor now allowed on alerts/cases/graph (read); added a test proving auditor is still **denied** the investigate write |
| `tests/conftest.py` | Fix test infra for in-body scope | `disable_authz` now supplies a full-scope test user when no token is present (real tokens still resolve normally) |
| `scripts/seed_demo_case_assignments.py` | Make AML-QA-003 reproducible | Idempotent script assigning N top cases to a demo analyst |
| `docs/RBAC.md` | Keep docs truthful | Documented case-detail scope, the shared-alert-queue limit, and the three-layer reconciliation debt |

All changes re-verified live; regression: **API 75 passed / 9 skipped**, RBAC unit
52 passed, web `tsc --noEmit` clean, `vite build` clean.

## 14. Remaining Limitations (honest — not everything in the 75-section brief was executed)

- **Not exhaustively tested:** every table's sort/filter/pagination, every
  modal/drawer, and keyboard-only accessibility. (SAR **PDF export** was
  subsequently implemented and verified end-to-end — real downloadable PDF with
  Vietnamese rendering, guards + audit intact; see `src/api/sar_pdf.py`. The
  users/approval-queue CSV exports remain client-side.)
- **Responsive:** verified at 1440×900 only; 1366×768 / 1280×800 / tablet widths
  not swept.
- **Charts:** dashboard metrics + typology distribution validated against API;
  not every chart was cross-checked payload-by-payload.
- **Workflows:** SAR prepare→validate→submit→approve was checked at the API/authz
  gate level, not click-through end-to-end in the browser.
- **Datasets:** IBM branch exercised in depth; SAML-D and Elliptic++ dataset views
  were not separately deep-audited this pass (they are independent by design — no
  score fusion — which is correct).
- **Alert-level data scope** remains architecturally absent (no `assignee` column
  on `alert`); the analyst UI now states this honestly rather than implying it.
- **RBAC single-source debt:** three authorization tables are reconciled now but
  still maintained by hand; deriving `ROUTE_ROLES`/`NAV_PERMISSION` from
  `permissions.py` would remove the drift class entirely.

## 15. Final Readiness Assessment

| Dimension | Score | Why (below 9 explained) |
|---|---|---|
| Functional correctness | 8/10 | Core flows work; SAR end-to-end and exports not click-verified |
| RBAC / security | 8/10 | Backend strong; IDOR + layer drift fixed. −2: the "single source of truth" is really three hand-synced tables (drift risk remains) and alerts have no record-level scope |
| AML workflow | 8/10 | Alert→case→graph→explanation→escalate coherent; MLRO decision + auditor read-only correct. −2: analyst assignment data is a thin demo seed, not an operational pipeline |
| UI consistency | 8/10 | Restrained dark enterprise system applied consistently; −2 for the badge/label honesty issues (now fixed) and vestigial nav metadata |
| Dashboard quality | 9/10 | Five genuinely distinct, role-appropriate dashboards on real data with honest empties |
| Chart quality | 7/10 | Inspected charts faithful; −3 because not every chart was semantically validated against its payload |
| Graph usability | 8/10 | Good hierarchy, direction, evidence; −2 for centre label overlap and un-swept interactions |
| AI agent accuracy | 9/10 | Live, correct risk decomposition, correct AML framing |
| AI agent grounding | 9/10 | Evidence-linked, zero hallucinated refs; −1 only because grounding was validated on a sample, not exhaustively |
| Responsive design | 6/10 | Only 1440×900 verified; smaller breakpoints unaudited |
| Auditability | 8/10 | Immutable `audit_log`, login/case/SAR events captured, auditor read-only; −2 because auth/role-change/export/config event types are not yet logged |
| Demo readiness | 8/10 | Clean console, real data, distinct roles, working AI; −2 for the un-swept areas above |

**Overall classification: DEMO READY WITH ISSUES.**
The security-critical defect (IDOR) and the role-consistency defects are fixed and
re-verified; what remains is polish, breadth of visual/responsive coverage, and
the structural RBAC-consolidation debt — none of which blocks a supervised demo.

## Priority Fix Plan

**Fix before demo**
- (Done) IDOR case-detail scope; auditor menu dead-ends; analyst scope label +
  demo assignments; badge overflow.
- Seed analyst assignments on any fresh DB (run `scripts/seed_demo_case_assignments.py`)
  so the analyst role demonstrates the positive scope path.

**Fix before production**
- Derive `ROUTE_ROLES` + `NAV_PERMISSION` from `permissions.py` (kill the
  three-table drift class); remove vestigial `NAV[].roles`.
- Add a record-level `assignee` to `alert` and enforce alert data-scope, or keep
  the shared-queue model explicitly.
- Expand `audit_log` to auth/login, role-change, activation, export, and config
  events (currently only case/SAR/login/settings/user-change).
- Address the `/403` page's frozen fake timestamp/request-id, and populate
  `agent-runs.step_count`.

**Nice to have**
- Collision-aware graph labels in the dense core; code-split the large bundles;
  full responsive pass at 1366×768; end-to-end SAR + export test coverage.
