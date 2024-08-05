import json
import os
import geopandas as gpd
import pandas as pd
import psycopg2
from pyairtable import Api

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

# Function to update Airtable rows based on DataFrame
def update_airtable_from_df(df, table):
    # Fetch all records from the table
    records = table.all()
    record_map = {record['fields']['bestand_id']: record['id'] for record in records if 'bestand_id' in record['fields']}
    
    # Create a mapping of Airtable field names to DataFrame column names
    airtable_field_names = [field['name'] for field in airtable_fields]
    df_columns = df.columns.tolist()
    matching_columns = [col for col in df_columns if col in airtable_field_names]
    
    # Iterate through each row in the DataFrame
    for index, row in df.iterrows():
        bestand_id = row['bestand_id']
        if bestand_id in record_map:
            record_id = record_map[bestand_id]
            # Prepare the data to update
            update_data = row[matching_columns].dropna().to_dict()  # Convert row to dictionary and drop NaN values
            table.update(record_id, update_data)
            print(f"Updated record with bestand_id: {bestand_id}")
        else:
            print(f"Record with bestand_id: {bestand_id} not found in Airtable")
def find_SR16_intersection(event):
    print("Finding SR16 intersection")
    # Parse the GeoJSON from the request
    geojson_dict = json.loads(event['body'])
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
    HK_SHP_path = gpd.read_file('/Users/hesam.ossanloo/Downloads/AkselForest1_vector_w_HK_infos.shp')
    SR16_intersect_GeoJSON_path = gpd.GeoDataFrame.from_features(SR16_intersection_results['features'])

    # Print columns to ensure correct names
    print("HK_SHP Columns: ", HK_SHP_path.columns)
    print("SR16_intersect_GeoJSON Columns: ", SR16_intersect_GeoJSON_path.columns)

    # Check and set CRS if not defined
    if HK_SHP_path.crs is None:
        HK_SHP_path.set_crs(epsg=4326, inplace=True)  # Assuming WGS84 CRS, change if needed

    if SR16_intersect_GeoJSON_path.crs is None:
        SR16_intersect_GeoJSON_path.set_crs(epsg=4326, inplace=True)  # Assuming WGS84 CRS, change if needed
    
    # Ensure both layers are in the same CRS
    HK_SHP_path = HK_SHP_path.to_crs(SR16_intersect_GeoJSON_path.crs)

    # Perform the spatial join to calculate the overlap
    joined = gpd.overlay(HK_SHP_path, SR16_intersect_GeoJSON_path, how='intersection')

    # Print joined columns to check if 'teig_best_' is present The reason they are cut is that in shp file
    # the column names are cut to 10 characters
    print("Joined Layer Columns: ", joined.columns)

    # Calculate the area of each intersection
    joined['intersection_area'] = joined.area

    # Calculate the percentage of overlap relative to the area of the polygons in the first layer
    first_layer_areas = HK_SHP_path[['teig_best_', 'geometry']].copy()
    first_layer_areas['first_layer_area'] = first_layer_areas.geometry.area

    # Merge the first layer areas into the joined dataframe to calculate overlap percentages
    joined = joined.merge(first_layer_areas[['teig_best_', 'first_layer_area']], on='teig_best_')
    joined['overlap_percentage'] = (joined['intersection_area'] / joined['first_layer_area']) * 100

    # List of attributes to be averaged
    attributes = ['srvolmb', 'srvolub', 'srbmo', 'srbmu', 'srhoydem', 'srdiam', 'srdiam_ge8', 
                'srgrflate', 'srhoydeo', 'srtrean', 'srtrean_ge8', 'srtrean_ge10', 
                'srtrean_ge16', 'srlai', 'srkronedek']

    # Calculate weighted averages
    for attr in attributes:
        joined[attr] = joined[attr] * joined['overlap_percentage']

    # Group by teig_best_ to aggregate the required values
    grouped = joined.groupby('teig_best_').agg(
        {**{attr: 'sum' for attr in attributes}, 'overlap_percentage': 'sum'}
    ).reset_index()

    # Normalize the attributes by the overlap percentage sum to get the average values
    for attr in attributes:
        grouped[attr] = grouped[attr] / grouped['overlap_percentage']

    # Function to get prod_lokalid with overlap percentage
    def get_prod_lokalid_overlap(df):
        return ', '.join(f"({row['prod_lokalid']} & {row['overlap_percentage']:.2f}%)" for idx, row in df.iterrows())

    # Add the prod_lokalid with the overlap percentage
    prod_lokalid_overlap = joined.groupby('teig_best_').apply(get_prod_lokalid_overlap).reset_index()
    prod_lokalid_overlap.columns = ['teig_best_', 'prod_lokalid_overlap']

    # Merge the aggregated data with prod_lokalid_overlap
    final_df = pd.merge(grouped, prod_lokalid_overlap, on='teig_best_')

    # Drop the overlap_percentage column as it's no longer needed
    final_df = final_df.drop(columns=['overlap_percentage'])

    # Rename the column teig_best_ to bestand_id
    final_df = final_df.rename(columns={'teig_best_': 'bestand_id'})

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
            update_airtable_from_df(final_df, table)
        else:
            print(f"Table {TABLE_NAME} does not exist in the Airtable")
            raise Exception(f"Table {TABLE_NAME} does not exist in the Airtable")

        print(f"Table is ready. Upserting the DataFrame to Airtable...")   
    except Exception as e:
        print(f"Error connecting to Airtable: {e}")
        response = {
            'statusCode': 500,
            'body': json.dumps({'message': 'Error connecting to Airtable', 'error': str(e)})
        }
        return add_cors_headers(response)
    # Save the result to a CSV file
    final_df.to_csv(f'{forestID}_SR16-HK-intersection_Flask.csv', index=False)
    

    print("CSV file with merged attributes has been created successfully.")
    
    response = {
        'statusCode': 200,
        'body': json.dumps({'message': 'SR16 intersection with HK GeoJSON has been updated successfully on the table!'}),
    }
    
    return add_cors_headers(response)
            
def lambda_handler(event, context):
    if event['httpMethod'] == 'OPTIONS':
        print(f"Received API Gateway event: {event['httpMethod']}")
        response = {
            'statusCode': 200,
            'body': json.dumps({})
        }
        return add_cors_headers(response)
    elif event['httpMethod'] == 'POST':
        print(f"Received API Gateway event: {event['httpMethod']}")
        return find_SR16_intersection(event)
    else:
        response = {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method not allowed'})
        }
        return add_cors_headers(response)