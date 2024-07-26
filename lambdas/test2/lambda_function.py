import sys 
import psycopg2
import os
import shapely

rds_host = os.getenv('POSTGIS_HOST')
user_name = os.getenv('POSTGIS_USERNAME')
password = os.getenv('POSTGIS_PASSWORD')
db_name = os.getenv('POSTGIS_DBNAME')
# create the database connection outside of the handler to allow connections to be
# re-used by subsequent function invocations.
try:
    conn = psycopg2. connect (host=rds_host, user=user_name, password=password, dbname=db_name, port=5432)
except psycopg2.Error as e:
    print("ERROR: Unexpected error: Could not connect to Postgres instance.")
    print(e)
    sys.exit ()
print("SUCCESS: Connection to RDS Postgres instance succeeded" )

def lambda_handler(event, context):
    """
    This function gets items from an existing RDS database
    """
    items = []
    item_count = 0
    with conn. cursor () as cur:
        cur.execute("SELECT ST_AsGeoJSON(geom) AS geojson FROM teig WHERE objectid = '1720856'")
        print("The following items have been found in the db:")
        for row in cur.fetchall():
            item_count += 1 
            print(row)
            items.append(row)
    conn. commit()
    print("Found &d items to RDS Postgres table", (item_count))
    return items