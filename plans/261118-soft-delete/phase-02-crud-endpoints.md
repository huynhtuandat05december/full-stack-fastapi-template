---
phase: 2
title: "CRUD, query filtering & delete endpoints"
status: pending
priority: P1
dependencies: [1]
---

# Phase 2: CRUD, query filtering & delete endpoints

## Overview
Convert the three delete endpoints to set `deleted_at` instead of removing rows,
cascade the soft-delete to a user's items, and add `deleted_at IS NULL` filters
to every read/auth path so soft-deleted rows are invisible to the API.

## Requirements
- Functional:
  - `DELETE /items/{id}`, `DELETE /users/me`, `DELETE /users/{user_id}` set
    `deleted_at = now()` and commit; rows remain in the DB.
  - Deleting a user soft-deletes that user's items.
  - Lists, get-by-id, and auth lookups exclude soft-deleted rows.
  - Soft-deleted users cannot authenticate.
- Non-functional: no change to routes, status codes, or response bodies.

## Architecture
Use `col(Model.deleted_at).is_(None)` in SQLModel `select`/`func.count`
statements (the codebase already imports `col` from `sqlmodel`). Set the
tombstone via the model's `get_datetime_utc()` helper for UTC consistency with
`created_at`.

## Related Code Files
- Modify: `backend/app/crud.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/routes/items.py`
- Modify: `backend/app/api/routes/users.py`

## Implementation Steps

### crud.py
1. `get_user_by_email` — add filter so lookups ignore soft-deleted users:
   ```python
   statement = select(User).where(
       User.email == email, col(User.deleted_at).is_(None)
   )
   ```
   (import `col` from `sqlmodel`). This flows into `authenticate`, `create_user`
   duplicate checks, `register_user`, and `update_user` email-uniqueness checks.

### deps.py — `get_current_user`
2. After `user = session.get(User, token_data.sub)`, treat a soft-deleted user
   as not found:
   ```python
   if not user or user.deleted_at is not None:
       raise HTTPException(status_code=404, detail="User not found")
   ```
   This invalidates existing tokens for soft-deleted users.

### items.py
3. `read_items` — add `col(Item.deleted_at).is_(None)` to **all four**
   statements (superuser count + list, owner count + list).
4. `read_item` and `update_item` — after `session.get(Item, id)`, also treat a
   soft-deleted row as missing: `if not item or item.deleted_at is not None:
   raise HTTPException(404, ...)`. (`session.get` by PK bypasses query filters,
   so an explicit check is required.)
5. `delete_item` — replace `session.delete(item)` with:
   ```python
   item.deleted_at = get_datetime_utc()
   session.add(item)
   session.commit()
   ```
   Keep the existing not-found (incl. already-deleted) and permission checks.
   Import `get_datetime_utc` from `app.models`.

### users.py
6. `read_users` — add `col(User.deleted_at).is_(None)` to the count and list
   statements.
7. `read_user_by_id`, `update_user` — treat soft-deleted rows as 404 (same PK
   `session.get` caveat as items).
8. `delete_user_me` — replace `session.delete(current_user)` with setting
   `current_user.deleted_at = get_datetime_utc()`, and soft-delete the user's
   items:
   ```python
   statement = (
       update(Item)
       .where(col(Item.owner_id) == current_user.id,
              col(Item.deleted_at).is_(None))
       .values(deleted_at=get_datetime_utc())
   )
   session.exec(statement)
   current_user.deleted_at = get_datetime_utc()
   session.add(current_user)
   session.commit()
   ```
   (import `update` from `sqlmodel`; `get_datetime_utc` from `app.models`).
9. `delete_user` (admin) — same pattern: replace the
   `delete(Item).where(...)` + `session.delete(user)` block with the
   `update(Item)...` soft-delete of owned items followed by setting
   `user.deleted_at`. Remove the now-unused `delete` import if nothing else
   uses it.

## Success Criteria
- [ ] All three delete endpoints leave rows in the DB with `deleted_at` set.
- [ ] Deleting a user soft-deletes all their items.
- [ ] Soft-deleted items/users never appear in lists or get-by-id (404).
- [ ] Soft-deleted user: login returns the usual "incorrect email/password"
      path and an old token yields 404.
- [ ] `mypy app` and `ruff check` pass.

## Risk Assessment
- **`session.get(Model, pk)` ignores WHERE filters** → every get-by-PK path
  (`read_item`, `update_item`, `read_user_by_id`, `update_user`, `delete_*`)
  needs an explicit `deleted_at is not None` guard; missing one leaks deleted
  rows. Enumerated above.
- **Missed read path** leaks deleted data → grep for `select(Item`,
  `select(User`, and `func.count` to confirm every statement is filtered.
- **Email reuse** — unique constraint still blocks re-registering a
  soft-deleted user's email (accepted per plan assumption). If product needs
  reuse later, switch to a partial unique index (`WHERE deleted_at IS NULL`)
  — out of scope here.
- **Count/list mismatch** → filter count statements too, not just the list
  queries, so pagination totals stay correct.
