
"""
Interactive Batch CLI for KosDB v2.3.0

Provides interactive batch building with:
- Command history and line editing
- Syntax highlighting hints
- Auto-completion
- Multi-line batch editing
- Progress indicators
- Error recovery
- Result caching support
"""

import sys
import os
import time
import threading
import re
import readline
from typing import List, Dict, Any, Optional, Callable, Union
from dataclasses import dataclass
from datetime import datetime

# Import compression support
try:
    from batch_compression import (
        BatchCompressionManager,
        CompressionAlgorithm,
        compress_batch_response,
        decompress_batch_response
    )
    COMPRESSION_AVAILABLE = True
except ImportError:
    COMPRESSION_AVAILABLE = False

# Import query cache support
try:
    from batch_query_cache import BatchQueryCache, BatchCacheManager
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    COMPRESSION_AVAILABLE = False

@dataclass
class BatchCommand:
    """Represents a single batch command."""
    command: str
    line_number: int
    validated: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'command': self.command,
            'line_number': self.line_number,
            'validated': self.validated,
            'error_message': self.error_message
        }


class InteractiveBatchBuilder:
    """Interactive batch builder for CLI."""
    
    def __init__(self, validator: Optional[Callable] = None):
        self.commands: List[BatchCommand] = []
        self.in_batch_mode = False
        self.current_line = 0
        self.validator = validator
        self.batch_name = None
        self._setup_completion()
    
    def _setup_completion(self):
        """Setup tab completion for batch commands."""
        self.valid_commands = [
            'SELECT', 'INSERT', 'UPDATE', 'DELETE',
            'CREATE', 'DROP', 'ALTER',
            'BEGIN', 'COMMIT', 'ROLLBACK',
            'EXPLAIN', 'DESCRIBE', 'SHOW'
        ]
        readline.set_completer(self._completer)
        readline.parse_and_bind('tab: complete')
    
    def _completer(self, text, state):
        """Tab completion function."""
        options = [cmd for cmd in self.valid_commands 
                  if cmd.upper().startswith(text.upper())]
        if state < len(options):
            return options[state]
        return None
    
    def start_batch_mode(self, name: Optional[str] = None):
        """Enter batch building mode."""
        self.in_batch_mode = True
        self.batch_name = name or f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_line = 0
        
        print(f"\n{'='*60}")
        print(f"Entering BATCH MODE: {self.batch_name}")
        print(f"{'='*60}")
        print("Type SQL commands, one per line.")
        print("Special commands:")
        print("  \\endbatch    - Finish and execute batch")
        print("  \\showbatch   - Show current batch")
        print("  \\clearbatch  - Clear all commands")
        print("  \\remove <n>  - Remove command number n")
        print("  \\preview     - Preview batch before execution")
        print("  \\validate    - Validate all commands")
        print("  \\save <file> - Save batch to file")
        print("  \\load <file> - Load batch from file")
        print("  \\help        - Show help")
        print("  \\cancel      - Cancel batch mode")
        print(f"{'='*60}\n")
    
    def end_batch_mode(self) -> List[str]:
        """Exit batch mode and return commands."""
        self.in_batch_mode = False
        commands = [cmd.command for cmd in self.commands]
        print(f"\nExiting batch mode. {len(commands)} commands collected.")
        return commands
    
    def add_command(self, command: str) -> bool:
        """Add command to batch."""
        command = command.strip()
        if not command:
            return False
        
        if command.startswith('\\'):
            return self._handle_special_command(command)
        
        self.current_line += 1
        batch_cmd = BatchCommand(command=command, line_number=self.current_line)
        
        if self.validator:
            try:
                self.validator(command)
                batch_cmd.validated = True
            except Exception as e:
                batch_cmd.error_message = str(e)
        
        self.commands.append(batch_cmd)
        print(f"  [{self.current_line}] Added: {command[:60]}{'...' if len(command) > 60 else ''}")
        return True
    
    def _handle_special_command(self, command: str) -> bool:
        """Handle special batch commands."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        
        handlers = {
            '\\endbatch': self._cmd_endbatch,
            '\\showbatch': self._cmd_showbatch,
            '\\clearbatch': self._cmd_clearbatch,
            '\\remove': lambda: self._cmd_remove(arg),
            '\\preview': self._cmd_preview,
            '\\validate': self._cmd_validate,
            '\\save': lambda: self._cmd_save(arg),
            '\\load': lambda: self._cmd_load(arg),
            '\\help': self._cmd_help,
            '\\cancel': self._cmd_cancel,
        }
        
        handler = handlers.get(cmd)
        if handler:
            return handler()
        else:
            print(f"Unknown command: {cmd}")
            return False
    
    def _cmd_endbatch(self) -> bool:
        """Handle \\endbatch command."""
        if not self.commands:
            print("Warning: Batch is empty!")
            confirm = input("Execute empty batch? (y/N): ").strip().lower()
            if confirm != 'y':
                return False
        
        self._cmd_preview()
        
        confirm = input("\nExecute this batch? (Y/n): ").strip().lower()
        if confirm == 'n':
            print("Batch execution cancelled.")
            return False
        
        self.in_batch_mode = False
        return False
    
    def _cmd_showbatch(self) -> bool:
        """Handle \\showbatch command."""
        if not self.commands:
            print("\nBatch is empty.")
            return False
        
        print(f"\n{'='*60}")
        print(f"BATCH: {self.batch_name}")
        print(f"{'='*60}")
        print(f"Commands: {len(self.commands)}")
        print(f"Estimated size: {self._estimate_size()} bytes")
        print(f"{'-'*60}")
        
        for i, cmd in enumerate(self.commands, 1):
            status = "OK" if cmd.validated else "ERR" if cmd.error_message else "?"
            line = f"  [{i:3d}] {status} {cmd.command[:50]}"
            if len(cmd.command) > 50:
                line += "..."
            print(line)
            if cmd.error_message:
                print(f"       Error: {cmd.error_message}")
        
        print(f"{'='*60}")
        return False
    
    def _cmd_clearbatch(self) -> bool:
        """Handle \\clearbatch command."""
        if not self.commands:
            print("Batch is already empty.")
            return False
        
        confirm = input("Clear all commands? (y/N): ").strip().lower()
        if confirm == 'y':
            count = len(self.commands)
            self.commands.clear()
            self.current_line = 0
            print(f"Cleared {count} commands.")
        else:
            print("Clear cancelled.")
        return False
    
    def _cmd_remove(self, arg: str) -> bool:
        """Handle \\remove command."""
        if not arg:
            print("Usage: \\remove <command_number>")
            return False
        
        try:
            idx = int(arg) - 1
            if 0 <= idx < len(self.commands):
                removed = self.commands.pop(idx)
                print(f"Removed command [{arg}]: {removed.command[:50]}...")
                for i, cmd in enumerate(self.commands):
                    cmd.line_number = i + 1
                self.current_line = len(self.commands)
            else:
                print(f"Invalid command number: {arg}")
        except ValueError:
            print(f"Invalid number: {arg}")
        return False
    
    def _cmd_preview(self) -> bool:
        """Handle \\preview command."""
        if not self.commands:
            print("\nBatch is empty - nothing to preview.")
            return False
        
        print(f"\n{'='*60}")
        print("BATCH PREVIEW")
        print(f"{'='*60}")
        
        total_commands = len(self.commands)
        validated = sum(1 for cmd in self.commands if cmd.validated)
        errors = sum(1 for cmd in self.commands if cmd.error_message)
        
        print(f"Batch Name:     {self.batch_name}")
        print(f"Total Commands: {total_commands}")
        print(f"Validated:      {validated}")
        print(f"Errors:         {errors}")
        print(f"Est. Size:      {self._estimate_size()} bytes")
        print(f"Est. Time:      {self._estimate_time()} ms")
        print(f"{'-'*60}")
        
        by_type = {}
        for cmd in self.commands:
            cmd_type = cmd.command.split()[0].upper()
            by_type[cmd_type] = by_type.get(cmd_type, 0) + 1
        
        print("Command Breakdown:")
        for cmd_type, count in sorted(by_type.items()):
            print(f"  {cmd_type}: {count}")
        
        print(f"\n{'-'*60}")
        print("Commands (first 5):")
        for i, cmd in enumerate(self.commands[:5], 1):
            print(f"  {i}. {cmd.command[:60]}")
        if len(self.commands) > 5:
            print(f"  ... and {len(self.commands) - 5} more")
        
        print(f"{'='*60}")
        return False
    
    def _cmd_validate(self) -> bool:
        """Handle \\validate command."""
        if not self.validator:
            print("No validator configured.")
            return False
        
        if not self.commands:
            print("Batch is empty.")
            return False
        
        print(f"\nValidating {len(self.commands)} commands...")
        
        valid_count = 0
        error_count = 0
        
        for cmd in self.commands:
            try:
                self.validator(cmd.command)
                cmd.validated = True
                cmd.error_message = None
                valid_count += 1
            except Exception as e:
                cmd.validated = False
                cmd.error_message = str(e)
                error_count += 1
                print(f"  [{cmd.line_number}] Error: {e}")
        
        print(f"\nValidation complete: {valid_count} valid, {error_count} errors")
        return False
    
    def _cmd_save(self, filename: str) -> bool:
        """Handle \\save command."""
        if not filename:
            filename = f"{self.batch_name}.json"
        
        if not self.commands:
            print("Batch is empty - nothing to save.")
            return False
        
        try:
            data = {
                'name': self.batch_name,
                'created': datetime.now().isoformat(),
                'commands': [cmd.to_dict() for cmd in self.commands]
            }
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Batch saved to: {filename}")
        except Exception as e:
            print(f"Error saving batch: {e}")
        return False
    
    def _cmd_load(self, filename: str) -> bool:
        """Handle \\load command."""
        if not filename:
            print("Usage: \\load <filename>")
            return False
        
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            
            self.commands.clear()
            for cmd_data in data.get('commands', []):
                cmd = BatchCommand(
                    command=cmd_data['command'],
                    line_number=len(self.commands) + 1,
                    validated=cmd_data.get('validated', False),
                    error_message=cmd_data.get('error_message')
                )
                self.commands.append(cmd)
            
            self.batch_name = data.get('name', self.batch_name)
            self.current_line = len(self.commands)
            print(f"Loaded batch from: {filename}")
        except FileNotFoundError:
            print(f"File not found: {filename}")
        except json.JSONDecodeError as e:
            print(f"Invalid JSON file: {e}")
        except Exception as e:
            print(f"Error loading batch: {e}")
        return False
    
    def _cmd_help(self) -> bool:
        """Handle \\help command."""
        help_text = """
