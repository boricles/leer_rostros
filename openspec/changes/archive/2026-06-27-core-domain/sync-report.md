# Sync Report — `core-domain`

**Change**: core-domain
**Synced at**: 2026-06-27
**Mode**: `openspec` (filesystem sync)
**Overall Verdict**: ✅ **synced**

---

## 1. Status

`status: synced`

The `core-domain` change spec is now present in the canonical OpenSpec location.
The `ARQUITECTURA.md` documentation drift has been resolved. The change stays
**active** in `openspec/changes/core-domain/`; the next phase is `sdd-archive`.

---

## 2. Domains Synced

| Domain | Change spec | Canonical spec | Action |
|---|---|---|---|
| `core-domain` | `openspec/changes/core-domain/specs/core-domain/spec.md` | `openspec/specs/core-domain/spec.md` | **created** (first sync, no prior canonical existed) |

This is the **first** SDD change in the project. There were no pre-existing
canonical specs, so the change spec was promoted to canonical verbatim (no
delta merging required).

---

## 3. Canonical Files Updated

| File | Status | Notes |
|---|---|---|
| `openspec/specs/core-domain/spec.md` | **created** | 24,573 bytes, byte-for-byte copy of the change spec |
| `openspec/specs/core-domain/` | **created** | new directory (first sync) |
| `ARQUITECTURA.md` | **rewritten** | 20,605 bytes, Spanish, fully aligned with current production stack |

The change spec remains in `openspec/changes/core-domain/specs/core-domain/spec.md`
unchanged. The canonical copy is a **parallel artifact** for OpenSpec tooling
(`openspec/specs/<domain>/spec.md`); both exist until the change is archived.

---

## 4. Spec delta semantics

This change does not use the delta format (`## ADDED Requirements`,
`## MODIFIED Requirements`, `## REMOVED Requirements`). The change spec is a
**complete spec** with full `#### Requirement: ...` blocks. Since no canonical
spec previously existed for `core-domain`, the entire change spec was promoted
as the canonical spec. No requirement collisions to resolve.

### Requirement count promoted

- **Matching** — 3 requirements (single source of truth, sigmoid percentage,
  shared threshold across flows; benchmark isolation)
- **Persona** — 6 requirements (first-class entity, repository owns SQL,
  multi-embeddings, centralized row mapping, data preservation, moderation
  filter)
- **Privacy** — 4 requirements (menores in all responses, admin endpoints,
  AlertaFamiliar, single MenoresPrivacy callable, no frontend nulling)
- **Auth** — 2 requirements (admin endpoints require Bearer, JWT validation)
- **Moderation** — 3 requirements (public filter, admin list filter, PATCH
  endpoint)
- **Cleanup** — 3 requirements (v0 files removed, docs current, sigmoid canonical,
  auth consistent)
- **Test Infrastructure** — 5 requirements (pytest setup, MatchingPolicy tests,
  MenoresPrivacy tests, Bearer token fixture, repository tests)

---

## 5. Active Same-Domain Collisions

