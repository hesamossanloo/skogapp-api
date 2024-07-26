#!/bin/bash

# Find the DB password from bitwarden, under AWS PostGIS Credentials
# Define the PostgreSQL connection string
PG_CONN="host=database-postgis-instance.c9iaucgywgv3.eu-north-1.rds.amazonaws.com user=postgres dbname=postgisDB password=$Password options='-c statement_timeout=0'"

# Path to the GDB file
GDB_PATH="/Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/Kartverket/Matrikkel_0000_Norge_25833.gdb"

# Define the layers to be imported
layers=("matrikkelenhet" "teig_arealmerknad" "teiggrensepunkt" "hjelpelinje" "eiendomsgrense" "teig" "anleggsprojeksjonspunkt" "anleggsprojeksjonsgrense" "anleggsprojeksjonsflate")

# Function to import a layer
import_layer() {
  local layer=$1
  echo "Importing layer: $layer" > "import_${layer}.log"
  ogr2ogr --config PG_USE_COPY YES -f "PostgreSQL" PG:"$PG_CONN" "$GDB_PATH" "$layer" -nln "$layer" -append -skipfailures -lco GEOMETRY_NAME=geom >> "import_${layer}.log" 2>&1
}

# Export necessary variables for parallel
export -f import_layer
export PG_CONN
export GDB_PATH

# Run the import for each layer in parallel
parallel import_layer ::: "${layers[@]}"