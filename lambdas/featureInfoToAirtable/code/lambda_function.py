import os
import boto3
from botocore.exceptions import ClientError
import shapefile
from pyairtable import Api
# Initialize the S3 client
s3_client = boto3.client('s3')

# Define the S3 bucket and folders
bucket_name = 'skogapp-lambda-generated-outputs'
s3_folder_feature_info = 'SkogAppHKFeatureInfo/'

# Temporary local paths
local_shp_path = '/tmp/vector_w_info.shp'
local_shx_path = '/tmp/vector_w_info.shx'
local_dbf_path = '/tmp/vector_w_info.dbf'

# Airtable configuration
AIRTABLE_PERSONAL_ACCESS_TOKEN = os.getenv('AIRTABLE_PERSONAL_ACCESS_TOKEN')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')

# Table fields and shape file records mappings
table_fields_names_maps = {
    "teig_best_": "bestand_id",
    "bestand_id": "DN",
    "hogstkl_ve": "hogstkl_verdi",
    "bonitet_be": "bonitet",
    "bontre_bes": "treslag",
    "arealm2": "arealm2",
    "alder": "alder",
    "srhoydeo": "srhoydeo",
    "srtrean": "srtrean",
    "srgrflate": "srgrflate",
    "srvolmb": "srvolmb",
    "srvolub": "srvolub",
    "Ht40": "Ht40",
    "height": "height",
    "N_per_hectare": "N_per_hectare",
    "G1": "G1",
    "yearly_height_growth": "yearly_height_growth",
    "delta_N_per_hectare": "delta_N_per_hectare",
    "G2": "G2",
    "volume_per_hectare": "volume_per_hectare",
    "volume_per_hectare_next_year": "volume_per_hectare_next_year",
    "volume_per_hectare_without_bark": "volume_per_hectare_without_bark",
    "volume": "volume",
    "volume_next_year": "volume_next_year",
    "volume_growth_next_year": "volume_growth_next_year",
    "volume_growth_factor": "volume_growth_factor",
    "saw_wood_portion": "saw_wood_portion",
    "volume_without_bark": "volume_without_bark",
    "carbon_stored": "carbon_stored",
    "carbon_captured_next_year": "carbon_captured_next_year",
    "years_to_maturity": "years_to_maturity",
    "volume_at_maturity": "volume_at_maturity",
    "volume_at_maturity_without_bark": "volume_at_maturity_without_bark",
}

# Define the table fields
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
    {'name': 'volume_at_maturity_without_bark', 'type': 'number', 'options': {'precision': 8}},
    {'name': 'yield_requirement', 'type': 'number', 'options': {'precision': 1}},
]

