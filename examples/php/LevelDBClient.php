<?php
/**
 * LevelDB Socket Server - PHP Client Library
 * 
 * A simple PHP client for connecting to the LevelDB Socket Server.
 * Supports authentication, queries, and result parsing.
 * 
 * @author LevelDB Team
 * @version 1.0.0
 */

class LevelDBClient {
    private $socket;
    private $host;
    private $port;
    private $connected = false;
    private $authenticated = false;
    
    /**
     * Constructor
     * 
     * @param string $host Server hostname (default: localhost)
     * @param int $port Server port (default: 9999)
     */
    public function __construct($host = 'localhost', $port = 9999) {
        $this->host = $host;
        $this->port = $port;
    }
    
    /**
     * Connect to the LevelDB server
     * 
     * @return bool True on success
     * @throws Exception on connection failure
     */
    public function connect() {
        $this->socket = @fsockopen($this->host, $this->port, $errno, $errstr, 30);
        
        if (!$this->socket) {
            throw new Exception("Connection failed: $errstr ($errno)");
        }
        
        // Read welcome banner (6 lines)
        $this->readLines(6);
        
        $this->connected = true;
        return true;
    }
    
    /**
     * Authenticate with username and password
     * 
     * @param string $username
     * @param string $password
     * @return bool True on successful authentication
     * @throws Exception on auth failure
     */
    public function authenticate($username, $password) {
        if (!$this->connected) {
            throw new Exception("Not connected");
        }
        
        // Send USER command
        $this->send("USER $username");
        $response = $this->readLine();
        
        if (strpos($response, 'OK') === false) {
            throw new Exception("USER command failed: $response");
        }
        
        // Send PASS command
        $this->send("PASS $password");
        $response = $this->readLine();
        
        if (strpos($response, 'OK') === false) {
            throw new Exception("Authentication failed: $response");
        }
        
        $this->authenticated = true;
        return true;
    }
    
    /**
     * Execute a SQL-like command
     * 
     * @param string $sql The command to execute
     * @return string Raw response from server
     */
    public function execute($sql) {
        if (!$this->authenticated) {
            throw new Exception("Not authenticated");
        }
        
        $this->send($sql);
        return $this->readResponse();
    }
    
    /**
     * Execute a SELECT query and return parsed results
     * 
     * @param string $sql SELECT query
     * @return array Array of associative arrays representing rows
     */
    public function query($sql) {
        $result = $this->execute($sql);
        return $this->parseSelectResult($result);
    }
    
    /**
     * Create a database
     * 
     * @param string $name Database name
     * @return string Response from server
     */
    public function createDatabase($name) {
        return $this->execute("CREATE DATABASE $name");
    }
    
    /**
     * Drop a database
     * 
     * @param string $name Database name
     * @return string Response from server
     */
    public function dropDatabase($name) {
        return $this->execute("DROP DATABASE $name");
    }
    
    /**
     * Select database to use
     * 
     * @param string $name Database name
     * @return string Response from server
     */
    public function useDatabase($name) {
        return $this->execute("USE $name");
    }
    
    /**
     * Create a table
     * 
     * @param string $name Table name
     * @param array $columns Column definitions (e.g., ['id INT PRIMARY KEY', 'name TEXT'])
     * @return string Response from server
     */
    public function createTable($name, array $columns) {
        $cols = implode(', ', $columns);
        return $this->execute("CREATE TABLE $name ($cols)");
    }
    
    /**
     * Drop a table
     * 
     * @param string $name Table name
     * @return string Response from server
     */
    public function dropTable($name) {
        return $this->execute("DROP TABLE $name");
    }
    
    /**
     * Insert data into table
     * 
     * @param string $table Table name
     * @param array $values Values to insert
     * @return string Response from server
     */
    public function insert($table, array $values) {
        $vals = [];
        foreach ($values as $v) {
            if (is_string($v)) {
                $vals[] = "'" . addslashes($v) . "'";
            } else {
                $vals[] = $v;
            }
        }
        $valStr = implode(', ', $vals);
        return $this->execute("INSERT INTO $table VALUES ($valStr)");
    }
    
    /**
     * Select from table
     * 
     * @param string $table Table name
     * @param string|null $where Optional WHERE clause
     * @param string|null $orderBy Optional ORDER BY column
     * @param bool $desc Sort descending (default: false)
     * @return array Parsed results
     */
    public function select($table, $where = null, $orderBy = null, $desc = false) {
        $sql = "SELECT * FROM $table";
        
        if ($where) {
            $sql .= " WHERE $where";
        }
        
        if ($orderBy) {
            $sql .= " ORDER BY $orderBy";
            if ($desc) {
                $sql .= " DESC";
            }
        }
        
        return $this->query($sql);
    }
    
