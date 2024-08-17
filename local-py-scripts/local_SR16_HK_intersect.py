# import json
# import os
# import geopandas as gpd
# import pandas as pd
from flask import Blueprint, Flask, request, jsonify
# import psycopg2
# from pyairtable import Api

import csv
import boto3
import json
import os

# import geopandas as gpd
# import pandas as pd
import fiona
from shapely.geometry import shape
from pyproj import CRS, Transformer
    
import psycopg2
from pyairtable import Api

main = Blueprint('main', __name__)

# Airtable configuration
AIRTABLE_PERSONAL_ACCESS_TOKEN = os.getenv('AIRTABLE_PERSONAL_ACCESS_TOKEN')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')

# Database connection parameters
conn_params = {
    'dbname': os.getenv('POSTGIS_DBNAME'),
    'user': os.getenv('POSTGIS_USERNAME'),
    'password': os.getenv('POSTGIS_PASSWORD'),
    'host': os.getenv('POSTGIS_HOST')
}

airtable_fields = [
    {'name': 'bestand_id', 'type': 'singleLineText'},
    {'name': 'DN', 'type': 'number', 'options': {'precision': 0}},
    {'name': 'hogstkl_verdi', 'type': 'number', 'options': {'precision': 0}},
    {'name': 'bonitet', 'type': 'number', 'options': {'precision': 0}},
    {'name': 'treslag', 'type': 'singleSelect', 'options': {
        'choices': [
            {'name': 'Furu', 'color': 'blueLight2'},
            {'name': 'Gran', 'color': 'greenLight2'},
            {'name': 'Bjørk / lauv', 'color': 'yellowLight2'}
        ]
    }},
    {'name': 'arealm2', 'type': 'number', 'options': {'precision': 0}},
    {'name': 'alder', 'type': 'number', 'options': {'precision': 0}},
    {'name': 'srhoydeo', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'srtrean', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'srgrflate', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'srvolmb', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'srvolub', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'Ht40', 'type': 'number', 'options': {'precision': 1}},
    {'name': 'height', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'N_per_hectare', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'G1', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'yearly_height_growth', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'delta_N_per_hectare', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'G2', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_per_hectare', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_per_hectare_next_year', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_per_hectare_without_bark', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_next_year', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_growth_next_year', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_growth_factor', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'saw_wood_portion', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_without_bark', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'carbon_stored', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'carbon_captured_next_year', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'years_to_maturity', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_at_maturity', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'volume_at_maturity_without_bark', 'type': 'number', 'options': {'precision': 8}}
]

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response

def query_fragment(geom, cursor):
    query = """
    WITH geojson AS (
        SELECT ST_Transform(
            ST_SetSRID(
                ST_GeomFromGeoJSON(%s), 4326), 25833) AS geom
    )
    SELECT row_to_json(fc)
    FROM (
        SELECT 'FeatureCollection' AS type, array_to_json(array_agg(f)) AS features
        FROM (
            SELECT 'Feature' AS type,
                   ST_AsGeoJSON(ST_Transform(ST_Intersection(public.sr16.geom, geojson.geom), 4326))::json AS geometry,
                   row_to_json((SELECT l FROM (SELECT public.sr16.*) AS l)) AS properties
            FROM public.sr16, geojson
            WHERE ST_Intersects(public.sr16.geom, geojson.geom)
        ) AS f
    ) AS fc;
    """
    cursor.execute(query, (json.dumps(geom),))
    return cursor.fetchone()[0]

