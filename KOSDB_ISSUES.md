# KosDB Issues — Affecting KosCMS Settings Persistence

These bugs were found while debugging why KosCMS admin/settings changes don't persist after page refresh.

## Bug 1: `use_database()` is thread-unsafe (CRITICAL)

**File:** `database.py:185-199`

The `Database` instance is shared across all `ClientHandler` threads on the server (`server.py:153` creates one instance, `server.py:196` passes it to every handler). The `use_database()` method closes and reopens the shared `self._db` handle without any locking:

```python
def use_database(self, db_name: str) -> str:
    # ...
    if self._db:
        self._db.close()          # <-- closes handle for ALL threads
    self._db = plyvel.DB(db_path, create_if_missing=True)  # <-- new handle
```

When KosCMS's connection pool (10 connections) sends `USE webcms` on every `acquire()`, concurrent calls close/reopen `_db` while other threads are mid-iteration, breaking iterators and causing silent data loss.

**Fix:**
1. Add an early return if already on the requested database:
```python
def use_database(self, db_name: str) -> str:
    if self._transaction_active:
        return "ERROR: Cannot switch database during transaction"
    if self.current_db == db_name and self._db:
        return f"Already using database '{db_name}'"  # <-- no-op
    # ... rest of existing logic
```

2. Add a `threading.Lock` around `use_database()`:
```python
# In __init__:
self._db_lock = threading.Lock()

# In use_database():
def use_database(self, db_name: str) -> str:
    with self._db_lock:
        # ... existing logic with the idempotent check above
```

---

## Bug 2: Single shared `Database` across all handler threads

**File:** `server.py:153` and `server.py:196`

One `Database` instance is created and passed to every `ClientHandler` thread. All handlers mutate the same `self._db`, `self._transaction_active`, and `self._transaction_changes` without synchronization.

**Fix (recommended):** Store per-handler database state. Each `ClientHandler` should have its own `_db` reference and `current_db` tracking. The `Database` class should be split into a connection-scoped state manager, or each handler should open its own `plyvel.DB` handle.

**Minimal fix:** At minimum, the lock from Bug 1's fix prevents the most critical race condition. A full per-connection state design is a longer-term improvement.

---

## Bug 3: `UpdateCommand` produces garbled response

**File:** `commands.py:170-171`

`Database.update()` returns a string like `"Updated 1 row(s) in 'settings'"`. `UpdateCommand` wraps it in an f-string:

```python
count = self.db.update(params['table'], params['set'], params.get('where'))
return f"OK: Updated {count} row(s)"
# Produces: "OK: Updated Updated 1 row(s) in 'settings' row(s)"
```

The client can't reliably parse the row count from this.

**Fix:**
```python
count = self.db.update(params['table'], params['set'], params.get('where'))
# count is actually a string, extract the number
import re
match = re.search(r'Updated (\d+) row', count)
num = int(match.group(1)) if match else 0
return f"OK: Updated {num} row(s)"
```

---

## Failure Chain (how these bugs cause KosCMS settings to not persist)

```
KosCMS pool acquire()
  -> sends "USE webcms"                          [kosdb_client.py:332]
    -> server: Database.use_database("webcms")   [database.py:185]
      -> self._db.close()                         [database.py:194-195]
      -> self._db = plyvel.DB(...)                [database.py:197]

Meanwhile, another thread doing SELECT * FROM settings:
  -> iterating self._db...                        [database.py:382]
  -> handle just got closed -> iterator broken -> empty result

get_settings() gets empty rows -> returns hardcoded defaults
User sees old values on refresh.
```

Bug 1's fix (idempotent `use_database` + lock) eliminates 99% of these occurrences since all KosCMS pool connections use the same database.

---

## Bug 4: INSERT doesn't support column list syntax

**Status:** FIXED — regex updated, `insert_with_columns` added.

**File:** `parser.py:23-25`

The INSERT regex only matches `INSERT INTO table VALUES (...)`:
```python
'INSERT': re.compile(
    r'^\s*INSERT\s+INTO\s+(?P<table>\w+)\s+VALUES\s*\((?P<values>[^)]+)\)\s*$',
    re.IGNORECASE
),
```

KosCMS sends `INSERT INTO settings (setting_key, value, type) VALUES (...)` which returns `ERROR: Unknown command`. This blocks all new settings saves.

**Fix:** Update the regex to optionally accept a column list:
```python
'INSERT': re.compile(
    r'^\s*INSERT\s+INTO\s+(?P<table>\w+)'
    r'(?:\s*\((?P<columns>\w[\w\s,]*)\))?'
    r'\s+VALUES\s*\((?P<values>[^)]+)\)\s*$',
    re.IGNORECASE
),
```

---

## Bug 5: `InsertCommand` double-splits columns list (REGRESSION)

**Status:** FIXED

**File:** `commands.py:147`

The parser (`parser.py:192`) already converts `columns` from a string to a list:
```python
if 'columns' in params and params['columns']:
    params['columns'] = [c.strip() for c in params['columns'].split(',')]
```

But `commands.py:147` tries to split it again:
```python
col_list = [c.strip() for c in columns.split(',')]  # <-- ERROR: 'list' has no attribute 'split'
```

**Fix:** Change line 147 to:
```python
col_list = columns  # parser.py already splits into a list
```

This causes `ERROR: 'list' object has no attribute 'split'` on every INSERT with column list, blocking all settings saves.
