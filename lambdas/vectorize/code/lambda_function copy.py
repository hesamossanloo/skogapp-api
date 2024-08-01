import json
import xml.etree.ElementTree as ET
from osgeo import ogr, gdal
import re
import fiona
from shapely.geometry import shape, mapping
from shapely.validation import make_valid
import boto3

s3 = boto3.client('s3')
bucket_name = 'skogapp-lambda-generated-outputs'  # Replace with your bucket name
s3_folder = 'SkogAppHKVectorize/'  # S3 folder

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response

def download_svg_from_s3(bucket, key, download_path):
    s3.download_file(bucket, key, download_path)

def svg_to_shp(svg_path, shp_path, bbox, image_size):
    try:
        # Parse the SVG file
        tree = ET.parse(svg_path)
        root = tree.getroot()
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}

        # Create a new shapefile
        schema = {'geometry': 'Polygon', 'properties': [('bestand_id', 'int')]}
        with fiona.open(shp_path, 'w', driver='ESRI Shapefile', schema=schema, crs="EPSG:4326") as shp:
            for i, element in enumerate(root.findall('.//svg:path', namespaces)):
                d = element.attrib.get('d', '')
                if d:
                    coordinates = parse_svg_path(d)
                    geo_coords = pixel_to_geo(coordinates, bbox, image_size)
                    polygon = {'type': 'Polygon', 'coordinates': [geo_coords]}
                    shp.write({'geometry': polygon, 'properties': {'bestand_id': i}})

        print(f"Shapefile created at {shp_path}")
    except Exception as e:
        print(f"Error converting SVG to SHP: {str(e)}")
        
def intersect_shapefile_with_geojson(shapefile_path, geojson_dict, output_shapefile):
    with fiona.open(shapefile_path, 'r') as shapefile_src:
        schema = shapefile_src.schema.copy()
        crs = shapefile_src.crs

        with fiona.open(output_shapefile, 'w', 'ESRI Shapefile', schema, crs) as output:
            for shape_feat in shapefile_src:
                shape_geom = shape(shape_feat['geometry'])
                shape_geom = make_valid(shape_geom)
                for geojson_feat in geojson_dict['features']:
                    geojson_geom = shape(geojson_feat['geometry'])
                    geojson_geom = make_valid(geojson_geom)
                    if shape_geom.intersects(geojson_geom):
                        intersection = shape_geom.intersection(geojson_geom)
                        if intersection.is_empty:
                            continue
                        output.write({
                            'geometry': mapping(intersection),
                            'properties': shape_feat['properties'],
                        })

def calculate_bounds(multipolygon):
    envelope = multipolygon.GetEnvelope()
    return envelope

def pixel_to_geo(pixel_coords, bbox, image_size):
    min_x, min_y, max_x, max_y = bbox
    img_width, img_height = image_size

    geo_coords = []
    for x, y in pixel_coords:
        geo_x = min_x + (x / img_width) * (max_x - min_x)
        geo_y = max_y - (y / img_height) * (max_y - min_y)
        geo_coords.append((geo_x, geo_y))

    return geo_coords

def parse_svg_path(path_data):
    command_re = re.compile(r'([MmLlHhVvCcSsQqTtAaZz])|([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)')
    
    def consume_numbers(it, count):
        return [float(next(it)[1]) for _ in range(count)]
    
    commands = command_re.findall(path_data)
    command_iter = iter(commands)
    current_pos = [0, 0]
    coordinates = []
    
    try:
        while True:
            command = next(command_iter)
            if command[0]:
                cmd_type = command[0]
            else:
                continue

            if cmd_type.upper() in 'ML':
                while True:
                    coords = consume_numbers(command_iter, 2)
                    current_pos = coords
                    coordinates.append(current_pos.copy())
                    if cmd_type.islower():
                        cmd_type = 'l'
                    if command_re.match(' '.join([next(command_iter)[1] for _ in range(2)])) is None:
                        break

            elif cmd_type.upper() in 'HV':
                while True:
                    if cmd_type.upper() == 'H':
                        current_pos[0] = float(next(command_iter)[1])
                    else:
                        current_pos[1] = float(next(command_iter)[1])
                    coordinates.append(current_pos.copy())
                    if cmd_type.islower():
                        cmd_type = cmd_type.lower()
                    if command_re.match(next(command_iter)[1]) is None:
                        break

            elif cmd_type.upper() == 'Z':
                coordinates.append(current_pos.copy())

    except StopIteration:
        pass
    
    return coordinates

def vectorize(event):
    gdal.SetConfigOption('OGR_GEOMETRY_ACCEPT_UNCLOSED_RING', 'NO')
    
    geojson_dict = json.loads(event['body'])
    forestID = geojson_dict.get('forestID')
    
    if not forestID:
        response = {
            'statusCode': 400,
            'body': json.dumps({'message': 'Missing forestID'})
        }
        return add_cors_headers(response)
    
    if geojson_dict['type'] != 'FeatureCollection':
        print("The provided GeoJSON data is not a FeatureCollection.")
        response = {
            'statusCode': 400,
            'body': json.dumps({'message': 'Invalid GeoJSON data. Must be a FeatureCollection.'})
        }
        return add_cors_headers(response)

    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for feature in geojson_dict['features']:
        geometry_json = json.dumps(feature['geometry'])
        ogr_geom = ogr.CreateGeometryFromJson(geometry_json)
        
        if ogr_geom is None:
            print("Failed to create geometry from GeoJSON.")
            response = {
                'statusCode': 400,
                'body': json.dumps({'message': 'Failed to create geometry from GeoJSON.'})
            }
            return add_cors_headers(response)
        
        bounds = calculate_bounds(ogr_geom)
        print(f"Bounds: {bounds}")
        
        min_x, max_x = min(min_x, bounds[0]), max(max_x, bounds[1])
        min_y, max_y = min(min_y, bounds[2]), max(max_y, bounds[3])
    
    combined_bounds_STR = f"{min_y},{min_x},{max_y},{max_x}"
    print(f"Combined Bounds Str: {combined_bounds_STR}")
    
    svg_path = "/tmp/downloaded_image_SVG_SHP_V2.svg"
    s3_key = f"{s3_folder}{forestID}_HK_image_cut.svg"
    
    try:
        download_svg_from_s3(bucket_name, s3_key, svg_path)
        new_shp_path = "/tmp/downloaded_image_SVG_SHP_V2.shp"
        svg_to_shp(svg_path, new_shp_path, [min_x, min_y, max_x, max_y], (1024, 1024))

        output_shp_path = "/tmp/intersection_SVG_SHP_V2.shp"
        intersect_shapefile_with_geojson(new_shp_path, geojson_dict, output_shp_path)

        s3_key_output = f"{s3_folder}vectorized_HK.shp"
        s3.upload_file(output_shp_path, bucket_name, s3_key_output)
        
        s3_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key_output}"
        print(f"Intersection shapefile saved at {s3_url}")
        response = {
            'statusCode': 200,
            'body': json.dumps({'message': 'SVG processing and intersection completed successfully.', 's3_url':s3_url})
        }
        return add_cors_headers(response)
    except Exception as e:
        print(f"Error during SVG processing: {str(e)}")
        response = {
            'statusCode': 500,
            'body': json.dumps({'message': 'SVG processing failed.', 'error': str(e)})
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
        return vectorize(event)
    else:
        response = {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method not allowed'})
        }
        return add_cors_headers(response)