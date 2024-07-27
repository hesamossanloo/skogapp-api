import os
import psycopg2
import time
import json
from shapely.ops import transform
from shapely.geometry import shape, mapping
from pyproj import Transformer

# Database connection parameters
conn_params = {
    'dbname': os.getenv('POSTGIS_DBNAME'),
    'user': os.getenv('POSTGIS_USERNAME'),
    'password': os.getenv('POSTGIS_PASSWORD'),
    'host': os.getenv('POSTGIS_HOST'),
    'port': 5432,
}

def create_query(inputs):
    kommunenummer = inputs.get('kommunenummer')
    matrikkelnummertekst_list = inputs.get('matrikkelnummertekst')
    if not kommunenummer:
        response = {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing kommunenummer'})
        }
        return add_cors_headers(response)
    if not matrikkelnummertekst_list:
        response = {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing matrikkelnummertekst'})
        }
        return add_cors_headers(response)

    matrikkelnummertekst_conditions = ", ".join(
        [f"'{mn}'" for mn in matrikkelnummertekst_list])
    query = f"kommunenummer = '{kommunenummer}' AND matrikkelnummertekst IN ({matrikkelnummertekst_conditions})"
    return query

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response

def filter_features(event, context):
    data = json.loads(event['body'])
    inputs = data.get('inputs', {})
    print("Filtering features with inputs:", inputs)
    layer_name = 'teig'
    name = inputs.get('name')
    if not name:
        response = {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing name'})
        }
        return add_cors_headers(response)
    query_condition = create_query(inputs)
    print("Query condition:", query_condition)
    if query_condition is None:
        response = {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid input format'})
        }
        return add_cors_headers(response)
    start_time = time.time()
    conn = None
    cursor = None
    try:
        print("Connecting to database with dbname: ", conn_params['dbname'])
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        print("Connected to database")
        sql_query = f"SELECT ST_AsGeoJSON(geom) AS geojson FROM {layer_name} WHERE {query_condition}"
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        print("Rows fetched: %s", len(rows))
    except Exception as e:
        print(f"Database error: {e}")
        response = {
            'statusCode': 500,
            'body': json.dumps({'error': 'Database query failed'})
        }
        return add_cors_headers(response)
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
        response = {
            'statusCode': 404,
            'body': json.dumps({'error': 'No valid geometries found'})
        }
        return add_cors_headers(response)
    # Transform geometries to EPSG:4326
    in_proj = "EPSG:25833"
    out_proj = "EPSG:4326"
    project = Transformer.from_crs(in_proj, out_proj, always_xy=True).transform
    transformed_features = [{'type': 'Feature', 'geometry': mapping(transform(
        project, shape(f['geometry']))), 'properties': f['properties']} for f in features]
    end_time = time.time()
    elapsed_time = end_time - start_time
    # Assuming transformed_features is already defined and is a list of features
    
    feature_collection = {
        "type": "FeatureCollection",
        "features": transformed_features,
        "name": name  # Add the name attribute here
    }
    response = {
        'statusCode': 200,
        'body': json.dumps({
            'filtered_features': feature_collection,
            'elapsed_time_to_prep_geojson': elapsed_time,
        })
    }
    return add_cors_headers(response)

def lambda_handler(event, context):
    if event['httpMethod'] == 'OPTIONS':
        response = {
            'statusCode': 200,
            'body': json.dumps({})
        }
        return add_cors_headers(response)
    elif event['httpMethod'] == 'POST':
        return filter_features(event, context)
    else:
        response = {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method not allowed'})
        }
        return add_cors_headers(response)