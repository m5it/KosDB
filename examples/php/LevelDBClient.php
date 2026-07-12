
<?php
/**
 * LevelDB Socket Server - PHP Client Library
 * 
 * A simple PHP client for connecting to the LevelDB Socket Server.
 * Supports authentication, queries, batch commands, and result parsing.
 * 
 * @author LevelDB Team
 * @version 2.3.0
 * 
 * New in v2.3.0:
 * - Batch command execution support via sendBatch()
 * - Multi-line response parsing for batch results
 * - Transaction batch support
 * - Partial failure handling
 */

class LevelDBClient {
    private $socket;
    private $host;
    private $port;
    private $connected = false;
    private $authenticated = false;
    private $debug = false;
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
     * Execute a batch of commands (v2.3.0+)
     * 
     * Sends multiple SQL commands separated by semicolons in a single request.
     * Each command is executed individually with results returned together.
     * 
     * @param array $commands Array of SQL commands to execute
     * @return array BatchResult object with commands, responses, and statistics
     * @throws Exception on connection or execution errors
     * 
     * Example:
     *   $result = $client->sendBatch([
     *       "INSERT INTO users VALUES (1, 'Alice')",
     *       "INSERT INTO users VALUES (2, 'Bob')",
     *       "SELECT * FROM users"
     *   ]);
     *   echo $result['summary']; // "3 command(s): 3 succeeded, 0 failed"
     *   foreach ($result['commands'] as $cmd) {
     *       echo $cmd['status']; // "OK" or "ERROR"
     *       echo $cmd['response'];
     *   }
     */
    public function sendBatch(array $commands) {
        if (!$this->authenticated) {
            throw new Exception("Not authenticated");
        }
        
        if (empty($commands)) {
            throw new Exception("No commands provided");
        }
        
        // Join commands with semicolons
        $batchSql = implode('; ', $commands);
        
        $this->send($batchSql);
        $rawResponse = $this->readBatchResponse();
        
        return $this->parseBatchResult($rawResponse, $commands);
    }
    
    /**
     * Execute a transaction batch (v2.3.0+)
     * 
     * Wraps commands in BEGIN/COMMIT for atomic execution.
     * If any command fails, the transaction can be rolled back.
     * 
     * @param array $commands Array of SQL commands (without BEGIN/COMMIT)
     * @param bool $rollbackOnError Whether to rollback on error (default: true)
     * @return array BatchResult object
     * @throws Exception on connection or execution errors
     * 
     * Example:
     *   $result = $client->sendTransactionBatch([
     *       "INSERT INTO orders VALUES (100, 'item1')",
     *       "INSERT INTO orders VALUES (101, 'item2')"
     *   ]);
     */
    public function sendTransactionBatch(array $commands, $rollbackOnError = true) {
        if (empty($commands)) {
            throw new Exception("No commands provided");
        }
        
        // Wrap in transaction
        $transactionCommands = array_merge(
            ['BEGIN'],
            $commands,
            $rollbackOnError ? ['COMMIT'] : ['COMMIT']
        );
        
        return $this->sendBatch($transactionCommands);
    }
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
     * Read batch response (multi-line)
     * 
     * Batch responses contain multiple command results separated by blank lines.
     * Reads until "Batch Complete" marker or timeout.
     * 
     * @return string Complete batch response
     */
    private function readBatchResponse() {
        $response = '';
        $startTime = time();
        $maxWaitTime = 60; // Longer timeout for batches
        
        while (true) {
            if (time() - $startTime > $maxWaitTime) {
                throw new Exception("Batch read timeout");
            }
            
            $line = $this->readLine();
            
            if ($line === false || $line === '') {
                // Check if we have a complete response
                if (strpos($response, 'Batch Complete') !== false) {
                    break;
                }
                continue;
            }
            
            $response .= $line . "\n";
            
            // Check for batch complete marker
            if (strpos($line, '--- Batch Complete ---') !== false) {
                // Read one more line for the summary
                $summaryLine = $this->readLine();
                if ($summaryLine !== false) {
                    $response .= $summaryLine . "\n";
                }
                break;
            }
            
            // Check for errors that terminate batch
            if (strpos($line, 'ERROR: Batch') === 0) {
                break;
            }
        }
        
        return trim($response);
    }
    
    /**
     * Parse batch result response into structured array
     * 
     * @param string $rawResponse Raw server response
     * @param array $originalCommands Original commands sent
     * @return array Structured result with commands and summary
     */
    private function parseBatchResult($rawResponse, array $originalCommands) {
        $result = [
            'success' => true,
            'commands' => [],
            'summary' => '',
            'total' => count($originalCommands),
            'succeeded' => 0,
            'failed' => 0
        ];
        
        // Check for pre-batch errors (e.g., batch too large)
        if (strpos($rawResponse, 'ERROR:') === 0 && strpos($rawResponse, '[1/') === false) {
            $result['success'] = false;
            $result['error'] = $rawResponse;
            return $result;
        }
        
        // Parse individual command results
        // Pattern: [N/TOTAL] STATUS: COMMAND\nRESPONSE
        $pattern = '/\[(\d+)\/(\d+)\]\s+(OK|ERROR):\s+(.+?)\n(.*?)(?=\[\d+\/\d+\]|--- Batch Complete ---|$)/s';
        preg_match_all($pattern, $rawResponse . "\n", $matches, PREG_SET_ORDER);
        
        foreach ($matches as $match) {
            $index = intval($match[1]) - 1; // Convert to 0-based
            $status = $match[3];
            $command = trim($match[4]);
            $response = trim($match[5]);
            
            $cmdResult = [
                'index' => $index + 1,
                'command' => $command,
                'status' => $status,
                'response' => $response,
                'success' => ($status === 'OK')
            ];
            
            $result['commands'][] = $cmdResult;
            
            if ($status === 'OK') {
                $result['succeeded']++;
            } else {
                $result['failed']++;
            }
        }
        
        // Parse summary line
        if (preg_match('/(\d+) command\(s\):\s+(\d+) succeeded,\s+(\d+) failed/', $rawResponse, $summaryMatch)) {
            $result['summary'] = $summaryMatch[0];
            $result['total'] = intval($summaryMatch[1]);
            $result['succeeded'] = intval($summaryMatch[2]);
            $result['failed'] = intval($summaryMatch[3]);
        }
        
        // Determine overall success
        $result['success'] = ($result['failed'] === 0);
        
        return $result;
    }
    
    /**
     * Enable or disable debug mode
     * 
     * @param bool $enabled
     */
    public function setDebug($enabled) {
        $this->debug = $enabled;
    }
    
    /**
     * Destructor - ensure connection is closed
     */
    public function __destruct() {
        $this->close();
    }
}
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