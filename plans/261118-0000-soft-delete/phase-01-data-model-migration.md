---
phase: 1
title: "Data Model & Migration"
status: pending
priority: P1
dependencies: []
---

# Phase 1: Data Model & Migration

## Overview
Add a nullable `deleted_at` timestamp column to the `User` and `Item` tables and generate the Alembic migration that creates it.

## Requirements
- Functional: Every `user` and `item` row can carry a deletion timestamp; `NULL` = active, non-null = soft-deleted.
- Non-functional: Reuse the existing timezone-aware datetime convention; migration must apply and downgrade cleanly.

## Architecture
`deleted_at` mirrors the existing `created_at` field (`datetime(timezone=True)`, nullable) already present on both tables. It is added only to the DB table models (`User`, `Item`), NOT to the `*Public` response schemas, so it is never exposed via the API. The `get_datetime_utc()` helper already defined in `models.py` is reused when setting the value in Phase 2.

## Related Code Files
- Modify: `backend/app/models.py`
- Create: `backend/app/alembic/versions/<rev>_add_deleted_at_soft_delete.py`

## Implementation Steps
1. In `backend/app/models.py`, add to the `User` table model (class `User(UserBase, table=True)`):
   ```python
   deleted_at: datetime | None = Field(default=None, nullable=True, index=True)
   ```
2. Add the same field to the `Item` table model (class `Item(ItemBase, table=True)`).
3. Do **not** add `deleted_at` to `UserPublic` / `ItemPublic` (keep it internal).
4. Generate the migration against a running DB:
   ```bash
   cd backend && alembic revision --autogenerate -m "add deleted_at soft delete"
   ```
   If autogenerate is not practical in this environment, hand-write it following `fe56fa70289e_add_created_at_to_user_and_item.py`:
   ```python
   def upgrade():
       op.add_column('item', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
       op.add_column('user', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
       op.create_index(op.f('ix_item_deleted_at'), 'item', ['deleted_at'])
       op.create_index(op.f('ix_user_deleted_at'), 'user', ['deleted_at'])

   def downgrade():
       op.drop_index(op.f('ix_user_deleted_at'), table_name='user')
       op.drop_index(op.f('ix_item_deleted_at'), table_name='item')
       op.drop_column('user', 'deleted_at')
       op.drop_column('item', 'deleted_at')
   ```
   Set `down_revision = 'fe56fa70289e'` (current head).
5. Verify: `cd backend && alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head`.

## Success Criteria
- [ ] `User` and `Item` table models have `deleted_at: datetime | None` (indexed).
- [ ] `*Public` schemas unchanged (field not leaked).
- [ ] Migration file references `down_revision = 'fe56fa70289e'` and adds both columns + indexes.
- [ ] `alembic upgrade head` / `downgrade -1` both succeed.

## Risk Assessment
- **Wrong down_revision chain** → migration won't apply. Mitigation: confirm current head (`fe56fa70289e`) before setting `down_revision`.
- **Index on nullable column** is cheap and speeds up the "exclude deleted" filter used everywhere in Phase 2; low risk.
