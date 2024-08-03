import json
import xml.etree.ElementTree as ET
from osgeo import ogr, gdal
import re
import shapefile
shapefile.VERBOSE = False

from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.validation import make_valid
from shapely.geometry.polygon import orient
import boto3

s3 = boto3.client('s3')
bucket_name = 'skogapp-lambda-generated-outputs'  # Replace with your bucket name
s3_folder_cut = 'SkogAppHKCut/'  # S3 folder
s3_folder_vectorize = 'SkogAppHKVectorize/'  # S3 folder

# Create a projection file
prj_content = """GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]"""

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response

def download_svg_from_s3(bucket, key, download_path):
    print(f"Downloading SVG file from S3: {key}")
    s3.download_file(bucket, key, download_path)

def normalize_polygon(coords, precision=6):
    """
    Normalize and simplify polygon coordinates for comparison.
    """
    # Create a Polygon object
    polygon = Polygon(coords)
    
    # Simplify the polygon to remove minor differences
    simplified = polygon.simplify(tolerance=0.000001, preserve_topology=True)
    
    # Ensure the coordinates are in a consistent order
    oriented = orient(simplified)
    
    # Round the coordinates for precision
    rounded_coords = [(round(x, precision), round(y, precision)) for x, y in oriented.exterior.coords]
    
    return rounded_coords

def svg_to_shp(svg_path, shp_path, bbox, image_size, tolerance=6):
    try:
        # Parse the SVG file
        tree = ET.parse(svg_path)
        root = tree.getroot()
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}

        # Create a new shapefile
        with shapefile.Writer(shp_path, shapefile.POLYGON) as shp:
            shp.field('bestand_id', 'N')

            processed_polygons = set()

            for i, element in enumerate(root.findall('.//svg:path', namespaces)):
                d = element.attrib.get('d', '')
                if d:
                    coordinates = parse_svg_path(d)
                    geo_coords = pixel_to_geo(coordinates, bbox, image_size)

                    # Normalize and simplify the polygon coordinates
                    normalized_coords = normalize_polygon(geo_coords, precision=tolerance)
                    polygon_tuple = tuple(normalized_coords)

                    if polygon_tuple not in processed_polygons:
                        # Define the polygon
                        polygon = [geo_coords]
                        shp.poly(polygon)
                        shp.record(i)

                        # Add the polygon to the set of processed polygons
                        processed_polygons.add(polygon_tuple)

        with open(f"{shp_path.replace('.shp', '.prj')}", 'w') as prj:
            prj.write(prj_content)

        print(f"Shapefile created at {shp_path}")
    except Exception as e:
        print(f"Error converting SVG to SHP: {str(e)}")
        
def intersect_shapefile_with_geojson(shapefile_path, geojson_dict, output_shapefile):
    print(f"Intersecting shapefile with GeoJSON: {shapefile_path}")
    try:
        with shapefile.Reader(shapefile_path) as shapefile_src:
            print(f"Shapefile fields: {shapefile_src.fields}")
            fields = shapefile_src.fields[1:]  # Skip the DeletionFlag field
            field_names = [field[0] for field in fields]

            with shapefile.Writer(output_shapefile) as output:
                print(f"Trying to write the intersection to: {output_shapefile}")
                output.fields = fields
                print("Processing shape records...")
                for shape_rec in shapefile_src.shapeRecords():
                    try:
                        shape_geom = shape(shape_rec.shape.__geo_interface__)
                        shape_geom = make_valid(shape_geom)  # Fix invalid geometry
                        
                        # Ensure the geometry is a valid Polygon or MultiPolygon
                        if not isinstance(shape_geom, (Polygon, MultiPolygon)):
                            # print(f"Skipping invalid geometry: {shape_geom}")
                            continue

                        for geojson_feat in geojson_dict['features']:
                            geojson_geom = shape(geojson_feat['geometry'])
                            geojson_geom = make_valid(geojson_geom)  # Fix invalid geometry
                            
                            # Ensure the GeoJSON geometry is a valid Polygon or MultiPolygon
                            if not isinstance(geojson_geom, (Polygon, MultiPolygon)):
                                # print(f"Skipping invalid GeoJSON geometry: {geojson_geom}")
                                continue

                            if shape_geom.intersects(geojson_geom):
                                intersection = shape_geom.intersection(geojson_geom)
                                if intersection.is_empty:
                                    continue
                                # Write the intersected part to the output shapefile
                                output.shape(intersection.__geo_interface__)
                                output.record(*[shape_rec.record[field] for field in field_names])
                    except Exception as e:
                        print(f"Error processing shape record: {e}")
    except Exception as e:
        print(f"Error reading shapefile: {e}")
    
    # Create the .prj file
    prj_path = output_shapefile.replace('.shp', '.prj')
    with open(prj_path, 'w') as prj_file:
        prj_file.write(prj_content)
    print(f"Projection file saved at {prj_path}")

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

