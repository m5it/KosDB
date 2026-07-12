
<?php
/**
 * KosDB Multi-Command Batch Example (PHP) - v2.3.0
 * 
 * This example demonstrates the batch command feature added in KosDB v2.3.0:
 * 
 * FEATURES:
 * - Execute multiple SQL commands in a single network request
 * - Transaction batch patterns (BEGIN...COMMIT/ROLLBACK)
 * - Error handling for partial failures
 * - Reading and parsing batch results
 * - Quoted semicolon handling (semicolons in strings don't split commands)
 * 
 * PERFORMANCE BENEFITS:
 * - Reduces network round-trips from N to 1
 * - Server-side command caching improves parsing speed
 * - Better for bulk operations (inserts, updates)
 * 
 * REQUIREMENTS:
 * - KosDB server v2.3.0+
 * - PHP 7.0+ with sockets extension
 */

require_once 'LevelDBClient.php';

/**
 * Demonstrates basic batch execution
 */
function demoBasicBatch($client) {
    echo "\n========================================\n";
    echo "Demo 1: Basic Batch Execution\n";
    echo "========================================\n";
    echo "Execute multiple commands in one request:\n\n";
    
    $commands = [
        "CREATE TABLE IF NOT EXISTS users (id INT, name TEXT)",
        "INSERT INTO users VALUES (1, 'Alice')",
        "INSERT INTO users VALUES (2, 'Bob')",
        "INSERT INTO users VALUES (3, 'Charlie')",
        "SELECT * FROM users ORDER BY id"
    ];
    
    try {
        $result = $client->sendBatch($commands);
        
        echo "Batch Summary: {$result['summary']}\n";
        echo "Total Commands: {$result['total']}\n";
        echo "Succeeded: {$result['succeeded']}\n";
        echo "Failed: {$result['failed']}\n\n";
        
        echo "Individual Results:\n";
        foreach ($result['commands'] as $cmd) {
            $statusIcon = $cmd['success'] ? '✓' : '✗';
            echo "  [$statusIcon] Command {$cmd['index']}: {$cmd['status']}\n";
            echo "      SQL: {$cmd['command']}\n";
            echo "      Response: " . substr($cmd['response'], 0, 50) . "...\n";
        }
        
        return $result['success'];
        
    } catch (Exception $e) {
        echo "ERROR: " . $e->getMessage() . "\n";
        return false;
    }
}

/**
 * Demonstrates transaction batch
 */
function demoTransactionBatch($client) {
    echo "\n========================================\n";
    echo "Demo 2: Transaction Batch\n";
    echo "========================================\n";
    echo "Atomic execution with BEGIN/COMMIT:\n\n";
    
    try {
        $result = $client->sendTransactionBatch([
            "CREATE TABLE IF NOT EXISTS orders (id INT, item TEXT)",
            "INSERT INTO orders VALUES (100, 'Laptop')",
            "INSERT INTO orders VALUES (101, 'Mouse')",
            "INSERT INTO orders VALUES (102, 'Keyboard')"
        ]);
        
        echo "Transaction Result: " . ($result['success'] ? 'SUCCESS' : 'PARTIAL FAILURE') . "\n";
        echo $result['summary'] . "\n";
        
        // Verify data was inserted
        $verify = $client->query("SELECT * FROM orders");
        echo "\nVerified Orders: " . count($verify) . " rows inserted\n";
        
        return $result['success'];
        
    } catch (Exception $e) {
        echo "ERROR: " . $e->getMessage() . "\n";
        return false;
    }
}

/**
 * Demonstrates error handling with partial failures
 */
