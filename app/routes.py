import os
import psycopg2
import time
import geopandas as gpd
from flask import Blueprint, json, request, jsonify
import boto3

main = Blueprint('main', __name__)

# Initialize Secrets Manager client
secrets_client = boto3.client('secretsmanager')
secret_name = os.getenv('SECRET_NAME')

# Fetch secrets
response = secrets_client.get_secret_value(SecretId=secret_name)
secrets = json.loads(response['SecretString'])

postgis_dbname = secrets.get("POSTGIS_DBNAME")
postgis_username = secrets.get("POSTGIS_USERNAME")
postgis_password = secrets.get("POSTGIS_PASSWORD")
postgis_host = secrets.get("POSTGIS_HOST")

# Database connection parameters
conn_params = {
    'dbname': postgis_dbname,
    'user': postgis_username,
    'password': postgis_password,
    'host': postgis_host
}


def create_query(inputs):
    kommunenummer = inputs.get('kommunenummer')
    matrikkelnummertekst_list = inputs.get('matrikkelnummertekst')
    if not kommunenummer or not matrikkelnummertekst_list:
        return None

    matrikkelnummertekst_conditions = ", ".join(
        [f"'{mn}'" for mn in matrikkelnummertekst_list])
    query = f"kommunenummer = '{kommunenummer}' AND matrikkelnummertekst IN ({
        matrikkelnummertekst_conditions})"
    return query


@main.route('/filter', methods=['POST'])
def filter_features():
    data = request.get_json()
    inputs = data.get('inputs', {})
    layer_name = 'teig'

    query_condition = create_query(inputs)
    if query_condition is None:
        return jsonify({'error': 'Invalid input format'}), 400

    start_time = time.time()

    # Connect to the database and execute the query
    try:
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        sql_query = f"SELECT ST_AsGeoJSON(geom) AS geojson FROM {
            layer_name} WHERE {query_condition}"
        cursor.execute(sql_query)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({'error': 'Database query failed'}), 500
    finally:
        cursor.close()
        conn.close()

    # Convert rows to GeoDataFrame
    geojson_list = [json.loads(row[0]) for row in rows if row[0]]
    features = [{'type': 'Feature', 'geometry': gj, 'properties': {}}
                for gj in geojson_list if gj.get('type') == 'MultiPolygon']

    if not features:
        return jsonify({'error': 'No valid geometries found'}), 404

    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:25833")

    # Reproject to EPSG:4326 if necessary
    if gdf.crs != 'epsg:4326':
        gdf = gdf.to_crs('epsg:4326')

    end_time = time.time()
    elapsed_time = end_time - start_time

    response = {
        'filtered_features': gdf.to_json(),
        'elapsed_time_to_prep_geojson': elapsed_time,
    }
    return jsonify(response)
