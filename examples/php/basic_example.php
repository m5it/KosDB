<?php
/**
 * LevelDB PHP Client - Basic Usage Example
 * 
 * This example demonstrates basic CRUD operations using the LevelDBClient.
 */

require_once 'LevelDBClient.php';

try {
    // Create client instance
    $db = new LevelDBClient('localhost', 9999);
    
    // Connect to server
    echo "Connecting to server...\n";
    $db->connect();
    
    // Authenticate
    echo "Authenticating...\n";
    $db->authenticate('admin', 'admin');
    echo "Authenticated successfully!\n\n";
    
    // Create a database
    echo "Creating database 'myapp'...\n";
    echo $db->createDatabase('myapp') . "\n\n";
    
    // Use the database
    echo "Selecting database 'myapp'...\n";
    echo $db->useDatabase('myapp') . "\n\n";
    
    // Create a table
    echo "Creating table 'users'...\n";
    echo $db->createTable('users', [
        'id INT PRIMARY KEY',
        'name TEXT',
        'email TEXT',
        'age INT'
    ]) . "\n\n";
    
    // Insert some data
    echo "Inserting users...\n";
    echo $db->insert('users', [1, 'John Doe', 'john@example.com', 30]) . "\n";
    echo $db->insert('users', [2, 'Jane Smith', 'jane@example.com', 25]) . "\n";
    echo $db->insert('users', [3, 'Bob Wilson', 'bob@example.com', 35]) . "\n\n";
    
    // Select all users
    echo "Selecting all users:\n";
    $users = $db->select('users');
    foreach ($users as $user) {
        print_r($user);
    }
    echo "\n";
    
    // Select with WHERE clause
    echo "Selecting users where age > 25:\n";
    $users = $db->select('users', 'age=30');
    foreach ($users as $user) {
        print_r($user);
    }
    echo "\n";
    
    // Select with ORDER BY
    echo "Selecting all users ordered by name DESC:\n";
    $users = $db->select('users', null, 'name', true);
    foreach ($users as $user) {
        print_r($user);
    }
    echo "\n";
    
    // Update a user
    echo "Updating user 1...\n";
    echo $db->update('users', "name='Johnny Doe'", 'id=1') . "\n\n";
    
    // Verify update
    echo "Selecting user 1 after update:\n";
    $users = $db->select('users', 'id=1');
    print_r($users[0] ?? 'Not found');
    echo "\n\n";
    
    // Delete a user
    echo "Deleting user 3...\n";
    echo $db->delete('users', 'id=3') . "\n\n";
    
    // Show remaining users
    echo "Remaining users:\n";
    $users = $db->select('users');
    foreach ($users as $user) {
        print_r($user);
    }
    echo "\n";
    
    // List databases
    echo "Databases:\n";
    $databases = $db->listDatabases();
    print_r($databases);
    echo "\n";
    
    // List tables
    echo "Tables:\n";
    $tables = $db->listTables();
    print_r($tables);
    echo "\n";
    
    // Show master status (replication)
    echo "Master Status:\n";
    echo $db->showMasterStatus() . "\n\n";
    
    // Clean up - drop table and database
    echo "Cleaning up...\n";
    echo $db->dropTable('users') . "\n";
    echo $db->dropDatabase('myapp') . "\n";
    
    // Close connection
    $db->close();
    echo "\nConnection closed.\n";
    
} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
    exit(1);
}