# Function to update Airtable rows based on a list of dictionaries
def update_airtable_from_dict(data, table):
    # Fetch all records from the table
    records = table.all()
    record_map = {record['fields']['bestand_id']: record['id'] for record in records if 'bestand_id' in record['fields']}
    
    # Create a mapping of Airtable field names to dictionary keys
    airtable_field_names = [field['name'] for field in airtable_fields]
    
    # Collect records to be updated in a list
    batch_records = []
    
    # Iterate through each dictionary in the data list
    for row in data:
        bestand_id = row['bestand_id']
        if bestand_id in record_map:
            # Prepare the data to update
            update_data = {key: value for key, value in row.items() if key in airtable_field_names and value is not None}
            batch_records.append({"id": record_map[bestand_id], "fields": update_data})
            print(f"Prepared update for record with bestand_id: {bestand_id} with data: {update_data}")
        else:
            print(f"Record with bestand_id: {bestand_id} not found in Airtable")
    
    # Perform batch upsert
    batch_size = 10  # Adjust the batch size as needed
    for i in range(0, len(batch_records), batch_size):
        batch = batch_records[i:i + batch_size]
        print(f"Upserting batch {i // batch_size + 1}: {len(batch)} records")
        table.batch_upsert(batch, ['bestand_id'], replace=False)
            