    /**
     * Update rows
     * 
     * @param string $table Table name
     * @param string $set SET clause (e.g., "name='New'")
     * @param string|null $where Optional WHERE clause
     * @return string Response from server
     */
    public function update($table, $set, $where = null) {
        $sql = "UPDATE $table SET $set";
        if ($where) {
            $sql .= " WHERE $where";
        }
        return $this->execute($sql);
    }
    
    /**
     * Delete rows
     * 
     * @param string $table Table name
     * @param string|null $where Optional WHERE clause
     * @return string Response from server
     */
    public function delete($table, $where = null) {
        $sql = "DELETE FROM $table";
        if ($where) {
            $sql .= " WHERE $where";
        }
        return $this->execute($sql);
    }
    
    /**
     * Show master status (replication)
     * 
     * @return string Response from server
     */
    public function showMasterStatus() {
        return $this->execute("SHOW MASTER STATUS");
    }
    
    /**
     * Show slave status (replication)
     * 
     * @return string Response from server
     */
    public function showSlaveStatus() {
        return $this->execute("SHOW SLAVE STATUS");
    }
    
    /**
     * List databases
     * 
     * @return array List of database names
     */
    public function listDatabases() {
        $result = $this->execute("SHOW DATABASES");
        // Parse result
        preg_match_all('/OK:\s*\n?((?:.|\n)*)/', $result, $matches);
        if (isset($matches[1][0])) {
            return array_filter(explode("\n", trim($matches[1][0])));
        }
        return [];
    }
    
    /**
     * List tables in current database
     * 
     * @return array List of table names
     */
    public function listTables() {
        $result = $this->execute("SHOW TABLES");
        preg_match_all('/OK:\s*\n?((?:.|\n)*)/', $result, $matches);
        if (isset($matches[1][0])) {
            return array_filter(explode("\n", trim($matches[1][0])));
        }
        return [];
    }
    
    /**
     * Close connection
     */
    public function close() {
        if ($this->socket) {
            $this->send("QUIT");
            fclose($this->socket);
            $this->socket = null;
            $this->connected = false;
            $this->authenticated = false;
        }
    }
    
    /**
     * Check if connected
     * 
     * @return bool
     */
    public function isConnected() {
        return $this->connected;
    }
    
    /**
     * Check if authenticated
     * 
     * @return bool
     */
    public function isAuthenticated() {
        return $this->authenticated;
    }
    
    // Private helper methods
    
    private function send($cmd) {
        fwrite($this->socket, $cmd . "\n");
    }
    
    private function readLine() {
        return trim(fgets($this->socket, 4096));
    }
    
    private function readLines($count) {
        $lines = [];
        for ($i = 0; $i < $count; $i++) {
            $lines[] = $this->readLine();
        }
        return $lines;
    }
    
    private function readResponse() {
        $response = '';
        $startTime = time();
        
        while (true) {
            // Timeout after 30 seconds
            if (time() - $startTime > 30) {
                throw new Exception("Read timeout");
            }
            
            $line = $this->readLine();
            
            if ($line === '') {
                continue;
            }
            
            $response .= $line . "\n";
            
            // Check for end markers
            if (strpos($line, 'OK:') === 0 || 
                strpos($line, 'ERROR:') === 0 ||
                strpos($line, 'BYE') === 0 ||
                strpos($line, 'row(s) in set') !== false ||
                strpos($line, 'Empty set') !== false) {
                break;
            }
        }
        
        return trim($response);
    }
    
    /**
     * Parse SELECT result into array of rows
     * 
     * @param string $text Raw response
     * @return array Parsed rows
     */
    private function parseSelectResult($text) {
        $lines = explode("\n", $text);
        $rows = [];
        $inTable = false;
        $headers = [];
        
        foreach ($lines as $line) {
            // Skip separator lines
            if (strpos($line, '+--') === 0 || strpos($line, '+-') === 0) {
                continue;
            }
            
            // Parse header row
            if (strpos($line, '| id') !== false && empty($headers)) {
                preg_match_all('/\|\s*(\w+)\s*/', $line, $matches);
                $headers = array_filter($matches[1]);
                $inTable = true;
                continue;
            }
            
            // Parse data row
            if ($inTable && strpos($line, '|') === 0) {
                preg_match_all('/\|\s*([^|]*)\s*/', $line, $matches);
                $values = array_map('trim', array_slice($matches[1], 1));
                
                if (count($values) >= count($headers)) {
                    $row = [];
                    foreach ($headers as $i => $header) {
                        $row[$header] = $values[$i] ?? null;
                    }
                    $rows[] = $row;
                }
            }
        }
        
        return $rows;
    }
    
    /**
     * Destructor - ensure connection is closed
     */
    public function __destruct() {
        $this->close();
    }
}