
"""
Batch Backup/Restore Operations Examples

Demonstrates batch backup and restore operations:
- Simple batch backups
- Conditional backups
- Backup chaining
- Automated backup workflows
"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_backup import (
    BatchBackupManager,
    BackupStatus,
    get_batch_backup_manager,
    parse_backup_chain
)


def example_simple_backup():
    """Example: Simple batch backup."""
    print("\n=== Simple Backup Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchBackupManager(temp_dir)
    
    try:
        result = manager.execute_backup(
            source_db='production_db',
            target_file='prod_backup.json.gz',
            tables=['users', 'orders', 'products']
        )
        
        print(f"Backup Status: {result.status.value}")
        print(f"File: {result.file_path}")
        print(f"Size: {result.size_bytes} bytes")
        print(f"Time: {result.elapsed_ms:.2f}ms")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def example_conditional_backup():
    """Example: Conditional backup based on database size."""
    print("\n=== Conditional Backup Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchBackupManager(temp_dir)
    
    try:
        context = {'db_size': 1500, 'row_count': 50000}
        
        condition = 'size > 1000'
        should_backup = manager.check_condition(condition, context)
        
        print(f"Database size: {context['db_size']} MB")
        print(f"Condition: {condition}")
        print(f"Should backup: {should_backup}")
        
        if should_backup:
            result = manager.execute_backup(
                source_db='large_db',
                target_file='conditional_backup.json.gz'
            )
            print(f"Backup completed: {result.status.value}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def example_backup_chain():
    """Example: Backup chaining with multiple operations."""
    print("\n=== Backup Chain Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchBackupManager(temp_dir)
    
    try:
        backup_result = manager.execute_backup(
            source_db='main_db',
            target_file='main_backup.json.gz'
        )
        
        operations = [
            {'type': 'backup', 'source_db': 'main_db', 'target_file': 'backup_copy1.json.gz'},
            {'type': 'verify', 'file_path': backup_result.file_path},
        ]
        
        result = manager.execute_chain(operations)
        
        print(f"Chain Results: {result.successful}/{result.total_operations} successful")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def example_restore_with_verification():
    """Example: Restore with verification."""
    print("\n=== Restore with Verification Example ===\n")
    
    temp_dir = tempfile.mkdtemp()
    manager = BatchBackupManager(temp_dir)
    
    try:
        backup_result = manager.execute_backup(
            source_db='source_db',
            target_file='source_backup.json.gz'
        )
        
        restore_result = manager.execute_restore(
            source_file=backup_result.file_path,
            target_db='restored_db',
            verify=True
        )
        
        print(f"Restore Status: {restore_result.status.value}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_all_examples():
    """Run all backup examples."""
    examples = [
        example_simple_backup,
        example_conditional_backup,
        example_backup_chain,
        example_restore_with_verification,
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\nError in {example.__name__}: {e}")
    
    print("\n" + "="*60)
    print("All backup examples completed!")
    print("="*60)


if __name__ == '__main__':
    run_all_examples()
