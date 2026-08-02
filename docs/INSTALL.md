# KosDB Installation Guide

Complete installation guide for KosDB and its dependencies.

## Overview

KosDB uses the **system LevelDB** library (`libleveldb-dev`) for compatibility
with plyvel. The custom `leveldb_for_KosDB` fork is no longer required for the
standard installation because the system library is built with RTTI, which plyvel
needs.

Components installed:

1. **System LevelDB** - via `apt-get install libleveldb-dev`
2. **plyvel_for_KosDB** - Python bindings for LevelDB  
3. **KosDB** - Main database server application

## Quick Start (Automated)

For automated installation of all components:

```bash
# Clone KosDB
git clone https://github.com/m5it/KosDB.git
cd KosDB

# Run master installation script
./install.sh
```

This will:
- Ensure system LevelDB development headers are installed
- Install plyvel_for_KosDB (using Cython to generate its C++ source)
- Set up KosDB with virtual environment
- Verify installation

## Manual Installation

### Step 1: Install System LevelDB

```bash
sudo apt-get update
sudo apt-get install libleveldb-dev
```

The system LevelDB provides `/usr/include/leveldb/` headers and
`/usr/lib/x86_64-linux-gnu/libleveldb.so`, which plyvel links against.

### Step 1a (Optional): Custom LevelDB Build

If you prefer to build LevelDB from source, use the upstream repository or the
`leveldb_for_KosDB` fork. Note that the fork builds with `-fno-rtti` by default,
which is incompatible with plyvel's comparator subclass. In that case, rebuild
LevelDB with RTTI enabled or use the system library instead.

```bash
# Clone KosDB
git clone https://github.com/m5it/KosDB.git
cd KosDB

# Run master installation script
./install.sh
```

This will:
- Clone and build leveldb_for_KosDB
- Install plyvel_for_KosDB
- Set up KosDB with virtual environment
- Verify installation

## Manual Installation

### Step 1: Install LevelDB

```bash
# Clone repository
git clone https://github.com/m5it/leveldb_for_KosDB.git
cd leveldb_for_KosDB

# Build and install
./build.sh

# Verify installation
./verify_install.sh
```

**Requirements:**
- CMake >= 3.10
- GCC/G++ >= 7.0 or Clang >= 6.0
- Optional: libsnappy-dev (for compression)

**Platform-specific prerequisites:**

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y cmake g++ libsnappy-dev
```

**CentOS/RHEL/Fedora:**
```bash
sudo yum install -y cmake gcc-c++ snappy-devel
# or: sudo dnf install -y cmake gcc-c++ snappy-devel
```

**macOS:**
```bash
brew install cmake snappy
```

### Step 2: Install Plyvel

```bash
# Clone repository
git clone https://github.com/m5it/plyvel_for_KosDB.git
cd plyvel_for_KosDB

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install
./install.sh

# Verify installation
./verify_install.sh
```

**Requirements:**
- Python 3.7+
- LevelDB installed (Step 1)
- Cython >= 0.29

### Step 3: Install KosDB

```bash
# Clone repository
git clone https://github.com/m5it/KosDB.git
cd KosDB

# Use virtual environment from plyvel step
source ../plyvel_for_KosDB/venv/bin/activate

# Or create new one
python3 -m venv venv
source venv/bin/activate

# Install KosDB
pip install -r requirements.txt
pip install -e .

# Verify installation
python verify_installation.py
```

## Configuration

### Create Configuration File

```bash
cp config.json.sample config.json
```

Edit `config.json` to match your requirements:

```json
{
    "server": {
        "host": "0.0.0.0",
        "port": 5555,
        "data_dir": "./data"
    },
    "tls": {
        "enabled": true,
        "cert_file": "server.crt",
        "key_file": "server.key"
    }
}
```

### Create Admin User

```bash
python server.py --prepare-admin admin --prepare-password yourpassword
```

## Starting KosDB

### Development Mode

```bash
source venv/bin/activate
python server.py
```

### Production Mode

```bash
source venv/bin/activate
python server.py --host 0.0.0.0 --port 5555
```

### With TLS

```bash
# Generate self-signed certificate (for testing)
openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt -days 365 -nodes

# Start with TLS
python server.py --tls-cert server.crt --tls-key server.key
```

## Verification

Test the installation:

```bash
# Run verification script
python verify_installation.py

# Expected output:
# ✓ LevelDB library found
# ✓ Plyvel X.X.X imported
# ✓ KosDB modules loaded
# ✓ Performance test passed
```

## Docker Installation (Optional)

```dockerfile
FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    cmake g++ libsnappy-dev \
    git

WORKDIR /opt/kosdb

# Clone and install all components
RUN git clone https://github.com/m5it/leveldb_for_KosDB.git && \
    cd leveldb_for_KosDB && ./build.sh && cd .. && \
    git clone https://github.com/m5it/plyvel_for_KosDB.git && \
    cd plyvel_for_KosDB && ./install.sh && cd .. && \
    git clone https://github.com/m5it/KosDB.git && \
    cd KosDB && pip install -r requirements.txt

WORKDIR /opt/kosdb/KosDB
EXPOSE 5555

CMD ["python", "server.py"]
```

## Troubleshooting

### "leveldb/db.h not found"

LevelDB is not installed or headers are missing.

**Solution:**
```bash
# Reinstall LevelDB
cd leveldb_for_KosDB
./build.sh
sudo ldconfig
```

### "ImportError: No module named 'plyvel'"

Plyvel is not installed or not in Python path.

**Solution:**
```bash
cd plyvel_for_KosDB
source venv/bin/activate
./install.sh
```

### "Permission denied" during LevelDB install

**Solution:**
```bash
# Install to user directory
./build.sh --prefix $HOME/.local
export PKG_CONFIG_PATH=$HOME/.local/lib/pkgconfig:$PKG_CONFIG_PATH
```

### "undefined symbol: leveldb" when importing plyvel

LevelDB library not found at runtime.

**Solution:**
```bash
# Update library cache
sudo ldconfig

# Or set LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
```

### Slow performance

Check LevelDB tuning options in KosDB:

```python
from database import Database

db = Database(
    "data",
    cache_size=64*1024*1024,      # Increase cache
    write_buffer_size=16*1024*1024,  # Increase buffer
    bloom_filter_bits=10
)
```

## Platform-Specific Notes

### Linux (Ubuntu/Debian/CentOS)

All features supported. Use package manager for prerequisites.

### macOS

Works with Homebrew. Note: Some performance optimizations may differ.

### Windows

Not officially supported. Consider WSL2 for Windows development.

## Performance Tuning

See [LEVELDB_TUNING.md](LEVELDB_TUNING.md) for detailed tuning options.

## Upgrading

### Upgrade LevelDB

```bash
cd leveldb_for_KosDB
git pull
./build.sh
```

### Upgrade Plyvel

```bash
cd plyvel_for_KosDB
git pull
./install.sh
```

### Upgrade KosDB

```bash
cd KosDB
git pull
pip install -e .
```

## Support

- **Issues:** https://github.com/m5it/KosDB/issues
- **Documentation:** See README.md and LEVELDB_TUNING.md
- **Performance:** See KOSDB_PERFORMANCE.md

## License

- KosDB: MIT License
- Plyvel: BSD License
- LevelDB: BSD 3-Clause License
