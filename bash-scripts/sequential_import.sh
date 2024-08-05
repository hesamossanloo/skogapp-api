#!/bin/bash

# Find the DB password from bitwarden, under AWS PostGIS Credentials
# Define the PostgreSQL connection string
PG_CONN="host=database-postgis-instance.c9iaucgywgv3.eu-north-1.rds.amazonaws.com user=postgres dbname=postgisDB password=UiLUBELKoTBMv9*$ options='-c statement_timeout=0'"

# Path to the GDB file
GDB_PATH="/Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/QGIS/Data/SR16/0000_25833_SR16_GDB.gdb"
# GDB_PATH="/Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/Kartverket/Matrikkel_0000_Norge_25833.gdb"

# Ensure logs directory exists
mkdir -p logs

# Function to import a layer in batches
import_layer_in_batches() {
  local layer=$1
  local batch_size=10000
  local total_features=$(ogrinfo -al -so "$GDB_PATH" "$layer" | grep "Feature Count:" | awk '{print $3}')
  local num_batches=$((total_features / batch_size))
  
  echo "Importing layer: $layer in $num_batches batches" > "logs/import_${layer}.log"
  
  for ((i=0; i<=num_batches; i++)); do
    local start=$((i * batch_size))
    local end=$((start + batch_size - 1))
    echo "Batch $i: Importing features $start to $end" >> "logs/import_${layer}.log"
    ogr2ogr --config PG_USE_COPY YES -f "PostgreSQL" PG:"$PG_CONN" "$GDB_PATH" "$layer" -where "FID >= $start AND FID <= $end" -nln "$layer" -append -skipfailures -lco GEOMETRY_NAME=geom >> "logs/import_${layer}.log" 2>&1
  done
  
  echo "Finished importing layer: $layer" >> "logs/import_${layer}.log"
}

# Function to truncate a table
truncate_table() {
  local table=$1
  echo "Truncating table: $table"
  psql "$PG_CONN" -c "TRUNCATE TABLE $table RESTART IDENTITY CASCADE;" >> "logs/truncate.log" 2>&1
}

# Export necessary variables for parallel
export -f import_layer_in_batches
export -f truncate_table
export PG_CONN
export GDB_PATH

# Define the layers to be imported in the correct order
layers=("teig" "teiggrensepunkt" "hjelpelinje" "eiendomsgrense" "anleggsprojeksjonspunkt" "anleggsprojeksjonsgrense" "anleggsprojeksjonsflate" "matrikkelenhet" "teig_arealmerknad")

# Truncate each table before importing data
for layer in "${layers[@]}"; do
  truncate_table "$layer"
done

# Run the import for each layer in sequence to ensure foreign key constraints are respected
for layer in "${layers[@]}"; do
  import_layer_in_batches "$layer"
done