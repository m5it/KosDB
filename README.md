# LevelDB Socket Server

A threaded Python socket server providing a MySQL-like command interface over LevelDB backend.

## Features

- **Threaded TCP Socket Server** - Handles multiple concurrent clients
- **Authentication** - 
- **LevelDB Backend** - Persistent key-value storage with table namespacing
- **SQL-like Commands** - CREATE, DROP, INSERT, SELECT, UPDATE, DELETE
- **Netcat Compatible** - Test with standard netcat client

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Start the Server

```bash
python server.py --prepare_admin admin --prepare_password yourpwd
python server.py
```

Server will start on port 9999 with default settings.

### Connect with Netcat

```bash
nc localhost 9999
```

### Authentication

```
Welcome to LevelDB Socket Server
Authentication required
Format: USER <username>, then PASS <password>
--------------------------------------------------

USER admin
| Command | Description |
|---------|-------------|
| `SHOW DATABASES` | List all databases |
| `CREATE DATABASE <name>` | Create a new database |
| `DROP DATABASE <name>` | Delete a database |
| `USE <database>` | Select database to use |
| `SHOW TABLES` | List tables in current database |
| `CREATE TABLE <name> (cols...)` | Create a new table |
| Command | Description |
|---------|-------------|
| `CREATE DATABASE <name>` | Create a new database |
| `DROP DATABASE <name>` | Delete a database |
| `USE <database>` | Select database to use |
| `CREATE TABLE <name> (cols...)` | Create a new table |
| `DROP TABLE <name>` | Delete a table |
| `INSERT INTO <table> VALUES (val...)` | Insert a record |
| `SELECT * FROM <table>` | Select all records |
| `SELECT col FROM <table> WHERE cond` | Select specific records |
| `UPDATE <table> SET col=val WHERE...` | Update records |
| `DELETE FROM <table> WHERE cond` | Delete records |
| `SHOW TABLES` | List tables |
| `HELP` | Show help |
| `QUIT` / `EXIT` | Disconnect |

### Example Session

```
> CREATE DATABASE testdb
OK: Database 'testdb' created

> USE testdb
OK: Using database 'testdb'

> CREATE TABLE users (id INT, name TEXT)
OK: Table 'users' created

> INSERT INTO users VALUES (1, 'John')
OK: Inserted into 'users'

> INSERT INTO users VALUES (2, 'Jane')
OK: Inserted into 'users'

> SELECT * FROM users
OK:
{'id': 1, 'name': 'John'}
{'id': 2, 'name': 'Jane'}

> SELECT name FROM users WHERE id=1
OK:
{'name': 'John'}

> UPDATE users SET name='Johnny' WHERE id=1
OK: Updated 1 record(s) in 'users'

> DELETE FROM users WHERE id=2
OK: Deleted 1 record(s) from 'users'

> DROP TABLE users
OK: Table 'users' dropped

> DROP DATABASE testdb
OK: Database 'testdb' dropped
```

## Testing

Run automated tests:
```bash
python tests/test_client.py
```

## Project Structure

```
t10/
├── server.py           # Main server entry point
├── database.py         # LevelDB wrapper
├── auth.py            # Authentication system
├── parser.py          # SQL command parser
├── commands.py        # Command execution framework
├── tests/
│   └── test_client.py  # Test client
├── requirements.txt    # Dependencies
└── README.md          # Documentation
```

## Configuration

Default settings in `server.py`:
- Host: 0.0.0.0
- Port: 9999
- Database: ./data.db

## License

MIT
