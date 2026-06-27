-- Create the database
CREATE DATABASE market_basket;

-- Connect to the database
\c market_basket

-- Create the transactions table
CREATE TABLE transactions (
    beer INTEGER,
    bread INTEGER,
    cola INTEGER,
    diapers INTEGER,
    eggs INTEGER,
    milk INTEGER
);
