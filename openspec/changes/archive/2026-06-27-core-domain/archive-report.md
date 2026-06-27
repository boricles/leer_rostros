# Archive Report — `core-domain`

**Change**: core-domain
**Archived at**: 2026-06-27
**Archive path**: `openspec/changes/archive/2026-06-27-core-domain/`
**Status**: ✅ **archived**

---

## 1. Preconditions Check

| Precondition | Status | Evidence |
|---|---|---|
| verify-report.md exists and says PASS | ✅ PASS | `openspec/changes/core-domain/verify-report.md` — Overall Verdict: ✅ **PASS**, 22/22 tests pass, domain 100% coverage |
| sync-report.md exists and says synced | ✅ PASS | `openspec/changes/core-domain/sync-report.md` — `status: synced`, canonical created at `openspec/specs/core-domain/spec.md` |
| Canonical spec exists at `openspec/specs/core-domain/spec.md` | ✅ PASS | 24,573 bytes, byte-for-byte copy of change spec |
| No `- [ ]` unchecked implementation tasks | ✅ PASS | Tasks.md uses numbered task headings (no markdown checkboxes); grep confirms zero `- [ ]` patterns |
| All 9 phases complete per apply-progress.md | ✅ PASS | Apply-progress.md confirms Phases 1-9 complete; verify-report cross-checks all spec requirements |
| Verified implementation correctness | ✅ PASS | Verify-report audits every requirement with file:line citations |

---

## 2. Artifacts Read

| Artifact | Status |
|---|---|
| `openspec/changes/core-domain/proposal.md` | ✅ Read — 8 product decisions confirmed |
| `openspec/changes/core-domain/specs/core-domain/spec.md` | ✅ Read — 26 requirements across 7 categories |
| `openspec/changes/core-domain/design.md` | ✅ Read — module map, public interfaces, data flows, SQL ownership |
| `openspec/changes/core-domain/tasks.md` | ✅ Read — 9 phases, numbered tasks (no checkboxes) |
| `openspec/changes/core-domain/apply-progress.md` | ✅ Read — all phases complete, 22/22 tests, 100% domain coverage |
| `openspec/changes/core-domain/verify-report.md` | ✅ Read — PASS, all spec requirements verified |
| `openspec/changes/core-domain/sync-report.md` | ✅ Read — synced, canonical spec created |
| `openspec/specs/core-domain/spec.md` | ✅ Read — canonical spec exists (first sync) |
| `openspec/changes/core-domain/explore.md` | ✅ Read — exploration notes (carried into archive) |
| `openspec/config.yaml` | ✅ Read — `active_change: core-domain` present |

---

## 3. Domains Synced

| Domain | Change Spec | Canonical Spec | Action |
|---|---|---|---|
| `core-domain` | `openspec/changes/core-domain/specs/core-domain/spec.md` | `openspec/specs/core-domain/spec.md` | **created** (first sync, no prior canonical) |

---

## 4. ADDED / MODIFIED / REMOVED Requirements

Since this is the **first SDD change** in the project, all requirements are **ADDED** (no prior canonical spec for `core-domain`).

### ADDED Requirements (by section)

**Matching** (3 requirements):

- Single source of truth for match threshold (`MatchingPolicy` loaded from `Settings.match_threshold`)
- Percentage formula uses sigmoid from `faces.distance_to_confidence`
- Cross-flow alert and ranking list share the same threshold
- Benchmark thresholds isolated from production

**Persona** (6 requirements):

- Persona is a first-class entity (`PersonaBase`, `Estado` enum, `Foto` dataclass)
- PersonaRepository owns all SQL for personas and persona_embeddings tables
- Persona handles multi-embeddings per photo (ROW_NUMBER() OVER PARTITION BY)
- Row-to-model mapping is centralized
- Menores names are stored, not nulled, before persistence (data preservation bug fix)
- Persona repository filters public searches by `moderacion='aprobada'`

**Privacy** (4 requirements):

- Menores privacy applied to ALL regular API responses (public AND admin — Q1 revised)
- Menores privacy applied in regular admin endpoints; super-admin role bypass out of scope
- AlertaFamiliar respects menores privacy (live privacy bug fix)
- MenoresPrivacy is a single callable
- Frontend no longer applies its own nulling logic

**Auth** (2 requirements):

- Admin endpoints require Bearer token
- Bearer token validated against Settings.admin_password (*deviated*: actual implementation uses JWT+bcrypt)

**Moderation** (3 requirements):

- Public searches filter by `moderacion='aprobada'`
- Admin can list by moderacion status
- PATCH /admin/personas/{id}/moderacion updates status

**Cleanup** (5 requirements):

- v0 prototype files removed (load_image.py, search_image.py, root main.py, haarcascade_frontalface_default.xml)
- Documentation reflects current production stack (CLAUDE.md, AGENTS.md rewritten)
- Repository uses sigmoid for confidence (old 1.2 divisor removed)
- Auth is consistent across admin endpoints

**Test Infrastructure** (5 requirements):

