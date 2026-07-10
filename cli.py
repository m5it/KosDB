#!/usr/bin/env python3
"""
LevelDB Socket Server - Interactive CLI Client

Features:
- Interactive mode with readline history and tab completion
- Scripting mode for batch command execution
- Colored output for better readability
- Connection management with configurable host/port
- Pretty-printed results for tables and structured data
"""

import socket
import sys
import os
import argparse
import getpass
import json
import re
from typing import Optional, List, Tuple


# ANSI color codes for terminal output
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'


class LevelDBClient:
    """Client for connecting to LevelDB Socket Server."""
    
    def __init__(self, host: str = 'localhost', port: int = 9999,
                 username: Optional[str] = None, password: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.socket: Optional[socket.socket] = None
        self.authenticated = False
        self.current_db: Optional[str] = None
        self.use_colors = sys.stdout.isatty()  # Only use colors in TTY
    
    def connect(self) -> bool:
        """Establish connection to server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30)
            self.socket.connect((self.host, self.port))
            return True
        except Exception as e:
            print(self._colorize(f"ERROR: Failed to connect to {self.host}:{self.port}", Colors.RED))
            print(f"       {e}")
            return False
    
    def disconnect(self):
        """Close connection."""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            self.authenticated = False
    
    def send(self, message: str) -> bool:
        """Send message to server."""
        if not self.socket:
            return False
        try:
            self.socket.sendall(message.encode() + b'\n')
            return True
        except Exception as e:
            print(self._colorize(f"ERROR: Failed to send: {e}", Colors.RED))
            return False
    
    def receive(self) -> Optional[str]:
        """Receive response from server."""
        if not self.socket:
            return None
        try:
            data = self.socket.recv(16384)
            if not data:
                return None
            return data.decode().strip()
        except socket.timeout:
            print(self._colorize("ERROR: Connection timeout", Colors.RED))
            return None
        except Exception as e:
            print(self._colorize(f"ERROR: Failed to receive: {e}", Colors.RED))
            return None
    
    def authenticate(self) -> bool:
        """Authenticate with server."""
        if not self.username:
            self.username = input("Username: ")
        if not self.password:
            self.password = getpass.getpass("Password: ")
        
        # Send USER command
        self.send(f"USER {self.username}")
        response = self.receive()
        if not response or not response.startswith("OK"):
            print(self._colorize(f"ERROR: {response}", Colors.RED))
            return False
        
        # Send PASS command
        self.send(f"PASS {self.password}")
        response = self.receive()
        if response and response.startswith("OK"):
            self.authenticated = True
            print(self._colorize(f"\n✓ {response}", Colors.GREEN))
            return True
        else:
            print(self._colorize(f"ERROR: {response}", Colors.RED))
            return False
    
    def execute(self, command: str) -> str:
        """Execute a command and return response."""
        if not self.send(command):
            return "ERROR: Not connected"
        
        response = self.receive()
        if response is None:
            return "ERROR: Connection lost"
        
        # Track current database
        if command.upper().startswith("USE "):
            if response.startswith("OK"):
                self.current_db = command.split()[1].strip()
        
        return response
    
    def _colorize(self, text: str, color: str) -> str:
        """Apply color if colors are enabled."""
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text
    
    def format_response(self, response: str) -> str:
        """Format server response with colors."""
        if response.startswith("OK"):
            # Success message
            if "\n" in response:
                # Multi-line result (like table output)
                lines = response.split('\n')
                formatted = [self._colorize(lines[0], Colors.GREEN)]
                
                # Format table output
                if len(lines) > 1 and '|' in lines[1]:
                    formatted.extend(self._format_table(lines[1:]))
                else:
                    formatted.extend(lines[1:])
                
                return '\n'.join(formatted)
            else:
                return self._colorize(response, Colors.GREEN)
        
        elif response.startswith("ERROR"):
            return self._colorize(response, Colors.RED)
        
        elif response.startswith("Empty set"):
            return self._colorize(response, Colors.YELLOW)
        
        elif "row(s) in set" in response:
            return self._colorize(response, Colors.CYAN)
        
        else:
            return response
    
    def _format_table(self, lines: List[str]) -> List[str]:
        """Format table output with colors."""
        result = []
        for i, line in enumerate(lines):
            if line.startswith('+--'):
                # Separator line - dim it
                result.append(self._colorize(line, Colors.DIM))
            elif i == 0 and '|' in line:
                # Header row
                result.append(self._colorize(line, Colors.BOLD + Colors.CYAN))
            else:
                result.append(line)
        return result


class InteractiveShell:
    """Interactive shell with readline support."""
    
    def __init__(self, client: LevelDBClient):
        self.client = client
        self.history_file = os.path.expanduser("~/.leveldb_cli_history")
        self.commands = [
            'SELECT', 'INSERT', 'UPDATE', 'DELETE',
            'CREATE', 'DROP', 'USE', 'SHOW',
            'DATABASES', 'TABLES', 'USERS',
            'HELP', 'QUIT', 'EXIT',
            'FROM', 'WHERE', 'ORDER', 'BY', 'ASC', 'DESC',
            'INTO', 'VALUES', 'SET',
            'MASTER', 'SLAVE', 'STATUS',
            'START', 'STOP', 'RESET',
        ]
        self.setup_readline()
    
    def setup_readline(self):
        """Configure readline for history and completion."""
        try:
            import readline
            import rlcompleter
            
            # Load history
            if os.path.exists(self.history_file):
                try:
                    readline.read_history_file(self.history_file)
                except:
                    pass
            
            # Set up completion
            readline.set_completer(self._completer)
            readline.parse_and_bind('tab: complete')
            readline.set_completer_delims(' \t\n;')
            
        except ImportError:
            pass  # Windows or no readline support
    
    def _completer(self, text: str, state: int) -> Optional[str]:
        """Tab completion function."""
        matches = [cmd for cmd in self.commands if cmd.upper().startswith(text.upper())]
        if state < len(matches):
            # Add space after command for convenience
            match = matches[state]
            if text.isupper():
                return match.upper()
            return match.lower()
        return None
    
    def save_history(self):
        """Save command history."""
        try:
            import readline
            readline.write_history_file(self.history_file)
        except:
            pass
    
    def run(self):
        """Run interactive shell."""
        print(self.client._colorize("\n" + "=" * 50, Colors.CYAN))
        print(self.client._colorize("  LevelDB Interactive CLI", Colors.BOLD + Colors.CYAN))
        print(self.client._colorize("=" * 50, Colors.CYAN))
        print("Type 'help' for commands, 'quit' to exit")
        print("-" * 50 + "\n")
        
        try:
            while True:
                # Build prompt
                db_name = self.client.current_db or "none"
                prompt = f"{self.client.username}@{db_name}> "
                if self.client.use_colors:
                    prompt = f"{Colors.GREEN}{self.client.username}{Colors.RESET}@{Colors.YELLOW}{db_name}{Colors.RESET}> "
                
                try:
                    command = input(prompt).strip()
                except EOFError:
                    print()
                    break
                
                if not command:
                    continue
                
                # Handle shell commands
                if command.lower() in ('quit', 'exit', 'q'):
                    break
                
                if command.lower() == 'help':
                    response = self.client.execute("HELP")
                else:
                    response = self.client.execute(command)
                
                print(self.client.format_response(response))
                
                # Check for disconnect
                if response == "BYE":
                    break
        
        except KeyboardInterrupt:
            print("\nInterrupted.")
        finally:
            self.save_history()
            self.client.disconnect()
            print(self.client._colorize("\nGoodbye!", Colors.CYAN))


def execute_script(client: LevelDBClient, script_file: str) -> int:
    """Execute commands from a script file."""
    try:
        with open(script_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"ERROR: Cannot read script file: {e}")
        return 1
    
    print(f"Executing script: {script_file}")
    print("-" * 40)
    
    exit_code = 0
    line_num = 0
    
    for line in lines:
        line_num += 1
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith('#') or line.startswith('--'):
            continue
        
        print(f"[{line_num:3d}] {line}")
        
        response = client.execute(line)
        print(client.format_response(response))
        print()
        
        # Check for errors
        if response.startswith("ERROR"):
            exit_code = 1
            # Continue execution unless it's a connection error
    
    return exit_code


def main():
    parser = argparse.ArgumentParser(
        description='LevelDB Socket Server CLI Client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Interactive mode
  %(prog)s -h localhost -p 9999     # Connect to specific server
  %(prog)s -u admin -f script.sql   # Execute script file
  %(prog)s -c "SELECT * FROM users" # Single command mode
  
Connection:
  %(prog)s --host 192.168.1.100 --port 9999 --user admin
        """
    )
    
    # Connection options
    conn_group = parser.add_argument_group('Connection Options')
    conn_group.add_argument('-H', '--host', default='localhost',
                          help='Server host (default: localhost)')
    conn_group.add_argument('-p', '--port', type=int, default=9999,
                          help='Server port (default: 9999)')
    conn_group.add_argument('-u', '--user', '--username',
                          help='Username for authentication')
    conn_group.add_argument('-P', '--password',
                          help='Password (insecure, use prompt instead)')
    conn_group.add_argument('-D', '--database',
                          help='Default database to use')
    
    # Execution modes
    mode_group = parser.add_argument_group('Execution Modes')
    mode_group.add_argument('-f', '--file', dest='script_file',
                           help='Execute commands from file')
    mode_group.add_argument('-c', '--command',
                           help='Execute single command and exit')
    mode_group.add_argument('-i', '--interactive', action='store_true',
                           help='Force interactive mode (default)')
    
    # Output options
    out_group = parser.add_argument_group('Output Options')
    out_group.add_argument('--no-color', action='store_true',
                          help='Disable colored output')
    out_group.add_argument('-v', '--verbose', action='store_true',
                          help='Verbose output')
    
    # Version
    parser.add_argument('--version', action='version', version='%(prog)s 0.2.0')
    
    args = parser.parse_args()
    
    # Create client
    client = LevelDBClient(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password
    )
    
    # Disable colors if requested
    if args.no_color:
        client.use_colors = False
    
    # Connect to server
    if not client.connect():
        return 1
    
    # Authenticate
    if not client.authenticate():
        client.disconnect()
        return 1
    
    # Use default database if specified
    if args.database:
        response = client.execute(f"USE {args.database}")
        if args.verbose or not response.startswith("OK"):
            print(client.format_response(response))
    
    # Execute based on mode
    exit_code = 0
    
    try:
        if args.command:
            # Single command mode
            response = client.execute(args.command)
            print(client.format_response(response))
            if response.startswith("ERROR"):
                exit_code = 1
        
        elif args.script_file:
            # Script mode
            exit_code = execute_script(client, args.script_file)
        
        else:
            # Interactive mode (default)
            shell = InteractiveShell(client)
            shell.run()
    
    finally:
        client.disconnect()
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
