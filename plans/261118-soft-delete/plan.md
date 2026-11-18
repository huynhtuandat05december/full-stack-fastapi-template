---
title: "Soft delete instead of hard delete"
status: pending
created: 2026-11-18
branch: sdlc/issue-5
issue: 5
mode: fast
blockedBy: []
blocks: []
---

# Soft delete instead of hard delete

## Summary

Replace the current **hard deletes** (`session.delete(...)` / `DELETE FROM ...`)
for `User` and `Item` with **soft deletes**: mark a row as deleted by setting a
`deleted_at` timestamp instead of physically removing it. All read paths must
then exclude soft-deleted rows so the API behaves identically to callers, while
data is retained in the database for audit / recovery.

This keeps the public HTTP contract unchanged (same endpoints, same
`Message` responses, same 404s for missing rows) while changing the underlying
persistence behavior.

## Problem

`backend/app/api/routes/items.py` and `backend/app/api/routes/users.py`
permanently destroy rows:

- `DELETE /items/{id}` → `session.delete(item)` (items.py:111)
- `DELETE /users/me` → `session.delete(current_user)` (users.py:141)
- `DELETE /users/{user_id}` → `delete(Item).where(...)` + `session.delete(user)`
  (users.py:228-230), relying on DB `ON DELETE CASCADE` for owned items.

Once deleted, records are unrecoverable and any audit history is lost.

## Goals

- Deletes mark rows as deleted (`deleted_at` set) rather than removing them.
- All reads (list, get-by-id, auth lookups) exclude soft-deleted rows.
- Deleting a user soft-deletes that user's items (cascade preserved logically).
- No change to the external API contract: same routes, status codes, and
  response bodies.

## Non-Goals

- No new "restore"/"undelete" endpoints (can be a follow-up).
- No admin "view trashed records" endpoint.
- No scheduled purge / retention job.
- No frontend changes — the generated client and UI are unaffected because the
  API contract is unchanged.

## Approach

Add a nullable, indexed `deleted_at: datetime | None` column to `User` and
`Item`. `deleted_at IS NULL` means "live"; a non-null value is the soft-delete
tombstone timestamp.

- **Writes:** delete endpoints set `deleted_at = now()` and `commit()` instead
  of `session.delete()`.
- **Reads:** every query that returns `User`/`Item` adds a
  `deleted_at IS NULL` filter. Auth lookups (`get_user_by_email`,
  `get_current_user`) treat soft-deleted users as non-existent/invalid.
- **Cascade:** soft-deleting a user runs an `UPDATE Item SET deleted_at=now()
  WHERE owner_id = :id AND deleted_at IS NULL`. The DB `ON DELETE CASCADE`
  foreign key stays in place as a safety net (it only fires on true deletes).

### Key decisions / assumptions

- **ASSUMPTION:** Use a nullable `deleted_at` timestamp (not an `is_deleted`
  boolean) — it records *when* deletion happened and is the common pattern; a
  single column covers both the flag and the audit timestamp.
- **ASSUMPTION:** `User.email` stays globally unique *including* soft-deleted
  rows. Re-registering with the email of a soft-deleted user is rejected
  (409/400 as today). This is the simplest, lowest-risk behavior; a partial
  unique index excluding soft-deleted rows is noted as a future option in
  Phase 2 risks.
- **ASSUMPTION:** Soft-deleted users cannot authenticate — login and
  `get_current_user` behave as if the user does not exist / is invalid.
- **ASSUMPTION:** Delete endpoints keep returning HTTP 200 with the existing
  `Message` body; deleting an already-soft-deleted row returns 404 (it is no
  longer visible to reads), matching today's "not found" behavior.

## Phases

| Phase | Title | Status | Priority |
|-------|-------|--------|----------|
| 1 | Data model + Alembic migration | pending | P1 |
| 2 | CRUD, query filtering & delete endpoints | pending | P1 |
| 3 | Tests & verification | pending | P2 |

See `phase-01-model-migration.md`, `phase-02-crud-endpoints.md`,
`phase-03-tests.md`.

## Affected files

- Modify: `backend/app/models.py` (add `deleted_at` to `User`, `Item`)
- Create: `backend/app/alembic/versions/<new>_add_deleted_at_soft_delete.py`
- Modify: `backend/app/crud.py` (filter deleted in lookups)
- Modify: `backend/app/api/deps.py` (reject soft-deleted in `get_current_user`)
- Modify: `backend/app/api/routes/items.py` (filter reads; soft-delete)
- Modify: `backend/app/api/routes/users.py` (filter reads; soft-delete + cascade)
- Modify: `backend/tests/api/routes/test_items.py`
- Modify: `backend/tests/api/routes/test_users.py`
- Modify: `backend/tests/crud/test_user.py`

## Acceptance criteria

- [ ] `User` and `Item` have an indexed nullable `deleted_at` column; a
      reversible Alembic migration adds it (`down_revision = 'fe56fa70289e'`).
- [ ] `DELETE /items/{id}`, `DELETE /users/me`, `DELETE /users/{user_id}` set
      `deleted_at` and leave the row physically present in the DB.
- [ ] Deleting a user soft-deletes all of that user's items.
- [ ] Soft-deleted items/users are absent from every list, get-by-id (404),
      and admin read.
- [ ] A soft-deleted user cannot log in or use an existing token.
- [ ] All existing + new backend tests pass (`bash backend/scripts/test.sh` or
      `pytest`), and `mypy` / `ruff` pass.

## Open questions

- None (defaults chosen above; revisit email-reuse policy if product requires
  re-registration with a deleted user's email).
