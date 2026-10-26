# KosDB

LevelDB-based database server with authentication, replication, and TLS.

## Installation

See [docs/INSTALL.md](docs/INSTALL.md) for detailed instructions.

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [Configuration](docs/CONFIGURATION.md)
- [Operations](docs/OPERATIONS.md)
- [Quick Reference](docs/QUICK_REFERENCE.md)

## :) To start in debian/ubuntu first install -> apt install python3-plyvel
python3 server.py -h # For help...

python3 server.py --prepare-admin admin --prepare-password adminpassword

python3 server.py --port 3306


# now you can connect and login
...


## Export and Import

KosDB includes offline export/import utilities that operate directly on the LevelDB data files.

> **Important:** The server must be stopped while using `--export` or `--import` to avoid LevelDB lock conflicts.

### Export

```bash
# Export a whole database
python3 server.py --export <database>

# Export with custom output file
python3 server.py --export <database> --export-to backup.sql

# Export a single table
python3 server.py --export <database>.<table>
```

### Import

```bash
python3 server.py --import backup.sql
```

The dump format is plain SQL compatible with KosDB's command parser. `DROP TABLE IF EXISTS`, `CREATE TABLE`, `INSERT`, and `SET TABLE ... next_id` statements are supported. During import, existing tables are automatically recreated.

## License

MIT License
