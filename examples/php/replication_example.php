<?php
/**
 * LevelDB PHP Client - Replication Example
 * 
 * This example demonstrates working with replication features.
 */

require_once 'LevelDBClient.php';

try {
    // Connect to master server
    echo "Connecting to MASTER server...\n";
    $master = new LevelDBClient('localhost', 9999);
    $master->connect();
    $master->authenticate('admin', 'admin');
    echo "Connected to master!\n\n";
    
    // Create replication user on master
    echo "Creating replication user on master...\n";
    echo $master->execute("CREATE REPLICATION USER 'repl' IDENTIFIED BY 'replpass'") . "\n\n";
    
    // Show master status
    echo "Master Status:\n";
    echo $master->showMasterStatus() . "\n\n";
    
    // Create test database on master
    echo "Creating test database on master...\n";
    echo $master->createDatabase('replication_test') . "\n";
    echo $master->useDatabase('replication_test') . "\n";
    echo $master->createTable('sync_data', ['id INT PRIMARY KEY', 'message TEXT', 'timestamp TEXT']) . "\n\n";
    
    // Connect to slave server
    echo "Connecting to SLAVE server...\n";
    $slave = new LevelDBClient('localhost', 9998);  // Slave on different port
    $slave->connect();
    $slave->authenticate('admin', 'admin');
    echo "Connected to slave!\n\n";
    
    // Show slave status
    echo "Slave Status:\n";
    echo $slave->showSlaveStatus() . "\n\n";
    
    // Insert data on master
    echo "Inserting data on MASTER...\n";
    $time = date('Y-m-d H:i:s');
    echo $master->insert('sync_data', [1, 'Hello from master!', $time]) . "\n";
    echo $master->insert('sync_data', [2, 'This will replicate', $time]) . "\n\n";
    
    // Wait a moment for replication
    echo "Waiting for replication (3 seconds)...\n";
    sleep(3);
    
    // Check data on slave
    echo "\nChecking data on SLAVE:\n";
    $slave->useDatabase('replication_test');
    $data = $slave->select('sync_data');
    foreach ($data as $row) {
        echo "ID: {$row['id']}, Message: {$row['message']}, Time: {$row['timestamp']}\n";
    }
    echo "\n";
    
    // Insert more data
    echo "Inserting more data on master...\n";
    $time = date('Y-m-d H:i:s');
    echo $master->insert('sync_data', [3, 'Replication is working!', $time]) . "\n\n";
    
    // Wait again
    echo "Waiting for replication (3 seconds)...\n";
    sleep(3);
    
    // Check again on slave
    echo "\nAll data on SLAVE:\n";
    $data = $slave->select('sync_data');
    foreach ($data as $row) {
        echo "ID: {$row['id']}, Message: {$row['message']}\n";
    }
    
    // Clean up
    echo "\nCleaning up...\n";
    echo $master->dropTable('sync_data') . "\n";
    echo $master->dropDatabase('replication_test') . "\n";
    
    // Close connections
    $master->close();
    $slave->close();
    
    echo "\nReplication test completed!\n";
    
} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
    exit(1);
}