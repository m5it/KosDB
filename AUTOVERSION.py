
# Auto-generated version file - do not edit manually
# Incremented automatically by git pre-commit hook
VERSION = "2.3.3"

if __name__ == "__main__":
    import sys
    if "-c" in sys.argv or "--current" in sys.argv:
        print(VERSION)
    elif "-h" in sys.argv or "--help" in sys.argv:
        print("Usage: python AUTOVERSION.py [-c|--current] [-h|--help]")
        print("  -c, --current  Print current version")
        print("  -h, --help     Show this help")
    else:
        print(f"KosDB Auto-Version: {VERSION}")
