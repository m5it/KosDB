# LevelDB Socket Server

A threaded Python socket server providing a MySQL-like command interface over LevelDB backend with database-backed authentication, privilege management, and replication.

## Features

- **Threaded TCP Socket Server** - Handles multiple concurrent clients
- **Database-Backed Authentication** - User accounts stored in LevelDB with hashed passwords
- **Privilege System** - Role-based access control (admin/users) with database/table-level permissions
- **Admin User Management** - Create admin users via command line
- **Binary Log (Binlog)** - All writes logged for replication
- **Master-Slave Replication** - One master, multiple slaves
- **Master-Master Replication** - Bi-directional replication between peers
- **Automatic Recovery** - Slaves reconnect and catch up on missed data
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

## Replication Setup

### Master-Slave Replication

**Start Master:**
```bash
python server.py --server-id 1 --role master --replication-port 10999 --data_dir ./data_master
```

**Create Replication User on Master:**
```sql
CREATE REPLICATION USER 'repl' IDENTIFIED BY 'replpass';
```

**Start Slave:**
```bash
python server.py --server-id 2 --role slave --master-host localhost:9999 --data_dir ./data_slave
```

### Master-Master Replication

**Server A:**
```bash
python server.py --server-id 1 --port 9999 --replication-port 10999 --peer-host localhost:9998 --data_dir ./data_a
```

**Server B:**
```bash
python server.py --server-id 2 --port 9998 --replication-port 10998 --peer-host localhost:9999 --data_dir ./data_b
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

### Replication Commands (Admin Only)
| Command | Description |
|---------|-------------|
| `SHOW MASTER STATUS` | Show binlog position and connected slaves |
| `SHOW SLAVE STATUS` | Show replication status and lag |
| `START SLAVE` | Start replication |
| `STOP SLAVE` | Stop replication |
| `RESET SLAVE` | Reset replication position |
| `CREATE REPLICATION USER <name> IDENTIFIED BY <pass>` | Create replication user |

### Admin Commands
| Command | Description |
|---------|-------------|
| `SHOW USERS` | List all users |
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

### Replication Commands
```
> SHOW MASTER STATUS
--------------------------------------------------
Master Status
--------------------------------------------------
Binlog Position: 150
Server ID: 1
Connected Slaves: 1
--------------------------------------------------

> SHOW SLAVE STATUS
--------------------------------------------------
Slave Status
--------------------------------------------------
Slave IO State: Connected
Master Host: localhost
Master Port: 9999
Last Applied Position: 150
Master Binlog Position: 150
--------------------------------------------------
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

## Command-Line Options

```
usage: server.py [-h] [--prepare_admin USER] [--prepare_password PASS]
                 [--host HOST] [--port PORT] [--data_dir DATA_DIR]
                 [--server-id SERVER_ID] [--role {master,slave}]
                 [--master-host HOST:PORT] [--replication-port PORT]
                 [--peer-host HOST:PORT]

LevelDB Socket Server with Replication

optional arguments:
  -h, --help            show this help message and exit
  --prepare_admin USER  Create admin user
  --prepare_password PASS
                        Admin password
  --host HOST           Client host (default: 0.0.0.0)
  --port PORT           Client port (default: 9999)
  --data_dir DATA_DIR   Data directory (default: ./data)
  --server-id SERVER_ID
                        Unique server ID (default: 1)
  --role {master,slave}
                        Server role: master or slave (default: master)
  --master-host HOST:PORT
                        Master host:port for slave replication
  --replication-port PORT
                        Port for replication connections (optional)
  --peer-host HOST:PORT
                        Peer host:port for master-master replication
```

## Project Structure

```
t10/
├── server.py              # Main server entry point
├── database.py            # LevelDB wrapper with binlog integration
├── auth.py               # Session-based authentication
├── binlog.py             # Binary log for replication
├── replication.py        # Replication client/server
├── replication_commands.py  # Replication control commands
├── parser.py             # SQL command parser
├── commands.py           # Command execution framework
├── tests/
│   ├── test_client.py    # Basic client tests
│   └── test_replication.py  # Replication tests
├── TESTING.md           # Testing documentation
├── requirements.txt      # Dependencies
└── README.md            # Documentation
```

## Configuration

Default settings:
- **Host**: 0.0.0.0
- **Port**: 9999
- **Data Directory**: ./data
- **System Database**: ./_system (stores users and privileges)
- **Binlog**: ./_binlog (replication log)

## Replication Architecture

### Master-Slave
```
[Master] <--writes-- [Client]
    |
    | binlog stream
    v
[Slave] <--reads-- [Client]
```

### Master-Master
```
[Server A] <----> [Server B]
   ^                   ^
   |                   |
writes              writes
```

## Security Notes

- Passwords are hashed with SHA-256 and a unique salt per user
- Session tokens are generated using `secrets.token_hex()`
- Privileges are checked for every database operation
- Admin users have full access to all databases and tables
- Replication users can only stream binlog (no query access)

## Testing

Run automated tests:
```bash
python tests/test_client.py
python tests/test_replication.py
```

See [TESTING.md](TESTING.md) for detailed testing procedures.

## License

MIT