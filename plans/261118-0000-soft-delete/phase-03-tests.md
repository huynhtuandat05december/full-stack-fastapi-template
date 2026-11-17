---
phase: 3
title: "Tests"
status: pending
priority: P1
dependencies: [2]
---

# Phase 3: Tests

## Overview
Update and extend the backend test suite to assert soft-delete semantics: rows persist with `deleted_at` set, become invisible to reads/auth, and cascade on user delete.

## Requirements
- Functional: Tests prove DELETE is now soft, not physical.
- Non-functional: Existing green-path assertions (status codes, success messages) remain valid.

## Architecture
Existing tests (`test_delete_item`, `test_delete_user_me`, `test_delete_user_super_user`) assert the success message and (for users) a follow-up 404. They should still pass because the API contract is unchanged. Add DB-level assertions that the row still exists with `deleted_at` populated, plus new tests for invisibility and cascade.

## Related Code Files
- Modify: `backend/tests/api/routes/test_items.py`
- Modify: `backend/tests/api/routes/test_users.py`
- Modify: `backend/tests/crud/test_user.py`

## Implementation Steps
1. **test_items.py** — extend `test_delete_item`: after the successful DELETE, `db.get(Item, item.id)` (or re-query without the filter via a fresh `Session`) and assert the row still exists with `deleted_at is not None`.
2. Add `test_delete_item_soft_hidden_from_reads`: create item, delete it, then `GET /items/{id}` → 404 and confirm it is absent from `GET /items/` list + count.
3. **test_users.py** — extend `test_delete_user_super_user`: assert the user row persists with `deleted_at` set and is absent from `GET /users/` list.
4. Add `test_delete_user_cascades_soft_delete_items`: create a user with items, delete the user, assert each item row still exists with `deleted_at` set.
5. Add `test_soft_deleted_user_cannot_authenticate`: soft-delete a user, then `authenticate(...)` / a login attempt returns None/401.
6. Add `test_delete_user_me_soft`: assert own-delete sets `deleted_at` and the token no longer resolves (`GET /users/me` → 404/401).
7. **test_crud/test_user.py** — add a case asserting `get_user_by_email` returns `None` for a soft-deleted user; and that the email-reuse policy behaves per the Phase 2 default (reuse blocked → create raises/returns 400).
8. Run the suite:
   ```bash
   cd backend && bash scripts/test.sh    # or: uv run pytest
   ```
   Fix any pre-existing tests that assumed physical deletion.

## Success Criteria
- [ ] New tests assert row persistence + `deleted_at` set on delete.
- [ ] New tests assert invisibility in reads/lists/get and failed auth.
- [ ] New test asserts user→items soft cascade.
- [ ] Full backend suite passes.

## Risk Assessment
- **Filtered query hides rows from test re-reads** — use a direct `db.get(...)` / raw select ignoring the filter to inspect `deleted_at`, since the normal read path now excludes deleted rows.
- **Shared test DB state** — ensure created test users/items use unique emails/titles so soft-deleted leftovers from prior tests don't collide (esp. with email-reuse-blocked policy).
