#!/bin/bash
# Path to the GDB file
# Find the DB password from bitwarden, under AWS PostGIS Credentials
GDB_PATH="/Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/Kartverket/Matrikkel_0000_Norge_25833.gdb"

ogr2ogr --config METHOD SKIP PG_USE_COPY YES -f "PostgreSQL" PG:"host=database-postgis-instance.c9iaucgywgv3.eu-north-1.rds.amazonaws.com user=postgres dbname=postgisDB password=$Password options='-c statement_timeout=0'" /Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/Kartverket/Matrikkel_0000_Norge_25833.gdb teig -nlt MULTIPOLYGON -nln public.teig -lco GEOMETRY_NAME=geom > logs/import_teig.log 2>&1