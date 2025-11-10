-- Lab 6: Views and User-Defined Functions (MySQL)
-- Generated for the provided schema (salesman, customers, orders)

-- Q1A: Function to calculate commission (10% of total sales for a salesman)
DELIMITER $$

CREATE FUNCTION get_commission(sid INT)
RETURNS DECIMAL(10,2)
DETERMINISTIC
BEGIN
    DECLARE total_sales DECIMAL(10,2);
    DECLARE commission DECIMAL(10,2);

    SELECT IFNULL(SUM(amount), 0) INTO total_sales
    FROM orders
    WHERE salesman_id = sid;

    SET commission = total_sales * 0.10;
    RETURN commission;
END $$

DELIMITER;

-- Q1B: Show salesmen and commission < 1000
-- (This is a SELECT query; run separately after function created)
-- Example:
SELECT
    s.salesman_id,
    s.name,
    s.city,
    s.salary,
    get_commission (s.salesman_id) AS commission
FROM salesman s
WHERE
    get_commission (s.salesman_id) < 1000;

-- Q2A: Create view `nameorders`
CREATE VIEW nameorders AS
SELECT
    o.order_no AS order_number,
    o.amount AS purchase_amount,
    s.salesman_id,
    s.name AS salesman_name,
    c.c_name AS customer_name,
    c.level
FROM
    orders o
    JOIN salesman s ON o.salesman_id = s.salesman_id
    JOIN customers c ON o.customer_id = c.customer_id;

-- Q2B: Display contents of view
SELECT * FROM nameorders;

-- Q2C: Note about inserting into view:
-- The view involves joins across multiple tables, so it is not updatable in general.
-- Attempting to INSERT into it will fail in MySQL (or not affect parent tables).
-- Example (will likely error):
INSERT INTO
    nameorders (
        order_number,
        purchase_amount,
        salesman_id,
        salesman_name,
        customer_name,
        level
    )
VALUES (
        70014,
        1000,
        101,
        'Nick Fury',
        'New Customer',
        200
    );

-- Q3A: Function to compute total purchase amount of a customer (uses view)
DELIMITER $$

CREATE FUNCTION get_total_purchase(cust_name VARCHAR(50))
RETURNS DECIMAL(12,2)
DETERMINISTIC
BEGIN
    DECLARE total_amount DECIMAL(12,2);

    SELECT IFNULL(SUM(purchase_amount), 0)
    INTO total_amount
    FROM nameorders
    WHERE customer_name = cust_name;

    RETURN total_amount;
END $$

DELIMITER;

-- Q3B: Example query for Brad Pitt
SELECT
    'Brad Pitt' AS customer_name,
    get_total_purchase ('Brad Pitt') AS total_purchase;

-- Q4A: View for salespeople in New York
CREATE VIEW newyork_salesmen AS
SELECT *
FROM salesman
WHERE
    city = 'New York';

-- Q4B: Display records
SELECT * FROM newyork_salesmen;

-- Q4C: Insert into view (this view is updatable because it's a single-table view)
-- Example:
INSERT INTO
    newyork_salesmen (
        salesman_id,
        name,
        city,
        salary
    )
VALUES (
        107,
        'the rock',
        'New York',
        3000
    );