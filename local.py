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
    'password': os.getenv('POSTGIS_PASSWORD', 'UiLUBELKoTBMv9*$'),
    'host': os.getenv('POSTGIS_HOST', 'database-postgis-instance.c9iaucgywgv3.eu-north-1.rds.amazonaws.com')
}


def create_query(inputs):
    kommunenummer = inputs.get('kommunenummer')
    matrikkelnummertekst_list = inputs.get('matrikkelnummertekst')
    if not kommunenummer or not matrikkelnummertekst_list:
        return None

    matrikkelnummertekst_conditions = ", ".join(
        [f"'{mn}'" for mn in matrikkelnummertekst_list])
    query = f"kommunenummer = '{kommunenummer}' AND matrikkelnummertekst IN ({matrikkelnummertekst_conditions})"
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
        sql_query = f"SELECT ST_AsGeoJSON(geom) AS geojson FROM {layer_name} WHERE {query_condition}"
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
    features = [{'type': 'Feature', 'geometry': gj, 'properties': {}} for gj in geojson_list if gj.get('type') == 'MultiPolygon']

    if not features:
        return jsonify({'error': 'No valid geometries found'}), 404

    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:25833")

    # Reproject to EPSG:4326 if necessary
    if gdf.crs != 'epsg:4326':
        gdf = gdf.to_crs('epsg:4326')

    # Ensure /tmp directory exists
    tmp_dir = '/tmp'
    if not os.path.exists(tmp_dir):
        print(f"Creating directory: {tmp_dir}")
        os.makedirs(tmp_dir)

    # Test writing a dummy file to /tmp
    test_file_path = os.path.join(tmp_dir, 'test_file.txt')
    try:
        with open(test_file_path, 'w') as test_file:
            test_file.write('This is a test file.')
        print(f"Test file written to {test_file_path}")
    except Exception as e:
        print(f"Error writing test file: {e}")

    # Save the filtered GeoDataFrame to a GeoJSON file
    output_geojson_path_akerhus = os.path.join(tmp_dir, 'output_4326_postgis.geojson')
    try:
        print(f"Saving GeoDataFrame to {output_geojson_path_akerhus}")
        gdf.to_file(output_geojson_path_akerhus, driver='GeoJSON')
        if os.path.exists(output_geojson_path_akerhus):
            print(f"File successfully saved to {output_geojson_path_akerhus}")
        else:
            print(f"File was not found after saving attempt: {output_geojson_path_akerhus}")
    except Exception as e:
        print(f"Error saving file: {e}")
        return jsonify({'error': 'Failed to save GeoJSON file'}), 500

    # List files in /tmp for debugging
    print("Listing files in /tmp:")
    for file_name in os.listdir(tmp_dir):
        print(f"- {file_name}")

    end_time_akerhus = time.time()
    elapsed_time_akerhus = end_time_akerhus - start_time_akerhus

    response = {
        'filtered_features_akerhus': gdf.to_json(),
        'output_file_akerhus': output_geojson_path_akerhus,
        'elapsed_time_to_prep_akerhus': elapsed_time_akerhus,
    }
    return jsonify(response)


# Set up the Flask app
app = Flask(__name__)
app.register_blueprint(main)

if __name__ == '__main__':
    app.run(debug=True)