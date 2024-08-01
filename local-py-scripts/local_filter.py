import os
import psycopg2
import time
import json
from flask import Blueprint, Flask, request, jsonify
from shapely.ops import transform
from shapely.geometry import shape, mapping, MultiPolygon
from pyproj import Transformer

main = Blueprint('main', __name__)

# Database connection parameters
conn_params = {
    'dbname': os.getenv('POSTGIS_DBNAME'),
    'user': os.getenv('POSTGIS_USERNAME'),
    'password': os.getenv('POSTGIS_PASSWORD'),
    'host': os.getenv('POSTGIS_HOST')
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
    print("Filtering features")
    data = request.get_json()
    inputs = data.get('inputs', {})
    print("Filtering features with inputs:", inputs)
    layer_name = 'teig'

    query_condition = create_query(inputs)
    print("Query condition: %s", query_condition)
    if query_condition is None:
        return jsonify({'error': 'Invalid input format'}), 400

    start_time_akerhus = time.time()

    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        sql_query = f"SELECT ST_AsGeoJSON(geom) AS geojson FROM {layer_name} WHERE {query_condition}"
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        print("Rows fetched: %s", len(rows))
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({'error': 'Database query failed'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # Convert rows to GeoJSON-like structure and then to features
    geojson_list = [json.loads(row[0]) for row in rows if row[0]]
    features = [{'type': 'Feature', 'geometry': gj, 'properties': {}}
                for gj in geojson_list if gj.get('type') == 'MultiPolygon']

    if not features:
        return jsonify({'error': 'No valid geometries found'}), 404

    # Transform geometries to EPSG:4326
    in_proj = "EPSG:25833"
    out_proj = "EPSG:4326"
    project = Transformer.from_crs(in_proj, out_proj, always_xy=True).transform
    transformed_features = [{'type': 'Feature', 'geometry': mapping(transform(
        project, shape(f['geometry']))), 'properties': f['properties']} for f in features]

    end_time_akerhus = time.time()
    elapsed_time_akerhus = end_time_akerhus - start_time_akerhus

    response = {
        'forest_geojson': json.dumps(transformed_features),
        'elapsed_time_to_prep_geojson': elapsed_time_akerhus,
    }
    return jsonify(response)


# Set up the Flask app
app = Flask(__name__)
app.register_blueprint(main)

if __name__ == '__main__':
    app.run(debug=True)
