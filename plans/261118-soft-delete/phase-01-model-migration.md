---
phase: 1
title: "Data model + Alembic migration"
status: pending
priority: P1
dependencies: []
---

# Phase 1: Data model + Alembic migration

## Overview
Add a nullable, indexed `deleted_at` timestamp column to both `User` and `Item`
SQLModel tables and generate a reversible Alembic migration that creates those
columns.

## Requirements
- Functional: `User` and `Item` rows can carry a soft-delete tombstone
  (`deleted_at`); `NULL` = live, non-null = deleted.
- Non-functional: migration is reversible; column indexed for efficient
  `deleted_at IS NULL` filtering; no data loss for existing rows (default NULL).

## Architecture
`deleted_at` mirrors the existing `created_at` pattern already on both models
(`created_at: datetime | None = Field(default_factory=get_datetime_utc)`), but
defaults to `None` (not set on insert) and is `index=True`.

## Related Code Files
- Modify: `backend/app/models.py`
- Create: `backend/app/alembic/versions/<rev>_add_deleted_at_soft_delete.py`

## Implementation Steps
1. In `backend/app/models.py`, add to the `User` table model (after
   `created_at`, line ~54):
   ```python
   deleted_at: datetime | None = Field(default=None, nullable=True, index=True)
   ```
2. Add the identical field to the `Item` table model (after `created_at`,
   line ~89).
   - Do **not** add `deleted_at` to `UserPublic` / `ItemPublic` — it stays
     internal and out of API responses (keeps the contract unchanged).
3. Create the Alembic migration. Preferred: run
   `docker compose exec backend alembic revision --autogenerate -m "add deleted_at soft delete"`
   (per `development.md`). If generating by hand, base it on
   `fe56fa70289e_add_created_at_to_user_and_item.py` and set:
   - `down_revision = 'fe56fa70289e'` (current head — verified via revision chain)
   - `upgrade()`:
     ```python
     op.add_column('user', sa.Column('deleted_at', sa.DateTime(), nullable=True))
     op.create_index(op.f('ix_user_deleted_at'), 'user', ['deleted_at'])
     op.add_column('item', sa.Column('deleted_at', sa.DateTime(), nullable=True))
     op.create_index(op.f('ix_item_deleted_at'), 'item', ['deleted_at'])
     ```
   - `downgrade()`: drop both indexes then both columns (reverse order).
4. Confirm the new revision becomes the single head (`alembic heads` → one id).

## Success Criteria
- [ ] `User.deleted_at` and `Item.deleted_at` exist, nullable, indexed.
- [ ] `deleted_at` is absent from `UserPublic` / `ItemPublic`.
- [ ] Migration applies cleanly (`alembic upgrade head`) and reverses
      (`alembic downgrade -1`) on an existing DB.
- [ ] `alembic heads` reports exactly one head.

## Risk Assessment
- **Multiple Alembic heads** if the migration's `down_revision` is wrong →
  verify `fe56fa70289e` is the current head before writing (chain:
  e2412789c190 → 9c0a54914c78 → d98dd8ec85a3 → 1a31ce608336 → fe56fa70289e).
- **Autogenerate drift** (SQLite vs Postgres index naming) → prefer
  autogenerate inside the backend container so it matches the configured DB.
