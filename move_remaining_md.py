#!/usr/bin/env python3
"""Move remaining .md files to docs or specs"""

import os
import shutil

# Ensure directories exist
os.makedirs('docs', exist_ok=True)
os.makedirs('specs', exist_ok=True)

# Define where each .md file should go
# docs = user-facing documentation
# specs = technical specs, plans, reports

docs_files = [
    'README.md',
    'INSTALL.md',
    'README_SETUP.md',
    'CONFIGURATION.md',
    'OPERATIONS.md',
    'TESTING.md',
    'CHANGELOG.md',
    'HISTORY.md',
    'MIGRATE.md',
    'LEVELDB_TUNING.md',
    'LOAD_TESTING.md',
    'KOSDB_PERFORMANCE.md',
    'KOSDB_ISSUES.md',
    'ACCEPTANCE_CRITERIA.md',
    'PLAN.md',
    'PROJECT.md',
    # Feature READMEs
    'CDC_README.md',
    'COMPRESSION_README.md',
    'CONNECTION_POOL_README.md',
    'CONNECTION_POOL_SIZING.md',
    'ERROR_HANDLING_PLAN.md',
    'GEOSPATIAL_README.md',
    'MV_README.md',
    'MULTITENANT_README.md',
    'PREPARED_STATEMENTS_README.md',
    'SECURITY_README.md',
    'TIMESERIES_README.md',
    'REPLICATION_BATCH.md',
    # Batch docs
    'BATCH_BACKUP.md',
    'BATCH_COMPRESSION.md',
    'BATCH_ERROR_HANDLING.md',
    'BATCH_GEOSPATIAL.md',
    'BATCH_MATERIALIZED_VIEWS.md',
    'BATCH_MIGRATION.md',
    'BATCH_MULTITENANT.md',
    'BATCH_QUERY_CACHE.md',
    'BATCH_SHARDING.md',
    'BATCH_TIMESERIES.md',
    'BATCH_TLS_BEST_PRACTICES.md',
    'BATCH_VECTOR_SEARCH.md',
    # Release docs
    'RELEASE_NOTES_v2.3.0.md',
    'GIT_TAG_NOTES_v2.3.0.md',
    'v2.3.0_RELEASE_CHECKLIST.md',
    # Command docs
    'COMMAND_SPLITTING.md',
    'TEST_COVERAGE_REPORT.md',
]

specs_files = [
    'MADSORT_INTEGRATION_SPEC.md',
]

def move_file(src, dst_folder):
    """Move file if it exists and isn't already there"""
    if not os.path.exists(src):
        return f"NOT_FOUND: {src}"
    
    dst = os.path.join(dst_folder, src)
    if os.path.exists(dst):
        return f"EXISTS: {src} already in {dst_folder}/"
    
    shutil.move(src, dst)
    return f"MOVED: {src} -> {dst_folder}/{src}"

# Move files
print("Moving documentation files to docs/")
docs_results = []
for f in docs_files:
    result = move_file(f, 'docs')
    docs_results.append(result)
    print(f"  {result}")

print("\nMoving specification files to specs/")
specs_results = []
for f in specs_files:
    result = move_file(f, 'specs')
    specs_results.append(result)
    print(f"  {result}")

# Summary
print("\n" + "="*60)
print("SUMMARY")
print("="*60)

moved_docs = sum(1 for r in docs_results if r.startswith("MOVED"))
exists_docs = sum(1 for r in docs_results if r.startswith("EXISTS"))
notfound_docs = sum(1 for r in docs_results if r.startswith("NOT_FOUND"))

moved_specs = sum(1 for r in specs_results if r.startswith("MOVED"))
exists_specs = sum(1 for r in specs_results if r.startswith("EXISTS"))
notfound_specs = sum(1 for r in specs_results if r.startswith("NOT_FOUND"))

print(f"\nDocs folder:")
print(f"  Moved: {moved_docs}")
print(f"  Already existed: {exists_docs}")
print(f"  Not found: {notfound_docs}")

print(f"\nSpecs folder:")
print(f"  Moved: {moved_specs}")
print(f"  Already existed: {exists_specs}")
print(f"  Not found: {notfound_specs}")

# List remaining .md files in root
print("\nRemaining .md files in root:")
remaining = [f for f in os.listdir('.') if f.endswith('.md') and os.path.isfile(f)]
for f in sorted(remaining):
    print(f"  - {f}")