def vectorize(geojson_dict, forestID):
    gdal.SetConfigOption('OGR_GEOMETRY_ACCEPT_UNCLOSED_RING', 'NO')
    
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
        
        min_x, max_x = min(min_x, bounds[0]), max(max_x, bounds[1])
        min_y, max_y = min(min_y, bounds[2]), max(max_y, bounds[3])
    
    combined_bounds_STR = f"{min_y},{min_x},{max_y},{max_x}"
    print(f"Combined Bounds Str: {combined_bounds_STR}")
    
    downloaded_svg_path = "/tmp/downloaded_image.svg"
    s3_key_cut = f"{s3_folder_cut}{forestID}_HK_image_cut.svg"
    
    try:
        download_svg_from_s3(bucket_name, s3_key_cut, downloaded_svg_path)
        downloaded_shp_path = "/tmp/downloaded_image.shp"
        svg_to_shp(downloaded_svg_path, downloaded_shp_path, [min_x, min_y, max_x, max_y], (1024, 1024))

        intersected_shp_path = "/tmp/intersection_image.shp"
        intersected_dbf_path = "/tmp/intersection_image.dbf"
        intersected_shx_path = "/tmp/intersection_image.shx"
        intersected_prj_path = "/tmp/intersection_image.prj"
        intersect_shapefile_with_geojson(downloaded_shp_path, geojson_dict, intersected_shp_path)

        print("Uploading intersection shapefile to S3...")
        s3_key_output_shp = f"{s3_folder_vectorize}{forestID}_vectorized_HK.shp"
        s3_key_output_dbf = f"{s3_folder_vectorize}{forestID}_vectorized_HK.dbf"
        s3_key_output_shx = f"{s3_folder_vectorize}{forestID}_vectorized_HK.shx"
        s3_key_output_prj = f"{s3_folder_vectorize}{forestID}_vectorized_HK.prj"
        s3.upload_file(intersected_shp_path, bucket_name, s3_key_output_shp)
        s3.upload_file(intersected_dbf_path, bucket_name, s3_key_output_dbf)
        s3.upload_file(intersected_shx_path, bucket_name, s3_key_output_shx)
        s3.upload_file(intersected_prj_path, bucket_name, s3_key_output_prj)
        
        s3_url_shp = f"https://{bucket_name}.s3.amazonaws.com/{s3_key_output_shp}"
        s3_url_dbf = f"https://{bucket_name}.s3.amazonaws.com/{s3_key_output_dbf}"
        s3_url_shx = f"https://{bucket_name}.s3.amazonaws.com/{s3_key_output_shx}"
        s3_url_prj = f"https://{bucket_name}.s3.amazonaws.com/{s3_key_output_prj}"
        
        print(f"Intersection shapefile saved at {s3_url_shp}")
        response = {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'SVG processing and intersection completed successfully.',
                's3_url_shp': s3_url_shp,
                's3_url_dbf': s3_url_dbf,
                's3_url_shx': s3_url_shx,
                's3_url_prj': s3_url_prj
            })
        }
        return add_cors_headers(response)
    except Exception as e:
        print(f"Error during SVG processing: {str(e)}")
        response = {
            'statusCode': 500,
            'body': json.dumps({'message': 'SVG processing failed.', 'error': str(e)})
        }
        return add_cors_headers(response)

def handle_api_event(event):
    if event['httpMethod'] == 'OPTIONS':
        response = {
            'statusCode': 200,
            'body': json.dumps({})
        }
        return add_cors_headers(response)
    elif event['httpMethod'] == 'POST':
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
        return vectorize(geojson_dict, forestID)
    else:
        response = {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method not allowed'})
        }
        return add_cors_headers(response)

def handle_sqs_event(event):
    for record in event['Records']:
        # Process each SQS message here
        message_body = record['body']
        print(f"Processing SQS message")
        geojson_dict = json.loads(message_body)
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
        
    return vectorize(geojson_dict, forestID)
    
def lambda_handler(event, context):
    # Check if the event is from API Gateway
    if 'httpMethod' in event:
        print(f"Received API Gateway event: {event['httpMethod']}")
        return handle_api_event(event)
    
    # Check if the event is from SQS
    elif 'Records' in event and event['Records'][0]['eventSource'] == 'aws:sqs':
        print(f"Received SQS event: {event['Records'][0]['eventSource']}")
        return handle_sqs_event(event)
    
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'message': 'Unsupported event source'})
        }