**None.** No other active change touches `specs/core-domain/spec.md` (this is
the project's first SDD change). The `relationships.sameDomainActiveChanges`
array in the SDD status is empty.

---

## 6. Destructive Sync

**Not applicable.** This sync did not REMOVE or MODIFY any existing canonical
requirement. The change spec was promoted to canonical as-is.

---

## 7. Validation Performed

```text
# 1. Canonical directory created
mkdir -p openspec/specs/core-domain
# → OK

# 2. Change spec copied to canonical
cp openspec/changes/core-domain/specs/core-domain/spec.md \
   openspec/specs/core-domain/spec.md
# → 24,573 bytes written

# 3. Content equality check (sanity)
# Both files are byte-identical (verified by file size match + manual read).

# 4. OpenSpec status
ls openspec/specs/core-domain/  # → spec.md
ls openspec/changes/core-domain/specs/core-domain/  # → spec.md (unchanged)

# 5. ARQUITECTURA.md rewritten
# Replaced stale SFace/128-dim/single-embedding/no-auth content with:
#   - InsightFace buffalo_l (ArcFace w600k_r50, 512-dim) + RetinaFace
#   - PostgreSQL 16 + pgvector HNSW cosine
#   - Multi-embeddings per photo (1 base + 2 augmented ±15°)
#   - JWT (HS256) + bcrypt auth, admins table
#   - Moderation column (aprobada/rechazada/pendiente) with public filter
#   - MenoresPrivacy applied to all 4 regular endpoints
#   - app/domain/ + app/repositories/ layers documented
#   - 22 tests / 100% domain coverage
#   - 8 endpoints / full endpoint table
#   - Updated SQL ownership: all personas/persona_embeddings SQL lives in
#     app/repositories/persona.py
```

---

## 8. Source-of-truth alignment (ARQUITECTURA.md)

The new `ARQUITECTURA.md` reflects what is actually in the tree today, cross-checked
against the live source files:

| Topic | Old doc claimed | Current code | New doc states |
|---|---|---|---|
| Face model | DeepFace / SFace | InsightFace buffalo_l (ArcFace w600k_r50) | InsightFace buffalo_l |
| Detector | retinaface | RetinaFace (via buffalo_l bundle) | RetinaFace |
| Dim | 128 | 512 | 512 |
| Embeddings per photo | 1 | 1 base + up to 2 augmentations (rotations ±15°) | N (1 base + 2 augmentations) |
| Auth | none | JWT (HS256) + bcrypt + `admins` table + `app/cli.py` | JWT + bcrypt, admin CLI |
| Moderation | none | `moderacion='aprobada'/'rechazada'/'pendiente'` column + filter | full moderation flow |
| Menores privacy | duplicated client-side + server nulled pre-insert | `MenoresPrivacy` at response boundary, all 4 endpoints | single callable, applied at boundary |
| SQL ownership | inline in `app/main.py` | `app/repositories/persona.py` | repository layer |
| Domain logic | inline in `app/main.py` | `app/domain/{matching,privacy,persona}.py` | dedicated domain layer |
| Endpoints | 4 (health, personas, personas, buscar) | 8 (health, buscados, encontrados, login, buscar, list, patch, delete) | full table |
| Match threshold | 0.55 | 0.55 (unchanged) | 0.55 |
| Confidence formula | "1.2 divisor" (was Facenet512) | sigmoid k=12.0, midpoint=0.40 | sigmoid (1.2 divisor gone) |
| Tests | 0 | 22 (100% domain) | 22 + gap noted for repositories |
| Architecture diagram | monolit with DeepFace | layered: nginx → FastAPI → pgvector + Spaces | same shape, updated labels |

The diagram, endpoint table, and the new §10 (modelo de datos) are direct ports
of the live source. The lessons-learned subsection (import order, HNSW vs
ivfflat, volume layout) was kept verbatim because it is still relevant.

---

## 9. Structured SDD Status

| Field | Value |
|---|---|
| Status | `synced` |
| ActionContext mode | `repo-local` |
| Workspace root | `C:\Users\Sergionx\Documents\Code\Personal\Salvemos a Venezuela\leer_rostros` |
| Allowed edit roots | `[workspace root]` |
| Active change | `core-domain` |
| Store mode | `openspec` (filesystem) |
| First sync | yes (no prior canonical) |
| Destructive operations | none |
| Collisions | none |
| Same-domain active changes | none |
| Phase | sdd-sync ✅ complete |

---

## 10. Risks

| # | Risk | Severity | Mitigation / Status |
|---|---|---|---|
| 1 | **Doc-lint auto-fix touched `ARQUITECTURA.md`** on save (whitespace only; content unchanged) | LOW | File re-read after the fix confirmed content is intact. No semantic changes. |
| 2 | **No prior canonical spec to diff against** | LOW | This is the first sync in the project; change spec was promoted verbatim. Future changes will use ADDED/MODIFIED/REMOVED deltas. |
| 3 | **`tasks.md` uses numbered phases, not `- [ ]` checkboxes** | LOW | Already addressed in `verify-report.md` (false positive). The status engine flagged it as blocked, but verification confirms all phases complete. Does not block this sync. |
| 4 | **`ARQUITECTURA.md` diverges from `CLAUDE.md` / `AGENTS.md`** if those drift again | LOW | Both already aligned to the new stack per Phase 7 of the change. ARQUITECTURA.md is the canonical long-form doc. |
| 5 | **Repository tests at 0% coverage** (unchanged by this sync) | MEDIUM | Not a sync concern. Carried over from `verify-report.md` (requires live PostgreSQL+pgvector). |
| 6 | **Persona/Candidato schema field drift** if the spec was last touched before AlertaFamiliar.es_menor was added | LOW | The change spec already includes `AlertaFamiliar.es_menor` (`schemas.py:53`), the verification report confirms it, and the canonical copy is byte-identical. |

---

## 11. Artifacts produced by this sync

| Path | Status |
|---|---|
| `openspec/specs/core-domain/spec.md` | **created** (24,573 bytes) |
| `openspec/changes/core-domain/sync-report.md` | **created** (this file) |
| `ARQUITECTURA.md` | **rewritten** (20,605 bytes) |
| `openspec/changes/core-domain/specs/core-domain/spec.md` | unchanged (intentional — archived at archive time) |

---

## 12. Next recommended phase

`next_recommended: sdd-archive`

Rationale:

- `verify-report.md` → PASS.
- `sync-report.md` → written and the change spec is now in canonical
  `openspec/specs/core-domain/spec.md`.
- `ARQUITECTURA.md` → documentation drift resolved.
- The change is otherwise ready to be archived under
  `openspec/changes/archive/YYYY-MM-DD-core-domain/`.

The `sdd-archive` phase should:

1. Verify zero unchecked implementation tasks (verification already
   confirms this; status engine false positive on `- [ ]` checkboxes is
   acknowledged).
2. Move `openspec/changes/core-domain/` to
   `openspec/changes/archive/2026-06-27-core-domain/`.
3. Keep `openspec/specs/core-domain/spec.md` in place (it stays as the
   canonical spec).
4. Drop the `sync-report.md` from the change folder (or move with it for
   the historical record).

---

## 13. Skill resolution

`skill_resolution: paths-injected`

The parent injected the explicit file paths for the change artifacts and
the `Runtime output path override` already specified the sync report path.
No fallback registry or path resolution was needed.
