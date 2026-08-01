# KosDB Fix Plan (Phases 1-2)

Scope agreed: critical bugs + data integrity. NOT in scope: repo hygiene (dead scripts,
committed logs, :memory:/ cleanup, packaging, CI), password hashing changes, recv framing.

## Phase 1 — Critical bugs

1. **Restore `create_table` in database.py**
   - `use_database` returns at line 343; lines 345-389 are the orphaned body of
     `create_table` (unreachable, references undefined vars). No `def create_table`
     exists anywhere, but commands.py calls it -> every CREATE TABLE fails.
   - Fix: re-add `def create_table(self, table_name, columns)` with guards
     (no db selected, table already exists) wrapping the orphaned body.

2. **Fix UPSERT / BATCH UPDATE in commands.py**
   - commands.py:305, 385 call `self.db._get_schema(table)` which doesn't exist.
   - commands.py:284, 290, 350 call `.split(',')` on values parser.py already
     converted to lists/dict.
   - Fix: add a `get_schema()` helper on Database (or read `_schema:` key directly);
     consume parser output as lists/dict.

3. **Remove `_cleanup_stale_locks`** (database.py:87-94)
   - `os.remove` on Linux succeeds even on flock'd LOCK files -> two processes can
     open the same LevelDB -> corruption. Delete the method and its call site.

4. **Fix server.py**
   - TLS: accepted sockets are wrapped with `wrap_client_socket` (client-side
     context, no server_side=True) -> handshake cannot work. Wrap with the
     server-side context instead.
   - Remove duplicated import block (lines 33-50), dead truncated first `main()`
     (351-355), duplicate `if __name__ == '__main__'` (400-401) that restarts the
     server after Ctrl+C.

5. **Fix binlog shutdown in database.py**
   - `self._binlog_queue.join(timeout=5)` is a TypeError (join takes no args),
     swallowed by bare except; worker thread never joined; close() can close the
     binlog DB mid-write.
   - Fix: enqueue None sentinel, `thread.join(timeout=5)`, worker calls
     `task_done()` in finally, close binlog DB only after thread exits.

## Phase 2 — Data integrity

6. **Index maintenance on UPDATE/DELETE** (database.py)
   - delete(): remove row's entries from every `_index:{table}:{col}` map.
   - update(): for changed indexed columns, remove old-value entry, add new-value entry.

7. **Apply WHERE in index SELECT path** (database.py:701-715)
   - `SELECT ... WHERE x=1 ORDER BY indexed_col` currently returns ALL rows when
     the order-by index exists. Apply the same predicate filter as fallback branch.

8. **PK correctness on insert** (database.py:442-449)
   - Reject duplicate primary keys instead of silently overwriting.
   - Fix next_id counter so PK-table rows stop all getting id="1".

9. **Lock read-modify-write counters**
   - Guard `next_id`, `_get_next_user_id`, `_get_next_privilege_id`,
     `Binlog._current_position` with locks.
   - Make binlog entry+position a single write_batch (binlog.py:75-77).

10. **Transaction/binlog ordering + txn index visibility**
    - Buffer binlog entries during active transaction; enqueue on commit, drop on
      rollback (replicas currently diverge on rollback).
    - `_update_indexes` must read pending index state from `_transaction_changes`
      so multi-insert transactions don't lose index entries (database.py:516-525).

## Verification

- `pytest tests/ -q` plus root `test_writebatch.py`, `test_upsert.py`,
  `test_batch_update.py`.
- Smoke test: LOGIN -> CREATE TABLE -> INSERT -> UPSERT -> SELECT (indexed WHERE)
  -> UPDATE -> DELETE -> verify index consistency.
