---
phase: 2
title: "CRUD Query Filtering & Delete Endpoints"
status: pending
priority: P1
dependencies: [1]
---

# Phase 2: CRUD Query Filtering & Delete Endpoints

## Overview
Convert DELETE endpoints to set `deleted_at` instead of removing rows, cascade user soft-delete to items, and exclude soft-deleted rows from every read/list/update/get/auth path.

## Requirements
- Functional: DELETE marks rows deleted; deleted rows are invisible to all other endpoints and to authentication; deleting a user soft-deletes their items.
- Non-functional: API response messages/shapes unchanged; keep KISS — a single reusable "not deleted" predicate.

## Architecture
A row is active when `deleted_at IS NULL`. Every query that currently selects `User`/`Item` gains a `.where(col(Model.deleted_at) == None)` (SQLModel/SQLAlchemy `IS NULL`) filter, including the `count(...)` statements so counts stay consistent with the data lists. DELETE handlers stop calling `session.delete(...)` and instead set `deleted_at = get_datetime_utc()`, `session.add(...)`, `session.commit()`. For `delete_user`, replace the bulk `delete(Item)` with a bulk `update(Item).values(deleted_at=...)` over the user's items.

> Note: DB-level `ondelete="CASCADE"` no longer fires (no physical delete), which is why the item cascade must be done explicitly in `delete_user`. `delete_user_me` currently does not touch items; keep parity by also soft-deleting that user's items.

## Related Code Files
- Modify: `backend/app/api/routes/items.py`
- Modify: `backend/app/api/routes/users.py`
- Modify: `backend/app/crud.py`
- Modify: `backend/app/api/deps.py`

## Implementation Steps
1. **items.py — `delete_item`:** replace `session.delete(item)` with:
   ```python
   from app.models import get_datetime_utc  # or import datetime helper
   item.deleted_at = get_datetime_utc()
   session.add(item)
   session.commit()
   ```
   Keep the 404/403 checks and `Message(message="Item deleted successfully")`.
2. **items.py — reads:** add `.where(col(Item.deleted_at).is_(None))` to both the `count_statement` and the list `statement` in `read_items` (superuser and owner branches). In `read_item`, `update_item`, and `delete_item`, after `session.get(Item, id)`, treat a row with `deleted_at` set as not found (`if not item or item.deleted_at: raise HTTPException(404, ...)`).
3. **users.py — `delete_user_me`:** set `current_user.deleted_at = get_datetime_utc()`; also soft-delete the user's items via bulk update:
   ```python
   session.exec(update(Item).where(col(Item.owner_id) == current_user.id).values(deleted_at=get_datetime_utc()))
   session.add(current_user)
   session.commit()
   ```
   (import `update` from `sqlmodel`). Keep the superuser-self-delete 403 guard and success message.
4. **users.py — `delete_user`:** replace `delete(Item).where(...)` with the equivalent `update(Item)...values(deleted_at=...)`, and replace `session.delete(user)` with `user.deleted_at = get_datetime_utc(); session.add(user)`. Keep guards and message.
5. **users.py — reads:** add the not-deleted filter to `read_users` `count_statement` and `statement`. In `read_user_by_id`, `update_user`, `delete_user`, treat `session.get(User, ...)` rows with `deleted_at` set as not found (404).
6. **crud.py — `get_user_by_email`:** add `.where(col(User.deleted_at).is_(None))` (import `col`) so soft-deleted emails are excluded from `authenticate`. Decide email-reuse policy per plan ASSUMPTION: keep the create/register uniqueness check seeing soft-deleted users as taken — since `get_user_by_email` now hides them, ALSO add an explicit check in `create_user`/`register_user` paths if email reuse must stay blocked (query ignoring the filter), OR accept that a soft-deleted email can be re-registered. Default: **block reuse** — add a dedicated lookup that ignores the `deleted_at` filter for the uniqueness guard, and document it.
7. **deps.py — `get_current_user`:** after `session.get(User, token_data.sub)`, reject soft-deleted users: `if not user or user.deleted_at: raise HTTPException(404, "User not found")` (keeps tokens for deleted users from working).

## Success Criteria
- [ ] All DELETE handlers set `deleted_at` and never call `session.delete(...)`.
- [ ] `read_items`/`read_users` lists + counts exclude soft-deleted rows.
- [ ] `get`/`update`/`delete` by id return 404 for soft-deleted rows.
- [ ] Soft-deleting a user soft-deletes their items.
- [ ] A soft-deleted user cannot authenticate (`get_current_user` + `authenticate`).
- [ ] Email-reuse policy implemented and documented (default: reuse blocked).

## Risk Assessment
- **Missed query path** leaks deleted rows. Mitigation: grep for `select(Item)`, `select(User)`, `session.get(Item`, `session.get(User`, `func.count()` and audit each.
- **`== None` lint** — use `col(Model.deleted_at).is_(None)` to satisfy SQLAlchemy/linters instead of `== None`.
- **Timezone mismatch** — reuse `get_datetime_utc()` everywhere for consistency with `created_at`.
- **Cascade gap** — `delete_user_me` previously didn't touch items; verify both user-delete paths soft-delete items.
