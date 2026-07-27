#!/bin/bash
# KosDB Master Setup Script
# Clones, builds, and installs all three repositories in correct order

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KOSDB_VERSION="2.3.0"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
INSTALL_MODE="${INSTALL_MODE:-auto}"  # auto, manual, docker
SKIP_TESTS="${SKIP_TESTS:-0}"
USE_VIRTUAL_ENV="${USE_VIRTUAL_ENV:-1}"

# Repository URLs
LEVELDB_REPO="https://github.com/m5it/leveldb_for_KosDB.git"
PLYVEL_REPO="https://github.com/m5it/plyvel_for_KosDB.git"
KOSDB_REPO="https://github.com/m5it/KosDB.git"

print_header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    local missing=()
    
    # Check git
    if ! command -v git &> /dev/null; then
        missing+=("git")
    else
        print_success "git found: $(git --version | head -1)"
    fi
    
    # Check cmake
    if ! command -v cmake &> /dev/null; then
        missing+=("cmake")
    else
        print_success "cmake found: $(cmake --version | head -1)"
    fi
    
    # Check compiler
    if ! command -v g++ &> /dev/null && ! command -v clang++ &> /dev/null; then
        missing+=("g++ or clang++")
    else
        print_success "C++ compiler found"
    fi
    
    # Check python3
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    else
        print_success "python3 found: $(python3 --version)"
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        missing+=("pip3")
    else
        print_success "pip3 found"
    fi
    
    if [ ${#missing[@]} -ne 0 ]; then
        print_error "Missing prerequisites: ${missing[*]}"
        echo ""
        echo "Install with:"
        echo "  Ubuntu/Debian: sudo apt-get install -y git cmake g++ python3 python3-pip"
        echo "  CentOS/RHEL:   sudo yum install -y git cmake gcc-c++ python3 python3-pip"
        echo "  macOS:         brew install git cmake python3"
        exit 1
    fi
    
    print_success "All prerequisites satisfied"
}

setup_virtual_environment() {
    if [ "$USE_VIRTUAL_ENV" != "1" ]; then
        print_info "Skipping virtual environment (USE_VIRTUAL_ENV=0)"
        return 0
    fi
    
    print_header "Setting Up Virtual Environment"
    
    if [ -d "$SCRIPT_DIR/venv" ]; then
        print_warning "Virtual environment already exists"
        read -p "Recreate? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$SCRIPT_DIR/venv"
        fi
    fi
    
    if [ ! -d "$SCRIPT_DIR/venv" ]; then
        print_info "Creating virtual environment..."
        python3 -m venv "$SCRIPT_DIR/venv"
    fi
    
    source "$SCRIPT_DIR/venv/bin/activate"
    print_success "Virtual environment activated"
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
}

clone_repositories() {
    print_header "Cloning Repositories"
    
    mkdir -p "$SCRIPT_DIR/.deps"
    cd "$SCRIPT_DIR/.deps"
    
    # Clone LevelDB
    if [ -d "leveldb_for_KosDB" ]; then
        print_info "Updating leveldb_for_KosDB..."
        cd leveldb_for_KosDB && git pull && cd ..
    else
        print_info "Cloning leveldb_for_KosDB..."
        git clone "$LEVELDB_REPO"
    fi
    
    # Clone Plyvel
    if [ -d "plyvel_for_KosDB" ]; then
        print_info "Updating plyvel_for_KosDB..."
        cd plyvel_for_KosDB && git pull && cd ..
    else
        print_info "Cloning plyvel_for_KosDB..."
        git clone "$PLYVEL_REPO"
    fi
    
    # KosDB is already the current directory
    print_success "Repositories ready"
}

build_leveldb() {
    print_header "Building LevelDB"
    
    cd "$SCRIPT_DIR/.deps/leveldb_for_KosDB"
    
    if [ -f "build.sh" ]; then
        ./build.sh
    else
        # Fallback manual build
        mkdir -p build && cd build
        cmake -DCMAKE_BUILD_TYPE=Release ..
        make -j$(nproc 2>/dev/null || echo 4)
        sudo make install
        sudo ldconfig
    fi
    
    # Verify
    if [ -f "/usr/local/lib/libleveldb.a" ] || [ -f "/usr/lib/libleveldb.a" ]; then
        print_success "LevelDB built and installed"
    else
        print_error "LevelDB installation not found"
        exit 1
    fi
}

install_plyvel() {
    print_header "Installing Plyvel"
    
    cd "$SCRIPT_DIR/.deps/plyvel_for_KosDB"
    
    if [ -f "install.sh" ]; then
        ./install.sh
    else
        # Fallback manual install
        pip install Cython
        python setup.py build_ext --inplace
        pip install -e .
    fi
    
    # Verify
    python3 -c "import plyvel; print(f'Plyvel {plyvel.__version__}')" || {
        print_error "Plyvel installation failed"
        exit 1
    }
    
    print_success "Plyvel installed"
}

install_kosdb() {
    print_header "Installing KosDB"
    
    cd "$SCRIPT_DIR"
    
    # Install dependencies
    pip install -r requirements.txt
    
    # Install KosDB
    pip install -e .
    
    # Create data directory
    mkdir -p data
    
    # Create config if doesn't exist
    if [ ! -f "config.json" ]; then
        cp config.json.sample config.json
        print_info "Created config.json from sample"
    fi
    
    print_success "KosDB installed"
}

run_tests() {
    if [ "$SKIP_TESTS" = "1" ]; then
        print_info "Skipping tests (SKIP_TESTS=1)"
        return 0
    fi
    
    print_header "Running Tests"
    
    cd "$SCRIPT_DIR"
    
    # Run verification script
    if [ -f "verify_installation.py" ]; then
        python verify_installation.py || {
            print_warning "Some tests failed, but installation may still work"
        }
    else
        # Basic import test
        python3 -c "
import sys
try:
    import plyvel
    import database
    import server
    print('Basic imports successful')
    sys.exit(0)
except Exception as e:
    print(f'Import error: {e}')
    sys.exit(1)
" || {
            print_error "Basic import test failed"
            exit 1
        }
    fi
    
    print_success "Tests completed"
}

