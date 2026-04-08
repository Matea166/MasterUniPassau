#!/bin/bash

apt-get update
apt-get install -y wget

export PGPASSWORD=postgres

# Download the JOB CSV files
wget wget https://bonsai.cedardb.com/job/imdb.tgz --no-check-certificate
tar xz -f imdb.tgz --directory /tmp


execute="psql -h $POSTGRES_HOST -p 5432 -d $POSTGRES_DB -U $POSTGRES_USER -a"


$execute -c "DROP SCHEMA public CASCADE;"
$execute -c "CREATE SCHEMA public;"
$execute -c "GRANT ALL ON SCHEMA public TO postgres;"
$execute -c "GRANT ALL ON SCHEMA public TO public;"

# Create the relations
$execute -q -f /tmp/schematext.sql

# Upload the CSV files
for path in /tmp/*.csv; do
    filename="$(cut -d '/' -f3 <<<"$path")"
    table="$(cut -d '.' -f1 <<<"$filename")"
    sed -i 's/\\\\\"/"/g' $path  # Removes \\" with "
    sed -i s/\\\\\"/\'/g $path  # Replaces \" with \'
    $execute -c "\COPY $table FROM '$path' DELIMITER ',' CSV;"
done

# Add the foreign keys
$execute -q -f foreign_keys.sql

# Add indexes on the foreign keys
$execute -q -f join-order-benchmark/fkindexes.sql

# Update the statistics
$execute -c "ANALYZE;"
