-- Create the database
CREATE DATABASE wetgrass;

-- Connect to the database
\c wetgrass;

-- Create the table
CREATE TABLE wetgrass_data (
    cloud CHAR(1),
    sprinkler VARCHAR(3),
    rain CHAR(1),
    wetgrass CHAR(1)
);
