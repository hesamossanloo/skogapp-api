import json
from osgeo import gdal, ogr
from urllib.parse import urlencode
import requests

# Function to calculate bounds of a MultiPolygon
def calculate_bounds(multipolygon):
    envelope = multipolygon.GetEnvelope()  # Returns a tuple (minX, maxX, minY, maxY)
    return envelope

def cut(event, context):
    geojson_dict = json.loads(event['body'])
    
    # Initialize variables for combined bounds
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    
    # Check if the GeoJSON data is a FeatureCollection
    if geojson_dict['type'] == 'FeatureCollection':
        for feature in geojson_dict['features']:
            geometry_json = json.dumps(feature['geometry'])
            ogr_geom = ogr.CreateGeometryFromJson(geometry_json)
            
            if ogr_geom is None:
                response = {
                    'statusCode': 400,
                    'body': json.dumps({'message': 'Failed to create geometry from GeoJSON.'})
                }
                return add_cors_headers(response)
            else:
                bounds = calculate_bounds(ogr_geom)
                min_x, max_x = min(min_x, bounds[0]), max(max_x, bounds[1])
                min_y, max_y = min(min_y, bounds[2]), max(max_y, bounds[3])
                
        combined_bounds_STR = f"{min_y},{min_x},{max_y},{max_x}"
    else:
        response = {
            'statusCode': 400,
            'body': json.dumps({'message': 'Invalid GeoJSON data. Must be a FeatureCollection.'})
        }
        return add_cors_headers(response)
            
    base_URL = "https://wms.nibio.no/cgi-bin/skogbruksplan?"
    WMS_params = {
        "LANGUAGE": "nor",
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "CRS": "EPSG:4326",
        "WIDTH": "1024",
        "HEIGHT": "1024",
        "LAYERS": "hogstklasser",
        "STYLES": "",
        "FORMAT": "image/tiff",
        "DPI": "144",
        "MAP_RESOLUTION": "144",
        "FORMAT_OPTIONS": "dpi:144",
        "TRANSPARENT": "TRUE"
    }
    WMS_params['BBOX'] = combined_bounds_STR
    encoded_params = urlencode(WMS_params, safe=',:')
    WMS_URL = base_URL + encoded_params
    
    downloaded_path = "/tmp/downloaded_image.tif"
    output_path = "/tmp/cut_image.png"

    WMS_response = requests.get(WMS_URL, timeout=(10, 30))
    if WMS_response.status_code == 200:
        with open(downloaded_path, 'wb') as file:
            file.write(WMS_response.content)
    else:
        response = {
            'statusCode': WMS_response.status_code,
            'body': json.dumps({'message': 'Failed to download image.'})
        }
        return add_cors_headers(response)
    
    gdal.UseExceptions()
    try:
        geojson_STR = json.dumps(geojson_dict)
        geojson_vsimem_path = '/vsimem/temp_geojson.json'
        gdal.FileFromMemBuffer(geojson_vsimem_path, geojson_STR)
        
        result = gdal.Warp(output_path, downloaded_path, format='PNG', dstNodata=0, outputBounds=[min_x, min_y, max_x, max_y], cutlineDSName=geojson_vsimem_path, cropToCutline=True)
        
        if not result:
            raise Exception("GDAL Warp operation failed.")
    
        gdal.Unlink(geojson_vsimem_path)
        WMS_response = {
            'statusCode': 200,
            'body': json.dumps({'message': 'Image processing completed successfully.', 'output_path': output_path})
        }
        return add_cors_headers(WMS_response)
    except Exception as e:
        WMS_response = {
            'statusCode': 500,
            'body': json.dumps({'message': 'Image processing failed.', 'error': str(e)})
        }
        return add_cors_headers(WMS_response)

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response  

def lambda_handler(event, context):
    if event['httpMethod'] == 'OPTIONS':
        response = {
            'statusCode': 200,
            'body': json.dumps({})
        }
        return add_cors_headers(response)
    elif event['httpMethod'] == 'POST':
        return cut(event, context)
    else:
        response = {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method not allowed'})
        }
        return add_cors_headers(response)