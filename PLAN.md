# Plan: Fix INSERT Regex to Support Column Lists
## ID: 1784437924.8390417
## Created: 2026-07-19 05:12:04
## Status: in_progress

### Goal:
The KosDB INSERT regex currently only supports `INSERT INTO table VALUES (...)` syntax. We need to extend it to also support `INSERT INTO table (col1, col2, ...) VALUES (...)` syntax that includes an optional column list before VALUES. This is needed because the admin API sends INSERT statements with explicit column lists like `INSERT INTO settings (setting_key, value, type) VALUES (...)`.

The fix involves:
1. Finding the INSERT regex pattern in the parser
2. Modifying it to optionally capture column list in parentheses
3. Updating the INSERT command handler to use column list when provided
4. Testing the new syntax works correctly

### Tasks (4):
1. [pending] Find INSERT regex pattern in parser
   ID: 1784437927.3966959

2. [pending] Modify INSERT regex to support optional column list
   ID: 1784437929.7024953

3. [pending] Update InsertCommand to handle column list
   ID: 1784437931.5895953

4. [pending] Test INSERT with column list syntax
   ID: 1784437933.5303857

---

