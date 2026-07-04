# LevelDB Socket Server

A threaded Python socket server providing a MySQL-like command interface over LevelDB backend with database-backed authentication and privilege management.

## Features

- **Threaded TCP Socket Server** - Handles multiple concurrent clients
- **Database-Backed Authentication** - User accounts stored in LevelDB with hashed passwords
- **Privilege System** - Role-based access control (admin/users) with database/table-level permissions
- **Admin User Management** - Create admin users via command line
- **LevelDB Backend** - Persistent key-value storage with table namespacing
- **SQL-like Commands** - CREATE, DROP, INSERT, SELECT, UPDATE, DELETE
- **Advanced Querying** - WHERE clauses, ORDER BY sorting, indexed columns
- **Netcat Compatible** - Test with standard netcat client

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Create an Admin User

Before first use, create an admin user:

```bash
python server.py --prepare_admin admin --prepare_password yourpassword
```

Or interactively (password will be prompted):

```bash
python server.py --prepare_admin admin
```

### 2. Start the Server

```bash
python server.py
```

Server will start on port 9999 with default settings.

Options:
```bash
python server.py --host 0.0.0.0 --port 9999 --data_dir ./data
```

### 3. Connect with Netcat

```bash
nc localhost 9999
```

## Authentication

The server requires authentication before accepting commands:

```
==================================================
LevelDB Socket Server
==================================================
Authentication required
USER <username> then PASS <password>
--------------------------------------------------

USER admin
OK: Send PASS <password>

PASS yourpassword
OK: Welcome admin (admin).
```

## Available Commands

### Database Commands
| Command | Description |
|---------|-------------|
| `SHOW DATABASES` | List all databases |
| `CREATE DATABASE <name>` | Create a new database |
| `DROP DATABASE <name>` | Delete a database |
| `USE <database>` | Select database to use |

### Table Commands
| Command | Description |
|---------|-------------|
| `SHOW TABLES` | List tables in current database |
| `CREATE TABLE <name> (col1 [PRIMARY KEY], col2 [INDEX], ...)` | Create table with optional indexes |
| `DROP TABLE <name>` | Delete a table |

### Data Commands
| Command | Description |
|---------|-------------|
| `INSERT INTO <table> VALUES (val1, val2, ...)` | Insert a record |
| `SELECT * FROM <table>` | Select all records |
| `SELECT * FROM <table> ORDER BY col [ASC\|DESC]` | Select with sorting |
| `SELECT col FROM <table> WHERE condition` | Select with filter |
| `UPDATE <table> SET col=val WHERE condition` | Update records |
| `DELETE FROM <table> WHERE condition` | Delete records |

### Admin Commands
| Command | Description |
|---------|-------------|
| `SHOW USERS` | List all users (admin only) |
| `HELP` | Show available commands |
| `QUIT` / `EXIT` | Disconnect |

## Example Session

### Basic Operations
```
> CREATE DATABASE testdb
OK: Database 'testdb' created

> USE testdb
OK: Switched to database 'testdb'

> CREATE TABLE users (id INT PRIMARY KEY, name TEXT, email TEXT INDEX)
OK: Table 'users' created

> INSERT INTO users VALUES (1, 'John', 'john@example.com')
OK: Inserted 1 row into 'users'

> INSERT INTO users VALUES (2, 'Jane', 'jane@example.com')
OK: Inserted 1 row into 'users'

> SELECT * FROM users
+----+-------+------------------+
| id | name  | email            |
+----+-------+------------------+
| 1  | John  | john@example.com |
| 2  | Jane  | jane@example.com |
+----+-------+------------------+
2 row(s) in set

> SELECT * FROM users ORDER BY name DESC
+----+-------+------------------+
| id | name  | email            |
+----+-------+------------------+
| 2  | Jane  | jane@example.com |
| 1  | John  | john@example.com |
+----+-------+------------------+
1 row(s) in set

> UPDATE users SET name='Johnny' WHERE id=1
OK: Updated 1 row(s) in 'users'

> DELETE FROM users WHERE id=2
OK: Deleted 1 row(s) from 'users'

> DROP TABLE users
OK: Table 'users' dropped

> DROP DATABASE testdb
OK: Database 'testdb' dropped
```

### Admin Operations
```
> SHOW USERS
OK:
admin
john_doe
```

## Table Schema Options

When creating tables, you can specify indexes:

```sql
CREATE TABLE products (
    id INT PRIMARY KEY,        -- Primary key for fast lookup
    name TEXT,                 -- Regular column
    category TEXT INDEX,       -- Indexed for fast filtering
    price FLOAT INDEX          -- Indexed for sorting
)
```

## User Management (Admin Only)

Admins can manage users through the database API (future CLI tool planned). Users are stored in the system database with:
- Username and hashed password (SHA-256 with salt)
- Admin flag
- Database/table-level privileges

## Project Structure

```
t10/
├── server.py           # Main server entry point
├── database.py         # LevelDB wrapper with user/privilege management
├── auth.py            # Session-based authentication
├── parser.py          # SQL command parser
├── commands.py        # Command execution framework
├── tests/
│   └── test_client.py  # Test client
├── requirements.txt    # Dependencies
└── README.md          # Documentation
```

## Configuration

Default settings:
- **Host**: 0.0.0.0
- **Port**: 9999
- **Data Directory**: ./data
- **System Database**: ./_system (stores users and privileges)

Command-line options:
```bash
python server.py --help
```

## Security Notes

- Passwords are hashed with SHA-256 and a unique salt per user
- Session tokens are generated using `secrets.token_hex()`
- Privileges are checked for every database operation
- Admin users have full access to all databases and tables

## Testing

Run automated tests:
```bash
python tests/test_client.py
```

## License

MIT