---
phase: 3
title: "Tests & verification"
status: pending
priority: P2
dependencies: [2]
---

# Phase 3: Tests & verification

## Overview
Update and add backend tests to assert soft-delete semantics (row persists,
reads hide it, cascade works, auth blocked), then run the full quality gate.

## Requirements
- Functional: tests prove rows are soft-deleted (not removed) and invisible to
  reads; user deletion cascades to items; soft-deleted users can't authenticate.
- Non-functional: existing tests still pass; coverage not regressed.

## Architecture
Tests use the existing fixtures/helpers: `backend/tests/conftest.py` (`db`,
`client` sessions), `tests/utils/item.py` (`create_random_item`),
`tests/utils/user.py`, `tests/utils/utils.py`. Assert persistence by querying
the DB directly for the row and checking `deleted_at is not None` (the row still
exists), rather than asserting `session.get(...) is None`.

## Related Code Files
- Modify: `backend/tests/api/routes/test_items.py`
- Modify: `backend/tests/api/routes/test_users.py`
- Modify: `backend/tests/crud/test_user.py`

## Implementation Steps
1. **Items** (`test_items.py`): update the existing delete test to assert, after
   `DELETE /items/{id}` returns 200, that the item row still exists in the DB and
   `item.deleted_at is not None` (expire/refresh the session first). Add a test
   that a soft-deleted item 404s on `GET /items/{id}` and is absent from
   `GET /items/`.
2. **Users** (`test_users.py`):
   - Update `delete_user_me` / `delete_user` tests to assert the user row
     persists with `deleted_at` set (not physically gone).
   - Add a test that deleting a user with items soft-deletes those items
     (query items by `owner_id`, assert all have `deleted_at` set).
   - Add a test that a soft-deleted user is absent from `GET /users/` and
     `GET /users/{id}` returns 404.
   - Add a test that a soft-deleted user cannot obtain a token
     (`POST /login/access-token` fails) and that a previously issued token
     yields 404 on `GET /users/me`.
3. **CRUD** (`test_user.py`): add a test that `get_user_by_email` /
   `authenticate` return `None` for a soft-deleted user.
4. Run the gate:
   - `bash backend/scripts/test.sh` (or `docker compose exec backend pytest`),
   - `docker compose exec backend mypy app`,
   - `ruff check` / `ruff format --check` (pre-commit).

## Success Criteria
- [ ] New + existing backend tests pass.
- [ ] Tests assert row persistence (`deleted_at` set), not physical removal.
- [ ] Cascade, read-hiding, and auth-blocked cases are covered.
- [ ] `mypy` and `ruff` clean.

## Risk Assessment
- **Stale session cache** → use `db.expire_all()` / `db.refresh(obj)` (or a
  fresh query) before asserting `deleted_at`, or the ORM may return the
  pre-commit in-memory state.
- **Fixture user pollution** → soft-deleted users remain in the table and could
  collide on the unique `email` in later tests; use random emails
  (`random_email()`) per test as the existing helpers already do.