def lambda_handler(event, context):
    # Get the object key from the S3 event
    #  print the event records with a text saying that
    print(f"Received event records: {event['Records']}")
    for record in event['Records']:
        print(f"Processing record: {record}")
        S3_object_key = record['s3']['object']['key']
        print(f"Processing object key: {S3_object_key}")
        # the issue is that the s3_object_key looks like this: Object SkogAppHKFeatureInfo/Knut123XY_vectorized_HK.shp
        # I want it to look llike this Knut123XY_vectorized_HK.shp
        # so I will split the string and get the first element
        received_S3_folder_name = S3_object_key.split('/')[0]
        print(f"Processing received S3 folder name: {received_S3_folder_name}")
        # I also need to get rid of the .shp extension
        received_S3_file_name = S3_object_key.split('/')[-1]
        forest_file_name_no_ext = received_S3_file_name.split('.')[0]
        print(f"Processing forest file name: {forest_file_name_no_ext}")

        # the first prefix before the underscrore is the forestID
        forestID = forest_file_name_no_ext.split('_')[0]
        # if forestID is not found, the function will not proceed
        if not forestID:
            print('No valid forestID found in the event.')
            return
        print(f"Processing table for forestID: {forestID}")
        # build the table name with forestID
        TABLE_NAME = f'{forestID}_bestandsdata'
        try:
            s3_client.head_object(Bucket=bucket_name, Key=f"{S3_object_key}")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                print(f"Object {S3_object_key} does not exist.")
                continue
            else:
                raise
        
        # Download the shapefile components from S3
        print("Downloading shapefile components from S3...", f"{received_S3_folder_name}/{forest_file_name_no_ext}.shp/shx/dbf/prj")
        s3_client.download_file(bucket_name, f"{received_S3_folder_name}/{forest_file_name_no_ext}.shp", local_shp_path)
        s3_client.download_file(bucket_name, f"{received_S3_folder_name}/{forest_file_name_no_ext}.shx", local_shx_path)
        s3_client.download_file(bucket_name, f"{received_S3_folder_name}/{forest_file_name_no_ext}.dbf", local_dbf_path)

        try:
            print("Connecting to Airtable... to Base ID: ", AIRTABLE_BASE_ID)
            api = Api(AIRTABLE_PERSONAL_ACCESS_TOKEN)
            base = api.base(AIRTABLE_BASE_ID)
            # check if the table exists in the Airtable
            tables = base.schema().tables
            table_exists = any(table.name == TABLE_NAME for table in tables)
            
            table = None
            if table_exists:
                table = base.table(TABLE_NAME)
            else:
                print(f"Table {TABLE_NAME} does not exist in the Airtable")
                # create the table
                print(f"Creating table {TABLE_NAME} in the Airtable")
                table = base.create_table(TABLE_NAME, airtable_fields)
                print(f"Table {TABLE_NAME} created in the Airtable")
            if table is None:
                print(f"Table {TABLE_NAME} does not exist in the Airtable and couldn't create it either!")
                return
            
            print(f"Table is ready. Now Processing shapefile: {local_shp_path}")
            # open the shapefile
            sf = shapefile.Reader(local_shp_path)
            
            # Get the field names from the shapefile
            field_names = [field[0] for field in sf.fields[1:]]

            # get the shapefile records and first record
            records = sf.records()
            
            # Collect records to batch upsert
            batch_records = []
            
            # Process each record in the shapefile
            processed_bestand_ids = []
            for record in records:
                # Initialize the mapped_record with empty values
                mapped_record = {airtable_field: '' for airtable_field in table_fields_names_maps.values()}

                # Map the keys from the record to the Airtable field names
                for field_name, value in zip(field_names, record):
                    if field_name in table_fields_names_maps:
                        mapped_record[table_fields_names_maps[field_name]] = value

                # Initialize a list to keep track of processed bestand_ids

                # Cross-reference mapped_record with airtable_fields and cast values
                for key, value in mapped_record.items():
                    for field in airtable_fields:
                        if key == 'bonitet':
                            value = value.split(' ')[-1]
                        if field['name'] == key and field['type'] == 'number':
                            precision = field['options'].get('precision')  # Default precision to 2 if not specified
                            try:
                                if precision == 0:
                                    mapped_record[key] = int(value)
                                else:
                                    mapped_record[key] = round(float(value), precision)
                            except ValueError:
                                mapped_record[key] = None  # Handle the case where value cannot be converted to float
                
                # Perform checks before adding to batch
                if mapped_record['bestand_id'] == '':
                    print(f"Skipping record with DN: {mapped_record['DN']} because of empty bestand_id")
                    continue
                if mapped_record['bestand_id'] in processed_bestand_ids:
                    print(f"Skipping record with bestand_id: {mapped_record['bestand_id']} as it is already processed")
                    continue
                
                # Add the mapped record to the batch
                batch_records.append({"fields": mapped_record})
                processed_bestand_ids.append(mapped_record['bestand_id'])

            # Insert or update the records in the Airtable table in batches
            batch_size = 10  # Adjust the batch size as needed
            for i in range(0, len(batch_records), batch_size):
                batch = batch_records[i:i + batch_size]
                print(f"Upserting batch {i // batch_size + 1}: {len(batch)} records")
                table.batch_upsert(batch, ['bestand_id'], replace=True)
            print(f"Successfully upserted all batches to the table {TABLE_NAME}")   
        except Exception as e:
            print(f"Error connecting to Airtable: {e}")
            return
            
    print('No more valid file found in the event.')