Interactive Batch Builder Commands:
====================================
\\endbatch    - Finish batch and execute
\\showbatch   - Display current batch contents
\\clearbatch  - Remove all commands from batch
\\remove <n>  - Remove command number n
\\preview     - Preview batch before execution
\\validate    - Validate all commands
\\save <file> - Save batch to JSON file
\\load <file> - Load batch from JSON file
\\help        - Show this help message
\\cancel      - Cancel batch mode without executing

Tips:
- Use TAB for command completion
- Commands are validated as you type
- Preview shows estimated size and execution time
        """
        print(help_text)
        return False
    
    def _cmd_cancel(self) -> bool:
        """Handle \\cancel command."""
        confirm = input("Cancel batch? All commands will be lost. (y/N): ").strip().lower()
        if confirm == 'y':
            self.commands.clear()
            self.in_batch_mode = False
            print("Batch cancelled.")
        else:
            print("Continue building batch...")
        return False
    
    def _estimate_size(self) -> int:
        """Estimate batch size in bytes."""
        return sum(len(cmd.command.encode('utf-8')) for cmd in self.commands)
    
    def _estimate_time(self) -> int:
        """Estimate execution time in milliseconds."""
        base_time = len(self.commands)
        for cmd in self.commands:
            cmd_upper = cmd.command.upper()
            if 'SELECT' in cmd_upper:
                base_time += 2
            elif 'INSERT' in cmd_upper or 'UPDATE' in cmd_upper:
                base_time += 5
        return base_time
    
    def get_batch(self) -> List[str]:
        """Get current batch commands."""
        return [cmd.command for cmd in self.commands]
    
    def is_valid(self) -> bool:
        """Check if all commands are valid."""
        if not self.commands:
            return False
        return all(cmd.validated for cmd in self.commands)


class BatchCLI:
    """Main CLI with batch support."""
    
    def __init__(self, executor=None):
        self.executor = executor
        self.batch_builder = InteractiveBatchBuilder(validator=self._validate)
        self.running = True
    
    def _validate(self, command: str) -> bool:
        """Validate a command."""
        command = command.strip()
        if not command:
            raise ValueError("Empty command")
        
        valid_starts = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 
                       'CREATE', 'DROP', 'ALTER', 'BEGIN', 
                       'COMMIT', 'ROLLBACK', 'EXPLAIN']
        
        first_word = command.split()[0].upper()
        if first_word not in valid_starts:
            raise ValueError(f"Unknown command: {first_word}")
        return True
    
    def run(self):
        """Run interactive CLI."""
        print("KosDB Interactive CLI")
        print("Type \\batch to enter batch mode, \\quit to exit")
        print()
        
        while self.running:
            try:
                if self.batch_builder.in_batch_mode:
                    prompt = f"batch[{len(self.batch_builder.commands)}]> "
                else:
                    prompt = "kosdb> "
                
                line = input(prompt).strip()
                
                if not line:
                    continue
                
                if line.startswith('\\'):
                    self._handle_command(line)
                elif self.batch_builder.in_batch_mode:
                    self.batch_builder.add_command(line)

class BatchCLI:
    """
    Main CLI with batch support and automatic decompression.
    """
    
    def __init__(self, executor=None):
        self.executor = executor
        self.batch_builder = InteractiveBatchBuilder(validator=self._validate)
        self.running = True
        self.compression_manager = BatchCompressionManager() if COMPRESSION_AVAILABLE else None
        self.cache_manager = BatchCacheManager() if CACHE_AVAILABLE else None
        self.show_metrics = False
    """
    
    def __init__(self, executor=None):
        self.executor = executor
        self.batch_builder = InteractiveBatchBuilder(validator=self._validate)
        self.running = True
        self.compression_manager = BatchCompressionManager() if COMPRESSION_AVAILABLE else None
        """Execute single command."""
        print(f"Executing: {command}")
        if self.executor:
            try:
                result = self.executor(command)
                print(f"Result: {result}")
            except Exception as e:
                print(f"Error: {e}")
        else:
            print("(No executor configured - command not executed)")
    
    def _show_status(self):
        """Show CLI status."""
        print(f"\nCLI Status:")
        print(f"  Batch Mode: {'Active' if self.batch_builder.in_batch_mode else 'Inactive'}")

            # Handle special commands
            if line.upper() == 'HELP':
                self._show_help()
                continue
            elif line.upper() == 'METRICS':
                self._show_metrics()
                continue
            elif line.upper() == 'CLEAR':
                self.batch_builder.clear()
                continue
            elif line.upper().startswith('CACHE STATUS'):
                self._show_cache_status()
                continue
            elif line.upper().startswith('WARM CACHE'):
                self._warm_cache(line)
                continue
            elif line.upper().startswith('CACHE CLEAR'):
                self._clear_cache()
                continue
            
            # Add to batch
            self.batch_builder.add_command(line)
                
                # Handle compressed response
                if isinstance(result, dict) and result.get('compressed'):
                    result = self._decompress_response(result)
                
                print(f"Result: {result}")
            except Exception as e:
                print(f"Error: {e}")
        else:
            print("(No executor configured - command not executed)")
    
    def _decompress_response(self, result: Dict[str, Any]) -> Any:
        """Decompress response if needed."""
        if not COMPRESSION_AVAILABLE:
            return result.get('data', result)
        
        try:

    def _show_help(self):
        """Show help text."""
        print("""
Interactive Batch Builder Commands:
  help              Show this help
  metrics           Show execution metrics
  clear             Clear current batch
  cache status      Show query cache status
  warm cache for    Pre-warm cache for a query
  cache clear       Clear query cache
  
  @<filename>      Load commands from file
  !<command>       Execute shell command
  
  ;;               Enter batch mode (type END to finish)
  run              Execute current batch
  save <name>      Save batch with name
  list             List saved batches
  load <name>      Load saved batch
  
  Ctrl+D           Exit
""")
    
    def _show_cache_status(self):
        """Show query cache status."""
        if not CACHE_AVAILABLE or not self.cache_manager:
            print("Query cache not available")
            return
        
        status = self.cache_manager.get_status()
        print(status)
    
    def _warm_cache(self, line: str):
        """Warm cache for a query."""
        if not CACHE_AVAILABLE or not self.cache_manager:
            print("Query cache not available")
            return
        
        # Extract query from "WARM CACHE FOR <query>"
        match = re.search(r'WARM\s+CACHE\s+FOR\s+(.+)', line, re.IGNORECASE)
        if not match:
            print("Usage: WARM CACHE FOR <SELECT ...>")
            return
        
        query = match.group(1).strip()
        print(f"Warming cache for: {query[:50]}...")
        
        def executor(q):
            if self.executor:
                return self.executor(q)
            return "Mock result"
        
        success = self.cache_manager.warm_cache(query, executor)
        if success:
            print("Cache warmed successfully")
        else:
            print("Failed to warm cache")
    
    def _clear_cache(self):

    def _show_metrics(self):
        """Show execution metrics."""
        print("\n--- Execution Metrics ---")
        
        if self.cache_manager:
            stats = self.cache_manager.get_stats()
            print(f"Cache Hit Ratio: {stats.get('hit_ratio', 0):.2%}")
            print(f"Cache Hits: {stats.get('hits', 0)}")
            print(f"Cache Misses: {stats.get('misses', 0)}")
            print(f"Invalidations: {stats.get('invalidations', 0)}")
        
        if self.compression_manager:
            stats = self.compression_manager.get_stats()
            print(f"Compression Ratio: {stats.get('avg_compression_ratio', 0):.2%}")
        
        print("-----------------------\n")
