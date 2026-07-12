
# Error Handling Plan for KosDB Server

## Current Issues Identified

### 1. Database Lock Issues
**Error**: `plyvel._plyvel.IOError: b'IO error: lock ./data/_system/LOCK: Resource temporarily unavailable'`

**Root Causes**:
- Previous server instance didn't shut down cleanly
- Another process is still holding the database lock
- Zombie processes from previous runs

**Solutions**:
```bash
# Check for existing processes
ps aux | grep "python3 server.py"

# Kill existing processes
pkill -f "python3 server.py"

# Remove stale lock files
rm -f ./data/_system/LOCK
rm -f ./data/*.LOCK

# Verify no processes are using the port
lsof -i :5555
```

**Prevention**:
- Implement graceful shutdown handler
- Add startup check for existing locks
- Create cleanup script

### 2. Import Errors
**Pattern**: `NameError: name 'X' is not defined`

**Root Causes**:
- Missing imports at top of files
- Circular imports
- Import order issues

**Solutions**:
- Standardize import section at top of each file
- Use `__all__` to define exports
- Add import validation tests

### 3. Syntax Errors
**Pattern**: `SyntaxError: unmatched '}'` or `IndentationError`

**Root Causes**:
- Corrupted files from multiple edits
- Merge conflicts
- Incomplete refactoring

**Solutions**:
- Rewrite entire files when corrupted
- Use version control
- Validate syntax before running

## Systematic Recovery Plan

### Step 1: Environment Cleanup
```bash
#!/bin/bash
# cleanup.sh - Run before starting server

echo "Cleaning up environment..."

# Kill existing Python processes
pkill -9 -f "python3 server.py" 2>/dev/null

# Wait for processes to die
sleep 2

# Remove lock files
find ./data -name "*.LOCK" -type f -delete 2>/dev/null

# Check port availability
if lsof -Pi :5555 -sTCP:LISTEN -t >/dev/null ; then
    echo "Port 5555 is still in use!"
    exit 1
fi

echo "Cleanup complete"
```

### Step 2: File Integrity Check
```bash
#!/bin/bash
# verify_files.sh

files=(
    "server.py"
    "parser.py"
    "commands.py"
    "database.py"
    "auth.py"
)

for file in "${files[@]}"; do
    echo "Checking $file..."
    python3 -m py_compile "$file"
    if [ $? -ne 0 ]; then
        echo "SYNTAX ERROR in $file"
        exit 1
    fi
done

echo "All files valid"
```

### Step 3: Dependency Check
```bash
#!/bin/bash
# check_deps.sh

python3 -c "import plyvel" 2>/dev/null || {
    echo "ERROR: plyvel not installed"
    echo "Run: pip install plyvel"
    exit 1
}

python3 -c "import bcrypt" 2>/dev/null || {
    echo "WARNING: bcrypt not installed (needed for auth)"
}

echo "Dependencies OK"
```

### Step 4: Startup Sequence
```bash
#!/bin/bash
# start_server.sh

# 1. Cleanup
./cleanup.sh || exit 1

# 2. Verify files
./verify_files.sh || exit 1

# 3. Check deps
./check_deps.sh || exit 1

# 4. Prepare admin if needed
if [ ! -d "./data/_system" ]; then
    echo "Initializing database..."
    python3 server.py --prepare_admin admin --prepare_password admin123
fi

# 5. Start server
echo "Starting server..."
python3 server.py --port 5555
```

## Error Prevention Checklist

### Before Running Server
- [ ] Check no existing Python processes
- [ ] Verify port is available
- [ ] Remove stale lock files
- [ ] Validate Python syntax
- [ ] Check all imports are present

### File Maintenance
- [ ] Keep imports at top of files
- [ ] Use consistent import ordering
- [ ] Validate syntax after edits
- [ ] Test imports after changes

### Development Workflow
- [ ] Make backup before major changes
- [ ] Test syntax after each edit
- [ ] Use version control
- [ ] Document changes

## Common Error Patterns & Fixes

### Pattern 1: Import Missing
```python
# ERROR
NameError: name 'argparse' is not defined

# FIX
Add at top: import argparse
```

### Pattern 2: Database Locked
```bash
# ERROR
IOError: lock ./data/_system/LOCK: Resource temporarily unavailable

# FIX
pkill -f "python3 server.py"
rm -f ./data/_system/LOCK
```

### Pattern 3: Syntax Error
```bash
# ERROR
SyntaxError: unmatched '}'

# FIX
python3 -m py_compile file.py  # Check syntax
# Or rewrite file from scratch
```

### Pattern 4: Port in Use
```bash
# ERROR
OSError: [Errno 98] Address already in use

# FIX
lsof -i :5555  # Find process
kill -9 <PID>  # Kill process
# Or use different port
```

## Recovery Scripts

### Quick Reset
```bash
#!/bin/bash
# reset_and_start.sh

echo "=== KosDB Server Reset ==="

# Stop any running server
pkill -9 -f "python3 server.py" 2>/dev/null
sleep 1

# Clear data (optional - for fresh start)
read -p "Clear all data? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf ./data
    echo "Data cleared"
fi

# Remove locks
find . -name "*.LOCK" -type f -delete 2>/dev/null

# Verify
echo "Checking environment..."
python3 -c "import plyvel; print('plyvel OK')"
python3 -m py_compile server.py && echo "server.py OK"
python3 -m py_compile parser.py && echo "parser.py OK"
python3 -m py_compile commands.py && echo "commands.py OK"

# Start
echo "Starting server..."
python3 server.py --port 5555
```

## Testing Strategy

### Pre-Flight Checks
1. Syntax validation
2. Import validation
3. Port availability
4. Database lock status
5. Dependency check

### Smoke Tests
```bash
# Test 1: Can we parse commands?
python3 -c "from parser import BackupRestoreParser; p = BackupRestoreParser(); print('Parser OK')"

# Test 2: Can we load commands?
python3 -c "from commands import CommandRegistry; print('Commands OK')"

# Test 3: Can we create database?
python3 -c "from database import Database; import tempfile; import shutil; d = tempfile.mkdtemp(); db = Database(d); shutil.rmtree(d); print('Database OK')"

# Test 4: Server starts?
timeout 5 python3 server.py --port 5555 &
sleep 2
curl -s http://localhost:5555 || echo "Server started"
pkill -f "python3 server.py"
```

## Monitoring & Logging

### Add to server.py
```python
import logging

# At startup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),
        logging.StreamHandler()
    ]
)

# Log all errors
try:
    # server code
except Exception as e:
    logging.exception("Server error")
    raise
```

## Emergency Procedures

### If Server Won't Start
1. Check logs: `tail -f server.log`
2. Check processes: `ps aux | grep python`
3. Check ports: `netstat -tlnp | grep 5555`
4. Check locks: `find ./data -name "*.LOCK"`
5. Try fresh data dir: `mv data data.backup`

### If Files Are Corrupted
1. Check git status: `git status`
2. Restore from git: `git checkout -- file.py`
3. Or restore from backup
4. Validate syntax: `python3 -m py_compile file.py`

### Complete Reset
```bash
# Nuclear option - complete reset
pkill -9 -f python
rm -rf data
rm -f *.log
rm -f *.LOCK
git checkout -- .
python3 server.py --port 5555
```