create_admin_user() {
    print_header "Create Admin User"
    
    read -p "Create admin user now? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        read -p "Username (default: admin): " username
        username=${username:-admin}
        
        read -s -p "Password: " password
        echo
        
        cd "$SCRIPT_DIR"
        python server.py --prepare-admin "$username" --prepare-password "$password"
        print_success "Admin user '$username' created"
    fi
}

print_summary() {
    print_header "Installation Complete"
    
    echo ""
    echo "KosDB v$KOSDB_VERSION has been successfully installed!"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Activate virtual environment (if used):"
    echo "   source $SCRIPT_DIR/venv/bin/activate"
    echo ""
    echo "2. Review configuration:"
    echo "   nano $SCRIPT_DIR/config.json"
    echo ""
    echo "3. Start the server:"
    echo "   cd $SCRIPT_DIR && python server.py"
    echo ""
    echo "4. Connect with client:"
    echo "   python cli.py"
    echo ""
    echo "Documentation:"
    echo "   - INSTALL.md - Full installation guide"
    echo "   - LEVELDB_TUNING.md - Performance tuning"
    echo "   - README.md - General documentation"
    echo ""
}

# Main execution
main() {
    print_header "KosDB Master Setup Script v$KOSDB_VERSION"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-venv)
                USE_VIRTUAL_ENV=0
                shift
                ;;
            --skip-tests)
                SKIP_TESTS=1
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --no-venv        Don't create virtual environment"
                echo "  --skip-tests     Skip test execution"
                echo "  --help           Show this help message"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Run installation steps
    check_prerequisites
    setup_virtual_environment
    clone_repositories
    build_leveldb
    install_plyvel
    install_kosdb
    run_tests
    create_admin_user
    print_summary
}

# Run main function
main "$@"