@main.route('/SR16Intersection', methods=['POST'])
def find_SR16_intersection():
    print("Finding SR16 intersection")
    # Parse the GeoJSON from the request
    geojson_dict = request.json
    forestID = geojson_dict.get('forestID')
    
    # if forestID is not found, the function will not proceed
    if not forestID:
        print('No valid forestID found in the event.')
        return
        
    print("Building connection to PostGIS!")
    conn = None
    cursor = None
    
    # Connect to the database and query the intersection
    try:
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        # Aggregate results
        SR16_intersection_results = {
            "type": "FeatureCollection",
            "features": []
        }

        for feature in geojson_dict['features']:
            geom = feature['geometry']
            result = query_fragment(geom, cursor)
            if result and 'features' in result and result['features'] is not None:
                SR16_intersection_results['features'].extend(result['features'])
    except Exception as e:
        print(f"Database error: {e}")
        response = {
            'statusCode': 500,
            'body': json.dumps({'error': 'Database query failed'}),
        }
        return add_cors_headers(response)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    # Load the vector layers
    # Read shapefile using fiona
    with fiona.open('/Users/hesam.ossanloo/Downloads/0ymOEIru0rXJhtpOIVsovYOBjIE3_vector_w_HK_infos.shp') as shp:
        shp_crs = CRS(shp.crs) if shp.crs else CRS.from_epsg(4326)  # Assuming WGS84 CRS if not defined
        HK_SHP_Geometries = [shape(feature['geometry']) for feature in shp]
        HK_SHP_Attributes = [{**feature['properties'], 'geometry': shape(feature['geometry'])} for feature in shp]
    # HK_SHP_path = gpd.read_file('/Users/hesam.ossanloo/Downloads/AkselForest1_vector_w_HK_infos.shp')
    # SR16_intersect_GeoJSON_path = gpd.GeoDataFrame.from_features(SR16_intersection_results['features'])

    # Convert GeoJSON features to shapely geometries
    SR16_intersect_GeoJSON_Features = [shape(feature['geometry']) for feature in SR16_intersection_results['features']]
    SR16_intersect_GeoJSON_Attributes = [{**feature['properties'], 'geometry': shape(feature['geometry'])} for feature in SR16_intersection_results['features']]

    # Assuming GeoJSON features are in WGS84 CRS
    geojson_crs = CRS.from_epsg(4326)

    # Ensure both layers are in the same CRS
    if shp_crs != geojson_crs:
        transformer = Transformer.from_crs(shp_crs, geojson_crs, always_xy=True)
        HK_SHP_Geometries = [transformer.transform(geom) for geom in HK_SHP_Geometries]

    # Print geometries to ensure correct data
    print("HK_SHP Geometries: ", HK_SHP_Geometries)
    print("SR16_intersect_GeoJSON Geometries: ", SR16_intersect_GeoJSON_Features)

    # Perform the spatial join to calculate the overlap
    intersections = []
    for hk_geom, hk_attr in zip(HK_SHP_Geometries, HK_SHP_Attributes):
        for sr_geom, sr_attr in zip(SR16_intersect_GeoJSON_Features, SR16_intersect_GeoJSON_Attributes):
            if hk_geom.intersects(sr_geom):
                intersection = hk_geom.intersection(sr_geom)
                intersection_area = intersection.area
                overlap_percentage = (intersection_area / hk_geom.area) * 100
                intersection_attributes = {**hk_attr, **sr_attr, 'intersection_area': intersection_area, 'overlap_percentage': overlap_percentage}
                intersections.append(intersection_attributes)

    # List of attributes to be averaged
    attributes = ['srvolmb', 'srvolub', 'srbmo', 'srbmu', 'srhoydem', 'srdiam', 'srdiam_ge8', 
                'srgrflate', 'srhoydeo', 'srtrean', 'srtrean_ge8', 'srtrean_ge10', 
                'srtrean_ge16', 'srlai', 'srkronedek']

    print("Aggregating the required values...")
    # Aggregate the required values
    aggregated_data = {}
    for intersection in intersections:
        teig_best_ = intersection['teig_best_']
        if teig_best_ not in aggregated_data:
            aggregated_data[teig_best_] = {attr: 0 for attr in attributes}
            aggregated_data[teig_best_]['overlap_percentage'] = 0
        for attr in attributes:
            aggregated_data[teig_best_][attr] += intersection[attr] * intersection['overlap_percentage']
        aggregated_data[teig_best_]['overlap_percentage'] += intersection['overlap_percentage']

    # Normalize the attributes by the overlap percentage sum to get the average values
    for teig_best_, data in aggregated_data.items():
        for attr in attributes:
            data[attr] /= data['overlap_percentage']

    # Function to get prod_lokalid with overlap percentage
    def get_prod_lokalid_overlap(intersections, teig_best_):
        return ', '.join(f"({intersection['prod_lokalid']} & {intersection['overlap_percentage']:.2f}%)" for intersection in intersections if intersection['teig_best_'] == teig_best_)

    # Add the prod_lokalid with the overlap percentage
    for teig_best_ in aggregated_data.keys():
        aggregated_data[teig_best_]['prod_lokalid_overlap'] = get_prod_lokalid_overlap(intersections, teig_best_)

    # Rename the column teig_best_ to bestand_id
    final_data = [{'bestand_id': teig_best_, **data} for teig_best_, data in aggregated_data.items()]

    print(f"Processing table for forestID: {forestID}")
    # build the table name with forestID
    TABLE_NAME = f'{forestID}_bestandsdata'
    try:
        print("Connecting to Airtable... to Base ID: ", AIRTABLE_BASE_ID)
        api = Api(AIRTABLE_PERSONAL_ACCESS_TOKEN)
        base = api.base(AIRTABLE_BASE_ID)
        tables = base.schema().tables
        table_exists = any(table.name == TABLE_NAME for table in tables)
        
        if table_exists:
            print(f"Table {TABLE_NAME} exists. Proceeding with updates...")
            table = base.table(TABLE_NAME)
            update_airtable_from_dict(final_data, table)
        else:
            print(f"Table {TABLE_NAME} does not exist in the Airtable")
            raise Exception(f"Table {TABLE_NAME} does not exist in the Airtable")

        print(f"Table is ready. Upserting the data to Airtable...")
    except Exception as e:
        print(f"Error connecting to Airtable: {e}")
    
    # Save the result to a CSV file
    with open(f'{forestID}_SR16-HK-intersection_Flask.csv', 'w') as csvfile:
        fieldnames = ['bestand_id'] + attributes + ['prod_lokalid_overlap']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in final_data:
            # Remove 'overlap_percentage' from the row before writing
            row.pop('overlap_percentage', None)
            writer.writerow(row)
    

    print("CSV file with merged attributes has been created successfully.")
    
    response = {
        'statusCode': 200,
        'body': json.dumps({'message': 'SR16 intersection with HK GeoJSON has been updated successfully on the table!'}),
    }
    
    return jsonify(add_cors_headers(response))

# Set up the Flask app
app = Flask(__name__)
app.register_blueprint(main)

if __name__ == '__main__':
    app.run(debug=True)