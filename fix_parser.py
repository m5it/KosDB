#!/usr/bin/env python3
"""Add UPSERT and BATCH_UPDATE patterns to parser.py"""

with open('parser.py', 'r') as f:
    content = f.read()

# Add UPSERT pattern after INSERT
if "'UPSERT'" not in content:
    old_insert = '''            'INSERT': re.compile(
                r'^\\s*INSERT\\s+INTO\\s+(?P<table>\\w+)(?:\\s*\\((?P<columns>[^)]+)\\))?\\s+VALUES\\s*\\((?P<values>[^)]+)\\)\\s*$',
                re.IGNORECASE
            ),'''
    
    new_insert = '''            'INSERT': re.compile(
                r'^\\s*INSERT\\s+INTO\\s+(?P<table>\\w+)(?:\\s*\\((?P<columns>[^)]+)\\))?\\s+VALUES\\s*\\((?P<values>[^)]+)\\)\\s*$',
                re.IGNORECASE
            ),
            'UPSERT': re.compile(
                r'^\\s*UPSERT\\s+INTO\\s+(?P<table>\\w+)(?:\\s*\\((?P<columns>[^)]+)\\))?\\s+VALUES\\s*\\((?P<values>[^)]+)\\)\\s*$',
                re.IGNORECASE
            ),'''
    
    content = content.replace(old_insert, new_insert)
    print("Added UPSERT pattern")

# Add BATCH_UPDATE pattern after UPDATE
if "'BATCH_UPDATE'" not in content:
    old_update = '''            'UPDATE': re.compile(
                r'^\\s*UPDATE\\s+(?P<table>\\w+)\\s+SET\\s+(?P<set>.+?)(?:\\s+WHERE\\s+(?P<where>.+))?\\s*$',
                re.IGNORECASE
            ),'''
    
    new_update = '''            'UPDATE': re.compile(
                r'^\\s*UPDATE\\s+(?P<table>\\w+)\\s+SET\\s+(?P<set>.+?)(?:\\s+WHERE\\s+(?P<where>.+))?\\s*$',
                re.IGNORECASE
            ),
            'BATCH_UPDATE': re.compile(
                r'^\\s*BATCH\\s+UPDATE\\s+(?P<table>\\w+)\\s+SET\\s+(?P<set>.+?)\\s+WHERE\\s+(?P<where_col>\\w+)\\s+IN\\s*\\((?P<where_values>[^)]+)\\)\\s*$',
                re.IGNORECASE
            ),'''
    
    content = content.replace(old_update, new_update)
    print("Added BATCH_UPDATE pattern")

with open('parser.py', 'w') as f:
    f.write(content)

print("Parser updated!")
