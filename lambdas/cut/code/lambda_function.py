import json
from osgeo import gdal, ogr
from urllib.parse import urlencode
import requests
import boto3

s3 = boto3.client('s3')
bucket_name = 'skogapp-lambda-generated-outputs'  # Replace with your bucket name
s3_folder = 'SkogAppHKCut/'  # S3 folder

def calculate_bounds(multipolygon):
    envelope = multipolygon.GetEnvelope()  # Returns a tuple (minX, maxX, minY, maxY)
    return envelope

def cut(event):
    print("Starting the cut function.")
    geojson_dict = json.loads(event['body'])
    
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    forestID = geojson_dict.get('forestID')
    
    if not forestID:
        response = {
            'statusCode': 400,
            'body': json.dumps({'message': 'Missing forestID'})
        }
        return add_cors_headers(response)
    
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
        print(f"Combined bounds: {combined_bounds_STR}")
    else:
        response = {
            'statusCode': 400,
            'body': json.dumps({'message': 'Invalid GeoJSON data. Must be a FeatureCollection.'})
        }
        return add_cors_headers(response)
    
    base_URL = "https://wms.nibio.no/cgi-bin/skogbruksplan?"
    
    # Download TIF
    WMS_TIF_params = {
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
    WMS_TIF_params['BBOX'] = combined_bounds_STR
    encoded_params_tif = urlencode(WMS_TIF_params, safe=',:')
    WMS_URL_TIF = base_URL + encoded_params_tif
    
    downloaded_tif_path = "/tmp/downloaded_image.tif"
    output_png_path = "/tmp/cut_image.png"

    WMS_response_tif = requests.get(WMS_URL_TIF, timeout=(10, 30))
    if WMS_response_tif.status_code == 200:
        with open(downloaded_tif_path, 'wb') as file:
            file.write(WMS_response_tif.content)
    else:
        response = {
            'statusCode': WMS_response_tif.status_code,
            'body': json.dumps({'message': 'Failed to download TIF image.'})
        }
        return add_cors_headers(response)
    
    gdal.UseExceptions()
    try:
        print("Starting the GDAL Warp operation.")
        geojson_STR = json.dumps(geojson_dict)
        geojson_vsimem_path = '/vsimem/temp_geojson.json'
        gdal.FileFromMemBuffer(geojson_vsimem_path, geojson_STR)
        
        result = gdal.Warp(output_png_path, downloaded_tif_path, format='PNG', dstNodata=0, outputBounds=[min_x, min_y, max_x, max_y], cutlineDSName=geojson_vsimem_path, cropToCutline=True)
        
        if not result:
            raise Exception("GDAL Warp operation failed.")
    
        gdal.Unlink(geojson_vsimem_path)
        
        # Upload the processed PNG image to S3
        s3_key_png = f"{s3_folder}{forestID}_HK_image_cut.png"
        s3.upload_file(output_png_path, bucket_name, s3_key_png)
        
        s3_url_png = f"https://{bucket_name}.s3.amazonaws.com/{s3_key_png}"
    except Exception as e:
        response = {
            'statusCode': 500,
            'body': json.dumps({'message': 'PNG image processing failed.', 'error': str(e)})
        }
        return add_cors_headers(response)

    # Download SVG
    print("Downloading the SVG image.")
    WMS_SVG_params = WMS_TIF_params.copy()
    WMS_SVG_params["FORMAT"] = "image/svg+xml"
    encoded_params_svg = urlencode(WMS_SVG_params, safe=',:')
    WMS_URL_SVG = base_URL + encoded_params_svg
    
    downloaded_svg_path = "/tmp/downloaded_image.svg"

    WMS_response_svg = requests.get(WMS_URL_SVG, timeout=(10, 30))
    if WMS_response_svg.status_code == 200:
        with open(downloaded_svg_path, 'wb') as file:
            file.write(WMS_response_svg.content)
    else:
        response = {
            'statusCode': WMS_response_svg.status_code,
            'body': json.dumps({'message': 'Failed to download SVG image.'})
        }
        return add_cors_headers(response)

    # Upload the SVG file to S3
    try:
        print("Uploading the SVG file to S3.")
        s3_key_svg = f"{s3_folder}{forestID}_HK_image_cut.svg"
        s3.upload_file(downloaded_svg_path, bucket_name, s3_key_svg)
        
        s3_url_svg = f"https://{bucket_name}.s3.amazonaws.com/{s3_key_svg}"
        
        response = {
            'statusCode': 200,
            'body': json.dumps({'message': 'Image processing completed successfully.', 's3_url_png': s3_url_png, 's3_url_svg': s3_url_svg})
        }
        return add_cors_headers(response)
    except Exception as e:
        response = {
            'statusCode': 500,
            'body': json.dumps({'message': 'SVG upload failed.', 'error': str(e)})
        }
        return add_cors_headers(response)

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response  

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
        return cut(event)
    else:
        response = {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method not allowed'})
        }
        return add_cors_headers(response)