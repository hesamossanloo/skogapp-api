import boto3
import shapefile
import requests
import xml.etree.ElementTree as ET
from shapely.geometry import shape
from shapely.validation import make_valid
from shapely.ops import transform
import pyproj

# Initialize the S3 client
s3_client = boto3.client('s3')

# Define the S3 bucket and folders
bucket_name = 'skogapp-lambda-generated-outputs'
s3_folder_vectorize = 'SkogAppHKVectorize/'
s3_folder_feature_info = 'SkogAppHKFeatureInfo/'

# Temporary local paths
local_shp_path = '/tmp/vectorized_HK.shp'
local_shx_path = '/tmp/vectorized_HK.shx'
local_dbf_path = '/tmp/vectorized_HK.dbf'
local_prj_path = '/tmp/vectorized_HK.prj'
local_out_shp_path = '/tmp/vector_w_info.shp'
local_out_shx_path = '/tmp/vector_w_info.shx'
local_out_dbf_path = '/tmp/vector_w_info.dbf'
local_out_prj_path = '/tmp/vector_w_info.prj'

# Function to get the bounding box of a point with a small buffer
def get_bbox(point, buffer=0.001):
    minx, miny, maxx, maxy = point.buffer(buffer).bounds
    return minx, miny, maxx, maxy

# Function to parse the XML response
def parse_xml_response(response_text):
    root = ET.fromstring(response_text)
    ns = {'gml': 'http://www.opengis.net/gml'}
    feature = root.find('.//hogstklasser_feature')
    if feature is None:
        return {}

    attributes = {
        'leveranseid': feature.findtext('leveranseid', default='', namespaces=ns),
        'prosjekt': feature.findtext('prosjekt', default='', namespaces=ns),
        'kommune': feature.findtext('kommune', default='', namespaces=ns),
        'hogstkl_verdi': feature.findtext('hogstkl_verdi', default='', namespaces=ns),
        'bonitet_beskrivelse': feature.findtext('bonitet_beskrivelse', default='', namespaces=ns),
        'bontre_beskrivelse': feature.findtext('bontre_beskrivelse', default='', namespaces=ns),
        'areal': feature.findtext('areal', default='', namespaces=ns),
        'arealm2': feature.findtext('arealm2', default='', namespaces=ns),
        'alder': feature.findtext('alder', default='', namespaces=ns),
        'alder_korr': feature.findtext('alder_korr', default='', namespaces=ns),
        'regaar_korr': feature.findtext('regaar_korr', default='', namespaces=ns),
        'regdato': feature.findtext('regdato', default='', namespaces=ns),
        'sl_sdeid': feature.findtext('sl_sdeid', default='', namespaces=ns),
        'teig_best_nr': feature.findtext('teig_best_nr', default='', namespaces=ns),
    }
    return attributes

