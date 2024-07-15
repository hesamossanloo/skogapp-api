import os
import psycopg2
import time
import geopandas as gpd
from flask import Blueprint, Flask, json, request, jsonify

main = Blueprint('main', __name__)

# Database connection parameters
conn_params = {
    'dbname': os.getenv('POSTGIS_DBNAME', 'postgisDB'),
    'user': os.getenv('POSTGIS_USER', 'postgres'),
    'password': os.getenv('POSTGIS_PASSWORD', '*****'),
    'host': os.getenv('POSTGIS_HOST', 'database-postgis-instance.c9iaucgywgv3.eu-north-1.rds.amazonaws.com')
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

    start_time_akerhus = time.time()

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

    end_time_akerhus = time.time()
    elapsed_time_akerhus = end_time_akerhus - start_time_akerhus

    response = {
        'filtered_features_akerhus': gdf.to_json(),
        'elapsed_time_to_prep_akerhus': elapsed_time_akerhus,
    }
    return jsonify(response)


# Set up the Flask app
app = Flask(__name__)
app.register_blueprint(main)

if __name__ == '__main__':
    app.run(debug=True)
