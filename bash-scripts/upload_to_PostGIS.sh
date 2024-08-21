#!/bin/bash
# This is the main command to upload the whole GDB to PostGIS. The other two scripts, sequential_import.sh and parallel_import.sh, are just wrappers around this command.
# were try to acheive the same thing but didnt work properly. So use this one.
# Path to the GDB file
# Find the DB password from bitwarden, under AWS PostGIS Credentials
GDB_PATH="/Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/Kartverket/Matrikkel_0000_Norge_25833.gdb"

ogr2ogr --config METHOD SKIP PG_USE_COPY YES -f "PostgreSQL" PG:"host=database-postgis-instance.c9iaucgywgv3.eu-north-1.rds.amazonaws.com user=postgres dbname=postgisDB password=UiLUBELKoTBMv9*$ options='-c statement_timeout=0'" /Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/QGIS/Data/SR16/0000_25833_SR16_GDB.gdb SkogressursFlate -nlt MULTIPOLYGON -nln public.SR16 -lco GEOMETRY_NAME=geom > logs/import_SR16.log 2>&1

# For SR16 this works
ogr2ogr -f "PostgreSQL" PG:"host=database-postgis-instance.c9iaucgywgv3.eu-north-1.rds.amazonaws.com user=postgres dbname=postgisDB password=UiLUBELKoTBMv9*$ options='-c statement_timeout=0'" /Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/QGIS/Data/SR16/0000_25833_SR16_GDB.gdb SkogressursFlate -nlt MULTIPOLYGON -nln public.SR16 -lco GEOMETRY_NAME=geom > logs/import_SR16.log 2>&1
ogr2ogr -f "PostgreSQL" PG:"host=database-postgis-instance.c9iaucgywgv3.eu-north-1.rds.amazonaws.com user=postgres dbname=postgisDB password=UiLUBELKoTBMv9*$" /Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/QGIS/Data/SR16/0000_25833_SR16_GDB.gpkg -nln public.SR16_V2 > logs/import_SR16_V2.log 2>&1

ogr2ogr -f "GPKG" /Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/QGIS/Data/SR16/0000_25833_SR16_GDB.gpkg /Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/QGIS/Data/SR16/0000_25833_SR16_GDB.gdb SkogressursFlate