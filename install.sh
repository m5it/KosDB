#!/bin/bash
# KosDB Master Installation Script
# Uses system leveldb (with RTTI) for plyvel compatibility

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KOSDB_VERSION="2.3.0"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default paths
INSTALL_PREFIX="${INSTALL_PREFIX:-/usr/local}"
WORK_DIR="${WORK_DIR:-$SCRIPT_DIR/.deps}"

echo "=========================================="
echo "KosDB Installation Script"
echo "=========================================="
echo "Version: $KOSDB_VERSION"
echo ""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --prefix)
            INSTALL_PREFIX="$2"
            shift 2
            ;;
        --work-dir)
            WORK_DIR="$2"
            shift 2
            ;;
        --skip-leveldb)
            SKIP_LEVELDB=1
            shift
            ;;
        --skip-plyvel)
            SKIP_PLYVEL=1
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --prefix PATH      Installation prefix (default: /usr/local)"
            echo "  --work-dir PATH    Working directory for clones (default: .deps)"
            echo "  --skip-leveldb     Skip system leveldb check/install"
            echo "  --skip-plyvel      Skip Plyvel build (if already installed)"
            echo "  --help             Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"

if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is required${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is required${NC}"
    exit 1
fi

# Check for virtual environment
if [[ -z "${VIRTUAL_ENV}" && -z "${CONDA_DEFAULT_ENV}" ]]; then
    echo -e "${YELLOW}⚠ Not in a virtual environment${NC}"
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
    source "$SCRIPT_DIR/venv/bin/activate"
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
fi

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Step 1: Ensure system LevelDB is installed
if [[ -z "$SKIP_LEVELDB" ]]; then
    echo ""
    echo -e "${BLUE}Step 1/3: Ensuring system LevelDB is installed...${NC}"
    
    if [[ "$EUID" -eq 0 ]]; then
        apt-get update && apt-get install -y libleveldb-dev || true
    elif command -v apt-get &> /dev/null; then
        echo -e "${YELLOW}⚠ apt-get available but not running as root${NC}"
        echo "Please run manually if leveldb is missing:"
        echo "  sudo apt-get install libleveldb-dev"
    fi
    
    # Verify system leveldb is usable
    if [[ ! -f "/usr/include/leveldb/db.h" && ! -f "/usr/local/include/leveldb/db.h" ]]; then
        echo -e "${RED}Error: leveldb headers not found${NC}"
        echo "Install with: sudo apt-get install libleveldb-dev"
        exit 1
    fi
    
    echo -e "${GREEN}✓ System LevelDB available${NC}"
else
    echo -e "${YELLOW}Skipping LevelDB check (--skip-leveldb)${NC}"
fi

# Step 2: Install Plyvel
if [[ -z "$SKIP_PLYVEL" ]]; then
    echo ""
    echo -e "${BLUE}Step 2/3: Installing Plyvel...${NC}"
    
    if [ -d "plyvel_for_KosDB" ]; then
        echo "Updating existing plyvel_for_KosDB..."
        cd plyvel_for_KosDB && git pull && cd ..
    else
        echo "Cloning plyvel_for_KosDB..."
        git clone https://github.com/m5it/plyvel_for_KosDB.git
    fi
    
    cd plyvel_for_KosDB
    
    echo "Installing Cython (required to generate plyvel C++ source)..."
    pip install cython
    
    echo "Generating plyvel C++ source from Cython..."
    cython --cplus plyvel/_plyvel.pyx
    
    echo "Building and installing Plyvel against system leveldb..."
    rm -rf build
    python setup.py build_ext --inplace
    pip install --no-build-isolation --force-reinstall .
    
    cd ..
    
    echo -e "${GREEN}✓ Plyvel installed${NC}"
else
    echo -e "${YELLOW}Skipping Plyvel build (--skip-plyvel)${NC}"
fi

# Step 3: Install KosDB
echo ""
echo -e "${BLUE}Step 3/3: Installing KosDB...${NC}"

cd "$SCRIPT_DIR"
echo "Installing KosDB dependencies..."
pip install -r requirements.txt

echo "Installing KosDB..."
pip install -e .

# Create data directory
mkdir -p data

# Create sample config if doesn't exist
if [ ! -f "config.json" ]; then
    echo "Creating sample configuration..."
    cat > config.json <<EOF
{
    "server": {
        "host": "0.0.0.0",
        "port": 5555,
        "data_dir": "./data"
    },
    "tls": {
        "enabled": false,
        "cert_file": "server.crt",
        "key_file": "server.key"
    },
    "logging": {
        "level": "INFO",
        "file": "kosdb.log"
    }
}
EOF
fi

echo -e "${GREEN}✓ KosDB installed${NC}"

# Verification
echo ""
echo -e "${BLUE}Verifying installation...${NC}"

python3 -c "
import sys
try:
    import plyvel
    print(f'✓ Plyvel {plyvel.__version__}')
except ImportError as e:
    print(f'✗ Plyvel import failed: {e}')
    sys.exit(1)

try:
    import database
    print('✓ KosDB database module')
except ImportError as e:
    print(f'✗ KosDB import failed: {e}')
    sys.exit(1)

print('✓ All imports successful')
"

echo ""
echo "=========================================="
echo -e "${GREEN}✓ KosDB installation complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Review configuration: nano config.json"
echo "  2. Create admin user:"
echo "     python server.py --prepare-admin admin --prepare-password yourpassword"
echo "  3. Start server:"
echo "     python server.py"
echo ""
echo "Or use the virtual environment:"
echo "  source venv/bin/activate"
echo "  python server.py"
