CREATE DATABASE nhanes;
CREATE DATABASE imdb;

\connect nhanes;

DROP TABLE IF EXISTS nhanes_data;

CREATE TABLE nhanes_data (
    seqn DOUBLE PRECISION,
    age_group TEXT,
    ridageyr DOUBLE PRECISION,
    riagendr DOUBLE PRECISION,
    paq605 DOUBLE PRECISION,
    bmxbmi DOUBLE PRECISION,
    lbxglu DOUBLE PRECISION,
    diq010 DOUBLE PRECISION,
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
