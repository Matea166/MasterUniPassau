CREATE DATABASE nhanes;
CREATE DATABASE imdb;

\connect nhanes;

DROP TABLE IF EXISTS nhanes_data;

CREATE TABLE nhanes_data (
    seqn INTEGER,
    age_group TEXT,
    ridageyr INTEGER,
    riagendr INTEGER,
    paq605 INTEGER,
    bmxbmi DOUBLE PRECISION,
    lbxglu DOUBLE PRECISION,
    diq010 INTEGER,
    lbxglt DOUBLE PRECISION,
    lbxin DOUBLE PRECISION
);

COPY nhanes_data (
    seqn,
    age_group,
    ridageyr,
    riagendr,
    paq605,
    bmxbmi,
    lbxglu,
    diq010,
    lbxglt,
    lbxin
)
FROM '/datasets/NHANES_age_prediction.csv'
WITH (
    FORMAT csv,
    HEADER true
);

ANALYZE nhanes_data;
