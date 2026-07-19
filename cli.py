
#!/usr/bin/env python3
"""
LevelDB Socket Server - Interactive CLI Client

Features:
- Interactive mode with readline history and tab completion
- Scripting mode for batch command execution
- Colored output for better readability
- Connection management with configurable host/port
- Pretty-printed results for tables and structured data
- Multi-command batch support with semicolon separation
"""

# Auto-version - increments automatically via git pre-commit hook
try:
    from AUTOVERSION import VERSION as __version__
except ImportError:
    __version__ = "2.3.0"

import socket
import sys
import os
import argparse
import getpass
import json
import re
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
        self.use_colors = sys.stdout.isatty()
        self.cache_enabled = True
    
    def _colorize(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text
    
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
            data = self.socket.recv(65536)
            if not data:
                return None
            return data.decode().strip()
        except socket.timeout:
            print(self._colorize("ERROR: Connection timeout", Colors.RED))
            return None
        except Exception as e:
            print(self._colorize(f"ERROR: Failed to receive: {e}", Colors.RED))
            return None
    
    def execute_batch(self, commands: str) -> str:
        """Execute multiple commands in batch mode."""
        if not self.send(commands):
            return "ERROR: Failed to send batch"
        
        response = self.receive()
        if response is None:
            return "ERROR: No response from server"
        
        return response
    
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
            print(self._colorize(f"Authenticated as {self.username}", Colors.GREEN))
            return True
        else:
            print(self._colorize(f"ERROR: {response}", Colors.RED))
            return False
    
    def display_batch_results(self, response: str):
        """Display batch results in formatted way."""
        if not response:
            print("No response")
            return
        
        # Check if it's a batch response
        if "[1/" in response and "--- Batch Complete ---" in response:
            # Colorize batch results
            lines = response.split('\n')
            for line in lines:
                if line.startswith('['):
                    if 'ERROR:' in line:
                        print(self._colorize(line, Colors.RED))
                    elif 'OK:' in line:
                        print(self._colorize(line, Colors.GREEN))
                    elif 'BYE:' in line:
                        print(self._colorize(line, Colors.YELLOW))
                    else:
                        print(line)
                elif 'Batch Complete' in line:
                    print(self._colorize(line, Colors.CYAN))
                else:
                    print(line)
        else:
            # Single command response
            if response.startswith("ERROR"):
                print(self._colorize(response, Colors.RED))
            else:
                print(response)


def read_batch_file(filepath: str) -> str:
    """Read commands from batch file."""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        # Filter out comments and empty lines, join with semicolons
        commands = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('--') and not line.startswith('#'):
                commands.append(line)
        
        return '; '.join(commands)
    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}")
        return ""
    except Exception as e:
        print(f"ERROR: Failed to read file: {e}")
        return ""


def interactive_mode(client: LevelDBClient):
    """Run interactive mode with multi-command support."""
    print("\n" + "=" * 50)
    print("KosDB Interactive CLI")
    print("Type SQL commands (end with ; for batch mode)")
    print("Special commands: \\q to quit, \\batch to enter batch builder")
    print("=" * 50 + "\n")
    
    # Try to import readline for history
    try:
        import readline
        readline.parse_and_bind('tab: complete')
    except ImportError:
        pass
    
    batch_buffer = []
    in_batch_mode = False
    
    while True:
        try:
            if in_batch_mode:
                prompt = "batch> "
            else:
                prompt = "kosdb> "
            
            line = input(prompt).strip()
            
            if not line:
                continue
            
            # Special commands
            if line == '\\q':
                break
            
            if line == '\\batch':
                in_batch_mode = True
                batch_buffer = []
                print("Entering batch mode. Type \\end to execute, \\cancel to abort")
                continue
            
            if line == '\\end' and in_batch_mode:
                in_batch_mode = False
                if batch_buffer:
                    batch_cmd = '; '.join(batch_buffer)
                    print(f"\nExecuting batch ({len(batch_buffer)} commands)...")
                    response = client.execute_batch(batch_cmd)
                    client.display_batch_results(response)
                    batch_buffer = []
                continue
            
            if line == '\\cancel' and in_batch_mode:
                in_batch_mode = False
                batch_buffer = []
                print("Batch cancelled")
                continue
            
            # In batch mode, accumulate commands
            if in_batch_mode:
                batch_buffer.append(line)
                print(f"  [{len(batch_buffer)}] {line}")
                continue
            
            # Check for semicolons - batch mode
            if ';' in line:
                response = client.execute_batch(line)
                client.display_batch_results(response)
            else:
                # Single command
                response = client.execute_batch(line)
                client.display_batch_results(response)
            
            if response == "BYE":
                break
                
        except KeyboardInterrupt:
            print("\nUse \\q to quit")
        except EOFError:
            break
    
    print("\nGoodbye!")


def main():
    parser = argparse.ArgumentParser(description='KosDB CLI Client')
    parser.add_argument('-H', '--host', default='localhost', help='Server host')
    parser.add_argument('-P', '--port', type=int, default=9999, help='Server port')
    parser.add_argument('-u', '--user', help='Username')
    parser.add_argument('-p', '--password', help='Password')
    parser.add_argument('-c', '--command', help='Execute single command')
    parser.add_argument('-b', '--batch', metavar='FILE', help='Execute batch from file')
    parser.add_argument('--no-color', action='store_true', help='Disable colored output')
    
    args = parser.parse_args()
    
    client = LevelDBClient(host=args.host, port=args.port,
                          username=args.user, password=args.password)
    
    if args.no_color:
        client.use_colors = False
    
    # Connect to server
    if not client.connect():
        sys.exit(1)
    
    # Authenticate
    if not client.authenticate():
        client.disconnect()
        sys.exit(1)
    
    # Execute batch file
    if args.batch:
        batch_commands = read_batch_file(args.batch)
        if batch_commands:
            print(f"Executing batch from {args.batch}...")
            response = client.execute_batch(batch_commands)
            client.display_batch_results(response)
        client.disconnect()
        return
    
    # Execute single command
    if args.command:
        response = client.execute_batch(args.command)
        client.display_batch_results(response)
        client.disconnect()
        return
    
    # Interactive mode
    interactive_mode(client)
    client.disconnect()


if __name__ == '__main__':
    main()
