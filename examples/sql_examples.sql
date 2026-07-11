-- KosDB v3.2.0 SQL Examples
-- Comprehensive examples of all new features

-- ============================================
-- 1. DATABASE SETUP
-- ============================================

-- Create database
CREATE DATABASE ecommerce;
USE ecommerce;

-- ============================================
-- 2. CHECK CONSTRAINTS
-- ============================================

-- Create table with CHECK constraints
CREATE TABLE products (
    id INT PRIMARY KEY,
    name TEXT NOT NULL,
    price FLOAT CHECK (price > 0),
    quantity INT CHECK (quantity >= 0),
    status TEXT CHECK (status IN ('active', 'discontinued')),
    discount FLOAT CHECK (discount >= 0 AND discount <= 100),
    
    -- Table-level CHECK constraint
    CHECK (price * (1 - discount/100) >= 0)
);

-- Valid inserts
INSERT INTO products VALUES (1, 'Laptop', 999.99, 50, 'active', 10);
INSERT INTO products VALUES (2, 'Mouse', 29.99, 100, 'active', 0);
INSERT INTO products VALUES (3, 'Monitor', 299.99, 25, 'active', 15);

-- Invalid inserts (will fail)
-- INSERT INTO products VALUES (4, 'Invalid', -10, 10, 'active', 0);  -- Negative price
-- INSERT INTO products VALUES (5, 'Invalid', 100, -5, 'active', 0);   -- Negative quantity
-- INSERT INTO products VALUES (6, 'Invalid', 100, 10, 'unknown', 0); -- Invalid status

-- ============================================
-- 3. FOREIGN KEYS
-- ============================================

