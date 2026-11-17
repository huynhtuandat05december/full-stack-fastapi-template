---
title: "Soft Delete Instead of Hard Delete"
status: pending
priority: P1
mode: fast
source: skill
issue: 3
branch: sdlc/issue-3
created: 2026-11-18
blockedBy: []
blocks: []
phases:
  - { id: 1, file: phase-01-data-model-migration.md, title: "Data Model & Migration", status: pending }
  - { id: 2, file: phase-02-crud-and-endpoints.md, title: "CRUD Query Filtering & Delete Endpoints", status: pending }
  - { id: 3, file: phase-03-tests.md, title: "Tests", status: pending }
---

# Soft Delete Instead of Hard Delete

## Objective

Replace hard `DELETE` (physical row removal) with **soft delete** (mark as deleted, keep the row) for `User` and `Item` records in the FastAPI backend, so data is recoverable and auditable instead of being irreversibly destroyed.

## Problem

Current behaviour performs physical deletes:
- `backend/app/api/routes/items.py` → `delete_item` calls `session.delete(item)`.
- `backend/app/api/routes/users.py` → `delete_user_me` calls `session.delete(current_user)`; `delete_user` bulk-deletes items (`delete(Item).where(...)`) then `session.delete(user)`.
- `backend/app/models.py` → `User.items` relationship + `Item.owner_id` FK use DB `CASCADE` delete, so deleting a user physically removes their items.

Hard deletes lose data permanently with no recovery path, no audit trail, and risk accidental irreversible loss.

## Solution Summary

Add a nullable `deleted_at: datetime | None` column to both `user` and `item` tables (mirrors the existing `created_at` pattern already in `models.py`). A row is "deleted" when `deleted_at IS NOT NULL`.

- **Delete endpoints** set `deleted_at = now()` instead of removing rows.
- **Read/list/update queries** filter out rows where `deleted_at IS NOT NULL`.
- **User soft-delete cascades** to the user's items by setting `deleted_at` on them in application code (DB `CASCADE` does not fire on an UPDATE, so the cascade must be explicit).
- API response messages and shapes stay unchanged so the frontend and existing green-path tests keep passing.

## Assumptions

- **ASSUMPTION:** Soft delete is modelled with a nullable `deleted_at` timestamp column (not a boolean `is_deleted`), reusing the `datetime(timezone=True)` + `get_datetime_utc()` convention already in `models.py`. A timestamp gives both the deleted-flag and the deletion time for audit.
- **ASSUMPTION:** Soft-deleted rows are excluded from all existing read/list/update/get paths (users and items), so from the API consumer's perspective behaviour is identical to today. No "list deleted" / "restore" endpoints are added (out of scope — can be a follow-up).
- **ASSUMPTION:** DELETE endpoint HTTP responses and messages ("Item deleted successfully", "User deleted successfully", 404/403 semantics) are preserved so the frontend and existing tests are unaffected.
- **ASSUMPTION:** Soft-deleting a user cascades to soft-deleting their items (consistency with current cascade behaviour).
- **ASSUMPTION:** The DB-level `ondelete="CASCADE"` FK and `cascade_delete=True` relationship stay in place (harmless; they only matter for an actual physical delete) to avoid an unnecessary schema/relationship change. The migration only adds columns.
- **ASSUMPTION:** The email-uniqueness check on user create/register continues to consider soft-deleted users as occupying the email (do not silently allow re-registering a soft-deleted email) — safest default to avoid unique-constraint collisions; revisit if product wants email reuse.

## Phase Roadmap

| Phase | Title | Priority | Depends on |
|-------|-------|----------|------------|
| 1 | Data Model & Migration | P1 | — |
| 2 | CRUD Query Filtering & Delete Endpoints | P1 | 1 |
| 3 | Tests | P1 | 2 |

## Affected Files

- Modify: `backend/app/models.py` — add `deleted_at` to `User` and `Item` tables.
- Create: `backend/app/alembic/versions/<rev>_add_deleted_at_soft_delete.py` — add columns.
- Modify: `backend/app/api/routes/items.py` — soft-delete + filter reads.
- Modify: `backend/app/api/routes/users.py` — soft-delete (+ item cascade) + filter reads + email check.
- Modify: `backend/app/crud.py` — filter `get_user_by_email`; add soft-delete helper(s) if useful.
- Modify: `backend/app/api/deps.py` — reject auth for soft-deleted users (`get_current_user`).
- Modify: `backend/tests/api/routes/test_items.py`, `backend/tests/api/routes/test_users.py`, `backend/tests/crud/test_user.py` — assert soft-delete semantics.

## Success Criteria

- [ ] `DELETE /items/{id}` and `DELETE /users/...` leave the row in the DB with `deleted_at` set.
- [ ] Soft-deleted users/items no longer appear in list/get/update endpoints and cannot authenticate.
- [ ] Soft-deleting a user soft-deletes their items.
- [ ] Alembic migration applies cleanly (`alembic upgrade head`) and downgrades.
- [ ] `backend` test suite passes, including new soft-delete assertions.

## Out of Scope

- Restore/undelete endpoints and admin "view deleted" UI.
- Hard-delete purge job / retention policy for old soft-deleted rows.
- Frontend changes (API contract is unchanged).

## Open Questions

None (defaults logged as ASSUMPTIONs above).