def lambda_handler(event, context):
    # Get the object key from the S3 event
    for record in event['Records']:
        s3_object_key = record['s3']['object']['key']
        if s3_folder_vectorize not in s3_object_key:
            return
        # the first prefix before the underscrore is the forestID
        forestID = s3_object_key.split('_')[0]
        # if forestID is not found, the function will not proceed
        if not forestID:
            print('No valid forestID found in the event.')
            return
        
        
        
        # Download the shapefile components from S3
        s3_client.download_file(bucket_name, f"{s3_object_key}.shp", local_shp_path)
        s3_client.download_file(bucket_name, f"{s3_object_key}.shx", local_shx_path)
        s3_client.download_file(bucket_name, f"{s3_object_key}.dbf", local_dbf_path)
        s3_client.download_file(bucket_name, f"{s3_object_key}.prj", local_prj_path)

        # Read the shapefile
        sf = shapefile.Reader(local_shp_path)
        writer = shapefile.Writer(local_out_shp_path)
        
        # Copy the fields from the original shapefile
        writer.fields = sf.fields[1:]  # Skip deletion field

        # Add new fields for feature information if they don't already exist
        new_fields = ['bestand_id', 'leveranseid', 'prosjekt', 'kommune', 'hogstkl_verdi', 'bonitet_beskrivelse',
                      'bontre_beskrivelse', 'areal', 'arealm2', 'alder', 'alder_korr', 'regaar_korr',
                      'regdato', 'sl_sdeid', 'teig_best_nr', 'shape_area']
        existing_fields = {field[0] for field in sf.fields[1:]}  # Get existing field names

        for attr_name in new_fields:
            if attr_name == 'shape_area':
                writer.field(attr_name, 'N', decimal=0)  # Define 'shape_area' as numeric
            elif attr_name not in existing_fields:
                writer.field(attr_name, 'C')

        # Define the projection transformation to a suitable CRS for area calculation (e.g., EPSG:3857)
        project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform

        # Define the WMS parameters
        wms_url = 'https://wms.nibio.no/cgi-bin/skogbruksplan'
        wms_layer = 'hogstklasser'
        width = 788
        height = 675
        info_format = 'application/vnd.ogc.gml'
        feature_count = 10

        # Process each shape and record
        for shape_rec in sf.shapeRecords():
            geom = shape(shape_rec.shape.__geo_interface__)
            if not geom.is_valid:
                geom = make_valid(geom)

            # Project geometry to a suitable CRS for area calculation
            projected_geom = transform(project, geom)
            area = int(projected_geom.area)  # Ensure area is an integer

            # Skip polygons with an area less than 3480
            if area < 3480:
                continue

            centroid = geom.centroid
            minx, miny, maxx, maxy = get_bbox(centroid)

            # Calculate I, J values (relative pixel coordinates)
            i = int((centroid.x - minx) / (maxx - minx) * width)
            j = int((centroid.y - miny) / (maxy - miny) * height)

            # Construct the GetFeatureInfo URL
            getfeatureinfo_url = (
                f"{wms_url}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&"
                f"BBOX={miny},{minx},{maxy},{maxx}&CRS=EPSG:4326&WIDTH={width}&HEIGHT={height}&"
                f"LAYERS={wms_layer}&STYLES=&FORMAT=image/png&"
                f"QUERY_LAYERS={wms_layer}&INFO_FORMAT={info_format}&"
                f"I={i}&J={j}&FEATURE_COUNT={feature_count}"
            )

            # Perform the request and get the response
            response = requests.get(getfeatureinfo_url)
            if response.status_code == 200:
                feature_info = parse_xml_response(response.text.strip())
                feature_info['bestand_id'] = int(shape_rec.record.bestand_id)
                feature_info['shape_area'] = area  # Add the calculated area as integer
                if feature_info:
                    # Prepare the record dictionary
                    record = shape_rec.record.as_dict()
                    for field in new_fields:
                        if field in feature_info:
                            record[field] = feature_info[field]
                    
                    writer.record(**record)
                    
                    # Add the shape and record with the updated dictionary to the writer
                    writer.shape(shape_rec.shape)

        writer.close()

        # Upload the new shapefile components to S3
        print("Uploading intersection with Feature infos shapefile to S3...")
        s3_client.upload_file(local_out_shp_path, bucket_name, f"{s3_folder_feature_info}{forestID}_vector_w_HK_infos.shp")
        s3_client.upload_file(local_out_dbf_path, bucket_name, f"{s3_folder_feature_info}{forestID}_vector_w_HK_infos.dbf")
        s3_client.upload_file(local_out_shx_path, bucket_name, f"{s3_folder_feature_info}{forestID}_vector_w_HK_infos.shx")
        s3_client.upload_file(local_out_prj_path, bucket_name, f"{s3_folder_feature_info}{forestID}_vector_w_HK_infos.prj")

        print('Feature info request successful and shapefile updated.')

    print('No valid file found in the event.')