-- Create parent table
CREATE TABLE categories (
    id INT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

-- Create child table with foreign key
CREATE TABLE products_fk (
    id INT PRIMARY KEY,
    name TEXT NOT NULL,
    category_id INT REFERENCES categories(id) ON DELETE SET NULL,
    price FLOAT CHECK (price > 0)
);

-- Insert parent data first
INSERT INTO categories VALUES (1, 'Electronics', 'Electronic devices');
INSERT INTO categories VALUES (2, 'Books', 'Physical and digital books');

-- Insert child data
INSERT INTO products_fk VALUES (1, 'Laptop', 1, 999.99);
INSERT INTO products_fk VALUES (2, 'Programming Book', 2, 49.99);

-- This will fail (category 999 doesn't exist)
-- INSERT INTO products_fk VALUES (3, 'Invalid', 999, 100);

-- ============================================
-- 4. ALTER TABLE OPERATIONS
-- ============================================

-- Create base table
CREATE TABLE customers (
    id INT PRIMARY KEY,
    name TEXT NOT NULL
);

INSERT INTO customers VALUES (1, 'Alice');
INSERT INTO customers VALUES (2, 'Bob');

-- ADD COLUMN
ALTER TABLE customers ADD COLUMN email TEXT;
ALTER TABLE customers ADD COLUMN phone TEXT;
ALTER TABLE customers ADD COLUMN status TEXT DEFAULT 'active';

-- Verify columns added
SELECT * FROM customers;

-- RENAME COLUMN
ALTER TABLE customers RENAME COLUMN name TO full_name;

-- MODIFY COLUMN type
ALTER TABLE customers MODIFY COLUMN phone VARCHAR(20);

-- ADD INDEX
ALTER TABLE customers ADD INDEX idx_email (email);
ALTER TABLE customers ADD INDEX idx_status (status);

-- ADD CONSTRAINT
ALTER TABLE customers ADD CONSTRAINT chk_email CHECK (email LIKE '%@%');

-- DROP COLUMN (with CASCADE to remove dependent objects)
ALTER TABLE customers DROP COLUMN phone CASCADE;

-- DROP INDEX
ALTER TABLE customers DROP INDEX idx_email;

-- DROP CONSTRAINT
ALTER TABLE customers DROP CONSTRAINT chk_email;

-- ============================================
-- 5. VIEWS
-- ============================================

-- Create orders table
CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_id INT NOT NULL,
    total FLOAT CHECK (total > 0),
    status TEXT CHECK (status IN ('pending', 'shipped', 'delivered')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO orders VALUES (1, 1, 150.00, 'delivered', '2024-01-10');
INSERT INTO orders VALUES (2, 1, 75.50, 'shipped', '2024-01-12');
INSERT INTO orders VALUES (3, 2, 200.00, 'pending', '2024-01-15');

-- Create view for completed orders
CREATE VIEW completed_orders AS
SELECT * FROM orders WHERE status = 'delivered';

-- Query the view
SELECT * FROM completed_orders;

-- Create view with join
CREATE VIEW customer_orders AS
SELECT 
    c.full_name,
    o.id as order_id,
    o.total,
    o.status
FROM customers c
JOIN orders o ON c.id = o.customer_id;

-- Query the view
SELECT * FROM customer_orders;

-- Show all views
SHOW VIEWS;

-- Drop view
DROP VIEW completed_orders;

-- ============================================
-- 6. SUBQUERIES
-- ============================================

-- Scalar subquery in SELECT
SELECT 
    full_name,
    (SELECT COUNT(*) FROM orders WHERE customer_id = customers.id) as order_count
FROM customers;

-- Scalar subquery in WHERE
SELECT * FROM products
WHERE price > (SELECT AVG(price) FROM products);

-- IN subquery
SELECT * FROM customers
WHERE id IN (SELECT customer_id FROM orders WHERE total > 100);

-- NOT IN subquery
SELECT * FROM customers
WHERE id NOT IN (SELECT customer_id FROM orders);

-- EXISTS subquery
SELECT * FROM customers c
WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id);

-- NOT EXISTS subquery
SELECT * FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id);

-- Correlated subquery
SELECT 
    full_name,
    (SELECT MAX(total) FROM orders WHERE customer_id = customers.id) as max_order
FROM customers;

-- ============================================
-- 7. JSON SUPPORT
-- ============================================

-- Create table with JSON column
CREATE TABLE events (
    id INT PRIMARY KEY,
    event_type TEXT,
    event_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert JSON data
INSERT INTO events VALUES (1, 'click', '{"x": 100, "y": 200, "target": "buy_button"}');
INSERT INTO events VALUES (2, 'purchase', '{"amount": 99.99, "currency": "USD", "items": [{"id": 1, "qty": 2}]}');
INSERT INTO events VALUES (3, 'page_view', '{"url": "/products", "referrer": "google"}');

-- Query with JSON extraction
SELECT id, event_type, event_data->target FROM events WHERE event_type = 'click';
SELECT id, event_type, event_data->>amount FROM events WHERE event_type = 'purchase';

-- Filter by JSON value
SELECT * FROM events WHERE event_data->>currency = 'USD';

-- ============================================
-- 8. FULL-TEXT SEARCH
-- ============================================

-- Create articles table
CREATE TABLE articles (
    id INT PRIMARY KEY,
    title TEXT,
    content TEXT,
    author TEXT
);

-- Insert sample data
INSERT INTO articles VALUES 
    (1, 'Introduction to Databases', 'Databases are essential for...', 'Alice'),
    (2, 'SQL Optimization Tips', 'Optimizing SQL queries requires...', 'Bob'),
    (3, 'Database Security', 'Securing your database is...', 'Alice');

-- Create full-text index
CREATE FULLTEXT INDEX idx_content ON articles(content);

-- Natural language search
SELECT * FROM articles WHERE MATCH(content) AGAINST('database');

-- Boolean mode search
SELECT * FROM articles WHERE MATCH(content) AGAINST('+SQL -security' IN BOOLEAN MODE);

-- With query expansion
SELECT * FROM articles WHERE MATCH(content) AGAINST('optimization' WITH QUERY EXPANSION);

-- ============================================
-- 9. TRANSACTIONS
-- ============================================

BEGIN;

INSERT INTO orders VALUES (4, 1, 50.00, 'pending', CURRENT_TIMESTAMP);
INSERT INTO orders VALUES (5, 2, 150.00, 'pending', CURRENT_TIMESTAMP);

-- Commit or rollback
COMMIT;
-- Or: ROLLBACK;

-- ============================================
-- 10. QUERY OPTIMIZATION
-- ============================================

-- EXPLAIN query plan
EXPLAIN SELECT * FROM products WHERE price > 100;

EXPLAIN SELECT * FROM customers 
WHERE id IN (SELECT customer_id FROM orders WHERE total > 100);

-- Show plan cache statistics
EXPLAIN CACHE;

-- ============================================
-- 11. BACKUP AND RESTORE
-- ============================================

-- Create backup
BACKUP DATABASE ecommerce TO '/backups/ecommerce.backup';

-- Create encrypted backup
BACKUP DATABASE ecommerce TO '/backups/ecommerce.backup' 
WITH ENCRYPTION 'my-secret-key';

-- Restore from backup
RESTORE DATABASE ecommerce FROM '/backups/ecommerce.backup';

-- Restore with encryption
RESTORE DATABASE ecommerce FROM '/backups/ecommerce.backup' 
WITH ENCRYPTION 'my-secret-key';

-- ============================================
-- 12. USER MANAGEMENT
-- ============================================

-- Create users
CREATE USER admin PASSWORD 'admin123';
CREATE USER analyst PASSWORD 'analyst123';

-- Grant privileges
GRANT ALL ON ecommerce.* TO admin;
GRANT SELECT ON ecommerce.* TO analyst;
GRANT INSERT, UPDATE ON ecommerce.orders TO analyst;

-- Show grants
SHOW GRANTS FOR admin;
SHOW GRANTS FOR analyst;

-- Revoke privileges
REVOKE INSERT ON ecommerce.orders FROM analyst;

-- Create role
CREATE ROLE readonly DESCRIPTION 'Read-only database access';
GRANT SELECT ON ecommerce.* TO readonly;
GRANT ROLE readonly TO analyst;

-- Show roles
SHOW ROLES;

-- ============================================
-- 13. CLEANUP
-- ============================================

-- Drop objects
DROP VIEW IF EXISTS customer_orders;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS products_fk;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS articles;

-- Drop database
-- DROP DATABASE ecommerce;