function demoPartialFailure($client) {
    echo "\n========================================\n";
    echo "Demo 3: Partial Failure Handling\n";
    echo "========================================\n";
    echo "Some commands fail, others succeed:\n\n";
    
    $commands = [
        "SELECT * FROM users",                          // Should succeed
        "INSERT INTO nonexistent_table VALUES (1)",     // Should fail
        "SELECT * FROM users WHERE id = 999",           // Should succeed (empty)
        "INVALID SQL SYNTAX HERE",                       // Should fail
        "SELECT COUNT(*) FROM users"                    // Should succeed
    ];
    
    try {
        $result = $client->sendBatch($commands);
        
        echo "Overall Success: " . ($result['success'] ? 'YES' : 'NO (partial failures)') . "\n";
        echo $result['summary'] . "\n\n";
        
        echo "Detailed Results:\n";
        foreach ($result['commands'] as $cmd) {
            $icon = $cmd['success'] ? '✓' : '✗';
            echo "  [$icon] [{$cmd['status']}] {$cmd['command']}\n";
            if (!$cmd['success']) {
                echo "      Error: {$cmd['response']}\n";
            }
        }
        
        return true;
        
    } catch (Exception $e) {
        echo "ERROR: " . $e->getMessage() . "\n";
        return false;
    }
}

/**
 * Demonstrates quoted semicolons (not command separators)
 */
function demoQuotedSemicolons($client) {
    echo "\n========================================\n";
    echo "Demo 4: Quoted Semicolons\n";
    echo "========================================\n";
    echo "Semicolons inside strings don't split:\n\n";
    
    try {
        $result = $client->sendBatch([
            "CREATE TABLE IF NOT EXISTS logs (id INT, message TEXT)",
            "INSERT INTO logs VALUES (1, 'Error: connection failed; retrying')",
            "INSERT INTO logs VALUES (2, 'Warning: timeout; aborting')",
            "SELECT * FROM logs"
        ]);
        
        echo "Result: {$result['summary']}\n";
        
        // Show the data
        $logs = $client->query("SELECT * FROM logs");
        echo "\nLogs with semicolons in messages:\n";
        foreach ($logs as $log) {
            echo "  ID {$log['id']}: {$log['message']}\n";
        }
        
        return $result['success'];
        
    } catch (Exception $e) {
        echo "ERROR: " . $e->getMessage() . "\n";
        return false;
    }
}

/**
 * Demonstrates bulk insert performance
 */
function demoBulkInsert($client) {
    echo "\n========================================\n";
    echo "Demo 5: Bulk Insert Performance\n";
    echo "========================================\n";
    echo "Insert 10 records in one batch vs individual:\n\n";
    
    $commands = [];
    for ($i = 1; $i <= 10; $i++) {
        $commands[] = "INSERT INTO users VALUES ($i, 'User$i')";
    }
    
    // Time the batch insert
    $start = microtime(true);
    try {
        $result = $client->sendBatch($commands);
        $batchTime = (microtime(true) - $start) * 1000;
        
        echo "Batch insert: {$result['succeeded']}/{$result['total']} rows in {$batchTime}ms\n";
        
        // Compare with individual inserts (simulated)
        echo "\nNote: Individual inserts would require 10 network round-trips\n";
        echo "      Batch insert uses only 1 network round-trip\n";
        
        return $result['success'];
        
    } catch (Exception $e) {
        echo "ERROR: " . $e->getMessage() . "\n";
        return false;
    }
}

// Main execution
echo "KosDB PHP Batch Commands Demo\n";
echo "==============================\n";
echo "Server: localhost:9999\n";
echo "Requires: KosDB v2.3.0+\n\n";