- pytest infrastructure in place
- MatchingPolicy has unit tests (14 tests, 100% coverage)
- MenoresPrivacy has unit tests (8 tests, 100% coverage)
- Auth tests use Bearer token fixture
- Repository tests cover multi-embeddings (*gap*: not implemented, requires live DB)

---

## 5. Active Same-Domain Change Warnings

**None.** No other active change touches `specs/core-domain/spec.md`. The `relationships.sameDomainActiveChanges` array in the SDD status is empty.

---

## 6. Stale-Checkbox Reconciliation

**Task numbering style**: `tasks.md` uses numbered task headings (e.g., `### Task 1.1: Add dev dependencies for testing`) organized by phase (1–9). There are **no `- [ ]` markdown checkboxes** anywhere in the file.

**Rationale for not blocking**: The SDD status engine flagged "tasks.md has no implementation task checkboxes" as a potential blocker. This is a **structural false positive** — the numbered phase structure provides equivalent traceability. All 9 phases are confirmed complete:

- `apply-progress.md` documents every phase with files created/modified, verifications, and notes
- `verify-report.md` cross-checks every spec requirement against the implementation with file:line citations
- 22/22 tests pass with 100% domain coverage

**Reconciliation**: The numbered task format is an accepted deviation from the standard `- [ ]` checkbox convention. No stale checkboxes exist because no checkboxes exist. Complete verification is achieved through apply-progress.md and verify-report.md cross-referencing.

---

## 7. Non-Critical Partial Archive Approval

**N/A.** The full change is being archived. No partial archive approval was needed.

---

## 8. Structured Status and ActionContext Findings

| Field | Value |
|---|---|
| Status | `archived` |
| Change | `core-domain` |
| Artifact store | `openspec` (filesystem) |
| ActionContext mode | `repo-local` |
| Workspace root | `C:\Users\Sergionx\Documents\Code\Personal\Salvemos a Venezuela\leer_rostros` |
| Allowed edit roots | `[workspace root]` |
| Preconditions | All met |
| Destructive operations | None (first sync) |
| Collisions | None |
| Same-domain active changes | None |

---

## 9. Destructive Merge Approvals or Blockers

**N/A.** This was the first SDD change for this project. No MODIFIED or REMOVED canonical requirements existed. The change spec was promoted verbatim as the canonical spec. No destructive merge was required.

---

## 10. Archived Path

```
openspec/changes/archive/2026-06-27-core-domain/
├── archive-report.md       ✅ (created)
├── apply-progress.md       ✅ (moved)
├── design.md               ✅ (moved)
├── explore.md              ✅ (moved — exploration notes, valuable for future reference)
├── proposal.md             ✅ (moved)
├── specs/
│   └── core-domain/
│       └── spec.md         ✅ (moved — change delta spec, canonical remains in openspec/specs/)
├── sync-report.md          ✅ (moved)
├── tasks.md                ✅ (moved)
└── verify-report.md        ✅ (moved)
```

**Canonical spec preserved at**: `openspec/specs/core-domain/spec.md` (unchanged by archive)

---

## 11. Memory Observation IDs

**N/A.** Mode is `openspec` (filesystem). No memory observations were created or retrieved.

---

## 12. Deviations from Design (Carried Forward)

| # | Deviation | Design Expectation | Actual Implementation | Assessment |
|---|---|---|---|---|
| 1 | **Auth upgraded** | Simple sha256 hash | JWT (HS256) + bcrypt with `admins` table, token expiry, `app/cli.py` | ✅ Security improvement |
| 2 | **CLI added** | Not in spec | `app/cli.py` for admin management | ✅ Operationally necessary |
| 3 | **Config extended** | Only `match_threshold` | Added `jwt_secret`, `jwt_algorithm`, `jwt_expires_minutes` | ✅ Required by JWT auth |
| 4 | **Repository tests not implemented** | Design said optional ("in-memory fake") | `tests/repositories/` has empty `__init__.py` only | ⚠️ Known gap — requires live PostgreSQL+pgvector |
| 5 | **`admins` table** | Not in original scope | Added to `database.py:129` | ✅ Required by JWT auth |

---

## 13. Residual Risks

| # | Risk | Severity | Notes |
|---|---|---|---|
| 1 | Repository layer at 0% test coverage | MEDIUM | Requires live PostgreSQL+pgvector for integration tests |
| 2 | No integration tests for full endpoints | LOW | Domain tests cover all logic (100% coverage) |
| 3 | Frontend XSS risk (pre-existing innerHTML usage) | LOW | Out of scope for this change |
| 4 | JWT_SECRET empty by default | LOW | Startup warns, fails at first login attempt |

---

## 14. config.yaml Update

`openspec/config.yaml` had `active_change: core-domain`. This has been **removed** since the change is archived. The change can be referenced historically via the archive path `openspec/changes/archive/2026-06-27-core-domain/`.

---

## 15. Next Recommended

**End of SDD flow.** The change is shipped. The user can commit and push.

Future work:

1. **Repository integration tests** — requires test database setup
2. **Manual smoke testing** with live database and InsightFace model before production deployment
3. **Frontend security audit** for innerHTML XSS risks (separate change)
