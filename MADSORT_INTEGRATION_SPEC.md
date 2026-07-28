# madS0rt Integration Specification for KosDB

## Overview

This document defines the technical specification for integrating **madS0rt** into **KosDB** as a pluggable high-performance sort engine.

The integration targets the query execution layer first (KosDB Python code), with optional future deep integration in storage internals.

## Goals

1. Add a pluggable sort abstraction in KosDB.
2. Support three sort backends:
   - `builtin` (Python default)
   - `madsort_py` (Python madS0rt)
   - `madsort_rust` (Rust implementation with Python bindings)
3. Introduce deterministic fallback behavior when optional engines are unavailable.
4. Improve ORDER BY / ranking performance while preserving result correctness.
5. Enable incremental rollout with configuration flags and benchmark gating.

## Non-Goals (Phase 1)

1. Modifying LevelDB internal comparator or compaction sort mechanics.
2. Replacing all specialized feature-local ordering implementations at once.
3. Introducing query semantics changes.

## Current Ecosystem Context

### Repositories

- `m5it/KosDB` — primary integration point.
- `m5it/madS0rt` — Python algorithm reference/fallback.
- `m5it/madS0rt-rust` — preferred performance backend.
- `m5it/plyvel_for_KosDB` — Python binding layer for LevelDB access.
- `m5it/leveldb_for_KosDB` — storage engine customization.

### Relevant KosDB Modules (initial reconnaissance)

- `database.py`
- `commands.py`
- `query_optimizer.py`
- `streaming_results.py`
- `config_validator.py`
- `config*.json`
- `tests/`, `test_integration/`, `benchmarks/`

## Architecture

## Sort Engine Abstraction

Create a unified interface used by query execution:

- `sort(values, key=None, reverse=False, stable=True, topk=None)`

### Backend Implementations

1. **Builtin backend**
   - Uses Python sorting.
   - Always available.

2. **madS0rt Python backend**
   - Uses `madS0rt` Python package.
   - Optional.

3. **madS0rt Rust backend**
   - Uses `madS0rt-rust` Python bindings.
   - Optional.
   - Preferred when installed and compatible.

### Engine Selection Modes

Config key: `sort_engine`

Allowed values:
- `auto` (default)
- `builtin`
- `madsort_py`
- `madsort_rust`

`auto` behavior:
1. Try rust backend.
2. Fallback to python backend.
3. Fallback to builtin.

## Proposed File Additions (KosDB)

- `sort_engine.py` (factory, detection, selection)
- `sort_backends/__init__.py`
- `sort_backends/builtin.py`
- `sort_backends/madsort_py.py`
- `sort_backends/madsort_rust.py`

## Proposed File Changes (KosDB)

1. `database.py`
   - Inject sort engine at initialization.
   - Expose helper for query execution pipeline.

2. `commands.py`
   - Route ORDER BY / explicit sort operations through sort abstraction.

3. `query_optimizer.py`
   - Add heuristic guardrails:
     - `sort_min_rows_for_accel` threshold
     - type-aware fast path eligibility

4. `streaming_results.py`
   - Add optional top-K strategy for `ORDER BY ... LIMIT N`.

5. `config_validator.py`
   - Validate `sort_engine` and numeric thresholds.

6. `config.json.sample` (+ environment/development/production configs)
   - Add new sorting configuration keys.

## Configuration Specification

New keys:

- `sort_engine`: string, enum `[auto, builtin, madsort_py, madsort_rust]`, default `auto`
- `sort_min_rows_for_accel`: integer, default `2000`
- `sort_enable_topk`: boolean, default `true`
- `sort_max_memory_mb`: integer (optional safety guard), default implementation-defined

Optional env overrides:

- `KOSDB_SORT_ENGINE`
- `KOSDB_SORT_MIN_ROWS_FOR_ACCEL`
- `KOSDB_SORT_ENABLE_TOPK`

## Correctness Requirements

All backends must preserve:

1. Exact row identity and count.
2. Deterministic ordering semantics equivalent to baseline behavior.
3. Stable sort behavior when required by existing query semantics.
4. Consistent handling of:
   - `None`/NULL-like values
   - NaN
   - mixed scalar types (must fail or normalize consistently with baseline)

## Fallback and Error Handling

1. If configured engine is unavailable, log warning and fallback unless strict mode is later introduced.
2. Any runtime backend exception during sort must fallback to builtin for that operation and emit structured diagnostic logs.
3. Avoid process crash due to optional backend import/runtime failures.

## Performance Plan

## Benchmarks

Add/extend benchmark suite to include:

Data shapes:
- random
- nearly sorted
- reverse sorted
- high duplication
- skewed distribution

Sizes:
- 1e3, 1e4, 1e5, 1e6

Metrics:
- latency p50/p95
- throughput
- memory usage
- CPU usage

Workloads:
- full ORDER BY
- ORDER BY with LIMIT (top-K candidate)

## Promotion Gate

Set `madsort_rust` as production-preferred only after:

1. correctness parity test pass
2. no regression in edge-case sorting semantics
3. measurable performance gain in representative workloads

## Testing Strategy

### Unit Tests

1. Backend factory selection tests.
2. Backend availability/fallback tests.
3. Sort semantic parity tests against builtin baseline.
4. Edge case tests for null/NaN/mixed types.

### Integration Tests

1. SQL-like ORDER BY result parity across engines.
2. ORDER BY + LIMIT top-K parity.
3. Feature interaction tests (cache, prepared statements, streaming).

### Reliability Tests

1. Fault-injection: import failure in optional backend.
2. Runtime exception in backend call.
3. Concurrency sanity checks in threaded request handling path.

## Rollout Plan

### Phase 1

- Add abstraction and builtin backend.
- Wire ORDER BY through abstraction.
- Hidden behind `sort_engine` config.

### Phase 2

- Add `madsort_py` and `madsort_rust` adapters.
- Add fallback logging and telemetry.

### Phase 3

- Add top-K optimization path.
- Introduce adaptive heuristics in optimizer.

### Phase 4

- Evaluate deeper integration points and optional storage-adjacent optimizations.

## Observability

Add structured logs/metrics:

- selected backend
- fallback count
- per-sort duration
- rows sorted
- top-K usage count

Expose in existing monitoring pathway if present.

## Compatibility and Packaging

1. Keep madS0rt backends optional dependencies.
2. Ensure installation docs include backend-specific setup.
3. Validate platform support for rust bindings.

## Risks and Mitigations

1. **Semantic drift across backends**
   - Mitigation: strict parity test suite and golden outputs.

2. **Packaging friction for rust backend**
   - Mitigation: optional dependency model + clear install docs + fallback.

3. **Unexpected regressions under small datasets**
   - Mitigation: threshold-based optimizer gating.

4. **Threading/concurrency behavior differences**
   - Mitigation: stress tests in threaded server mode.

## Open Questions

1. Exact current ORDER BY execution hotspots in `commands.py` / `database.py`.
2. Canonical null/NaN ordering policy expected by existing tests.
3. Whether strict mode is desired when explicitly choosing unavailable backends.
4. Whether top-K should be forced only when LIMIT is below configurable ceiling.

## Immediate Next Actions

1. Perform line-level deep scan for exact function insertion points.
2. Draft PR-1 implementation with abstraction + builtin backend + wiring.
3. Add parity tests before enabling optional engines.
4. Add benchmark baseline snapshot in repository docs.

---

Owner: KosDB engineering
Status: Draft v1
Date: 2026-07-28