try {
    // Create client
    $client = new LevelDBClient('localhost', 9999);
    
    // Connect
    echo "Connecting... ";
    $client->connect();
    echo "OK\n";
    
    // Authenticate
    echo "Authenticating... ";
    $client->authenticate('admin', 'admin');
    echo "OK\n";
    
    // Run demos
    $results = [];
    $results[] = demoBasicBatch($client);
    $results[] = demoTransactionBatch($client);
    $results[] = demoPartialFailure($client);
    $results[] = demoQuotedSemicolons($client);
    $results[] = demoBulkInsert($client);
    
    // Cleanup
    echo "\n========================================\n";
    echo "Cleaning up test tables...\n";
    $client->execute("DROP TABLE IF EXISTS users");
    $client->execute("DROP TABLE IF EXISTS orders");
    $client->execute("DROP TABLE IF EXISTS logs");
    
    // Close connection
    $client->close();
    
    // Summary
    $passed = count(array_filter($results));
    $total = count($results);
    
    echo "\n========================================\n";
    echo "Demo Complete: $passed/$total demos successful\n";
    echo "========================================\n";
    
    exit($passed === $total ? 0 : 1);
    
} catch (Exception $e) {
    echo "\nFATAL ERROR: " . $e->getMessage() . "\n";
    exit(1);
}
        if (!$result) {
            throw new Exception("Failed to connect: " . socket_strerror(socket_last_error($this->socket)));
        }
        
        // Read welcome message
        $welcome = socket_read($this->socket, 4096);
        echo "Server: " . trim($welcome) . "\n";
        
        return true;
    }
    
    /**
     * Authenticate with server
     */
    public function authenticate($username, $password) {
        // Send USER
        socket_write($this->socket, "USER $username\n");
        $response = socket_read($this->socket, 4096);
        echo "USER response: " . trim($response) . "\n";
        
        // Send PASS
        socket_write($this->socket, "PASS $password\n");
        $response = socket_read($this->socket, 4096);
        echo "PASS response: " . trim($response) . "\n";
        
        if (strpos($response, "OK") !== 0) {
            throw new Exception("Authentication failed");
        }
        
        return true;
    }
    
    /**
     * Execute batch of commands
     */
    public function executeBatch($commands) {
        echo "\nSending batch: " . substr($commands, 0, 50) . "...\n";
        
        socket_write($this->socket, $commands . "\n");
        
        // Read response (may be large)
        $response = '';
        while ($buf = socket_read($this->socket, 8192)) {
            $response .= $buf;
            if (strlen($buf) < 8192) break;
        }
        
        return $response;
    }
    
    /**
     * Close connection
     */
    public function disconnect() {
        if ($this->socket) {
            socket_close($this->socket);
            $this->socket = null;
        }
    }
}

// Example usage
try {
    $client = new KosDBBatchClient('localhost', 9999);
    $client->connect();
    $client->authenticate('admin', 'admin');
    
    // Example 1: Basic batch
    echo "========================================\n";
    echo "Example 1: Basic Batch\n";
    echo "========================================\n";
    
    $batch1 = "CREATE TABLE users (id, name); " .
              "INSERT INTO users VALUES (1, 'Alice'); " .
              "INSERT INTO users VALUES (2, 'Bob'); " .
              "SELECT * FROM users";
    
    $result = $client->executeBatch($batch1);
    echo "Batch Result:\n$result\n";
    
    // Example 2: Transaction batch
    echo "\n========================================\n";
    echo "Example 2: Transaction Batch\n";
    echo "========================================\n";
    
    $batch2 = "BEGIN; " .
              "INSERT INTO orders VALUES (100, 'laptop'); " .
              "INSERT INTO orders VALUES (101, 'mouse'); " .
              "COMMIT";
    
    $result = $client->executeBatch($batch2);
    echo "Batch Result:\n$result\n";
    
    // Example 3: Batch with quoted semicolons
    echo "\n========================================\n";
    echo "Example 3: Quoted Semicolons\n";
    echo "========================================\n";
    
    $batch3 = "INSERT INTO logs VALUES ('Error: connection; timeout'); " .
              "INSERT INTO logs VALUES ('Warning: retry; attempt 1'); " .
              "SELECT * FROM logs";
    
    $result = $client->executeBatch($batch3);
    echo "Batch Result:\n$result\n";
    
    $client->disconnect();
    echo "\nDone!\n";
    
} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
    exit(1);
}
?>
