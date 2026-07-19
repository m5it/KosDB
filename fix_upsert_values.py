#!/usr/bin/env python3
"""Fix UPSERT value parsing"""

with open('commands.py', 'r') as f:
    content = f.read()

# Find and replace the value parsing in UpsertCommand
old_upsert = '''        # Parse values
        values = []
        for v in values_str.split(','):
            v = v.strip()
            if v.startswith("'") and v.endswith("'"):
                v = v[1:-1]
            elif v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            try:
                v = int(v)
            except ValueError:
                try:
                    v = float(v)
                except ValueError:
                    pass
            values.append(v)'''

new_upsert = '''        # Parse values (same logic as InsertCommand)
        values = []
        for v in values_str.split(','):
            v = v.strip()
            # Handle quoted strings
            if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                v = v[1:-1]
            else:
                # Try to convert to number
                try:
                    v = int(v)
                except ValueError:
                    try:
                        v = float(v)
                    except ValueError:
                        pass  # Keep as string
            values.append(v)'''

content = content.replace(old_upsert, new_upsert)

with open('commands.py', 'w') as f:
    f.write(content)

print("Fixed UPSERT value parsing!")
