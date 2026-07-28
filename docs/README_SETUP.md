# KosDB Quick Setup

## One-Command Installation

```bash
curl -fsSL https://raw.githubusercontent.com/m5it/KosDB/main/setup.sh | bash
```

Or manually:

```bash
git clone https://github.com/m5it/KosDB.git
cd KosDB
./setup.sh
```

## What This Does

The `setup.sh` script automatically:

1. ✅ Checks prerequisites (git, cmake, g++, python3)
2. ✅ Creates Python virtual environment
3. ✅ Clones leveldb_for_KosDB and builds it
4. ✅ Installs plyvel_for_KosDB
5. ✅ Installs KosDB with all dependencies
6. ✅ Runs verification tests
7. ✅ Optionally creates admin user

## Options

```bash
# Skip virtual environment (use system Python)
./setup.sh --no-venv

# Skip tests (faster install)
./setup.sh --skip-tests

# Combined
./setup.sh --no-venv --skip-tests
```

## After Installation

```bash
# Start server
source venv/bin/activate
python server.py

# Or with options
python server.py --host 0.0.0.0 --port 5555
```

## Manual Installation

If you prefer manual control, see [INSTALL.md](INSTALL.md) for step-by-step instructions.

## Troubleshooting

See [INSTALL.md](INSTALL.md#troubleshooting) for common issues and solutions.
