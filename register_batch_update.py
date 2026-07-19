#!/usr/bin/env python3
"""Register BATCH_UPDATE command in CommandRegistry"""

with open('commands.py', 'r') as f:
    content = f.read()

# Add BATCH_UPDATE to the command registry
old_registry = """            'UPSERT': UpsertCommand(self.db, self.replication_client),
            'UPDATE': UpdateCommand(self.db, self.replication_client),"""

new_registry = """            'UPSERT': UpsertCommand(self.db, self.replication_client),
            'BATCH_UPDATE': BatchUpdateCommand(self.db, self.replication_client),
            'UPDATE': UpdateCommand(self.db, self.replication_client),"""

content = content.replace(old_registry, new_registry)

with open('commands.py', 'w') as f:
    f.write(content)

print("BATCH_UPDATE command registered in CommandRegistry!")
