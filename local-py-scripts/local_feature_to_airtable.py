import os
import shapefile
from pyairtable import Api

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
shp_path = os.path.join(script_dir, "outputs/vectorize/intersected_image_w_info.shp")
if not os.path.exists(shp_path):
    print(f"File {shp_path} does not exist")
    exit(1)
# get the forestID from the shapefile path, first split with /, then
#  get the last part, then split with _, then get the first part
forestID = shp_path.split('/')[-1].split('_')[0]
# Airtable configuration
AIRTABLE_PERSONAL_ACCESS_TOKEN = os.getenv('AIRTABLE_PERSONAL_ACCESS_TOKEN')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
# build the table name with forestID
TABLE_NAME = f'{forestID}_bestandsdata'
api = Api(AIRTABLE_PERSONAL_ACCESS_TOKEN)
base = api.base(AIRTABLE_BASE_ID)

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
            {'name': 'Bjørk / Lauv', 'color': 'yellowLight2'}
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

# check if the table exists in the Airtable
tables = base.schema().tables
table_exists = any(table.name == TABLE_NAME for table in tables)
table = None
if table_exists:
    table = base.table(TABLE_NAME)
else:
    print(f"Table {TABLE_NAME} does not exist in the Airtable")
    # create the table
    try:
        print(f"Creating table {TABLE_NAME} in the Airtable")
        table = base.create_table(TABLE_NAME, airtable_fields)
        print(f"Table {TABLE_NAME} created in the Airtable")
    except Exception as e:
        print(f"Error creating table {TABLE_NAME}: {str(e)}")

if table is None:
    print(f"Table {TABLE_NAME} does not exist in the Airtable and couldn't create it either!")
    exit(1)
    
print(f"Table is ready. Now Processing shapefile: {shp_path}")

# open the shapefile
sf = shapefile.Reader(shp_path)

# Get the field names from the shapefile
field_names = [field[0] for field in sf.fields[1:]]

# get the shapefile records and first record
records = sf.records()

# Process each record in the shapefile
for record in records:
    # Initialize the mapped_record with empty values
    mapped_record = {airtable_field: '' for airtable_field in table_fields_names_maps.values()}

    # Map the keys from the record to the Airtable field names
    for field_name, value in zip(field_names, record):
        if field_name in table_fields_names_maps:
            mapped_record[table_fields_names_maps[field_name]] = value

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

    # Insert or update the record in the Airtable table
    table_records = table.all()
    if len(table_records) == 0:
        print(f"Inserting record to the table {TABLE_NAME}: {mapped_record['bestand_id']}")
        table.create(mapped_record)
    else:
        print(f"Updating record in the table {TABLE_NAME}: {mapped_record['bestand_id']}")
        if mapped_record['bestand_id'] == '':
            print(f"Skipping record with DN: {mapped_record['DN']} because of empty bestand_id")
            continue
        table.batch_upsert([{"fields": mapped_record}], ['bestand_id', 'DN'], replace=True)