import json
import xml.etree.ElementTree as ET
from osgeo import ogr, gdal, osr
import shapefile
shapefile.VERBOSE = False

from shapely.geometry import shape, Polygon, MultiPolygon, LinearRing
from shapely.validation import make_valid
import boto3

s3 = boto3.client('s3')
bucket_name = 'skogapp-lambda-generated-outputs'  # Replace with your bucket name
s3_folder_cut = 'SkogAppHKCut/'  # S3 folder
s3_folder_vectorize = 'SkogAppHKVectorize/'  # S3 folder

# Create a projection file
prj_content = """GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]"""

def log(forestID, message):
    if forestID:
        print(f"forestID: {forestID} - {message}")
    else:
        forestID = "unknown"
        print(f"forestID: {forestID} - {message}")

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response

def parse_svg(svg_file, image_size, bbox):
    svg_width, svg_height = image_size
    # Parse the SVG file
    tree = ET.parse(svg_file)
    root = tree.getroot()

    # SVG namespace (to handle SVG elements correctly)
    ns = {'svg': 'http://www.w3.org/2000/svg'}

    paths = []
    for path in root.findall('.//svg:path', ns):
        path_data = path.attrib['d']
        points = convert_path_to_polygon(path_data, svg_width, svg_height, bbox)
        if points:
            paths.append(points)
    
    polygons = create_polygons_from_paths(paths)
    
    return polygons

def convert_path_to_polygon(path_data, svg_width, svg_height, bbox):
    min_x, min_y, max_x, max_y = bbox
    paths = []
    points = []
    commands = path_data.split()
    i = 0
    while i < len(commands):
        if commands[i] == 'M':  # Move to
            if points:  # If there's an existing ring, finalize it
                if len(points) > 2:
                    points.append(points[0])  # Close the ring
                    paths.append(points)
                points = []
            x, y = float(commands[i+1]), float(commands[i+2])
            lon = min_x + (x / svg_width) * (max_x - min_x)
            lat = min_y + (1 - (y / svg_height)) * (max_y - min_y)
            points.append((lon, lat))
            i += 3
        elif commands[i] == 'L':  # Line to
            x, y = float(commands[i+1]), float(commands[i+2])
            lon = min_x + (x / svg_width) * (max_x - min_x)
            lat = min_y + (1 - (y / svg_height)) * (max_y - min_y)
            points.append((lon, lat))
            i += 3
        elif commands[i] == 'Z':  # Close path
            if len(points) > 2:
                points.append(points[0])  # Close the ring
                paths.append(points)
            points = []
            i += 1
        else:
            i += 1

    if points and len(points) > 2:
        points.append(points[0])  # Close the ring
        paths.append(points)

    return paths

def create_polygons_from_paths(paths, tolerance=1e-9, simplify_tolerance=1e-6):
    unique_polygons = []
    
    for path in paths:
        if len(path) > 1:
            # First ring is the exterior, the rest are holes
            exterior = LinearRing(path[0])
            holes = [LinearRing(hole) for hole in path[1:] if len(hole) > 3]  # Ensure holes are valid rings
            polygon = Polygon(shell=exterior, holes=holes)
        else:
            # Only one ring, no holes
            exterior = LinearRing(path[0])
            polygon = Polygon(shell=exterior)

        # Simplify the polygon slightly to remove small variations
        simplified_polygon = polygon.simplify(simplify_tolerance, preserve_topology=True)

        # Normalize the polygon by buffering with a small distance and then reversing the buffer
        normalized_polygon = simplified_polygon.buffer(tolerance).buffer(-tolerance)

        # Check if this normalized polygon is equal to any existing one
        is_duplicate = any(existing_polygon.equals(normalized_polygon) for existing_polygon in unique_polygons)
        
        if not is_duplicate:
            unique_polygons.append(normalized_polygon)

    return unique_polygons

def write_polygons_to_shapefile(polygons, shp_file_path):
    driver = ogr.GetDriverByName("ESRI Shapefile")
    data_source = driver.CreateDataSource(shp_file_path)
    
    spatial_ref = osr.SpatialReference()
    spatial_ref.ImportFromEPSG(4326)
    
    layer = data_source.CreateLayer("layer", geom_type=ogr.wkbPolygon, srs=spatial_ref)
    
    field_name = ogr.FieldDefn("bestand_id", ogr.OFTInteger)
    layer.CreateField(field_name)
    
    for i, polygon in enumerate(polygons):
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("bestand_id", i + 1)
        
        wkt = polygon.wkt
        geom = ogr.CreateGeometryFromWkt(wkt)
        feature.SetGeometry(geom)
        
        layer.CreateFeature(feature)
        feature = None
        # Close and save the data source
    data_source = None
    
    # Create a .prj file for the shapefile
    create_prj_file(shp_file_path, spatial_ref)

def create_prj_file(shp_file_path, spatial_ref):
    # Write the .prj file
    prj_file_path = shp_file_path.replace('.shp', '.prj')
    with open(prj_file_path, 'w') as prj_file:
        prj_file.write(spatial_ref.ExportToWkt())
        
def download_svg_from_s3(bucket, key, download_path, forestID):
    log(forestID, f"Downloading SVG file from S3: {key}")
    try:
        s3.download_file(bucket, key, download_path)
    except Exception as e:
        log(forestID, f"Error downloading SVG file: {e}")
        raise e

def intersect_shapefile_with_geojson(shapefile_path, geojson_dict, output_shapefile, forestID):
    try:
        with shapefile.Reader(shapefile_path) as shapefile_src:
            log(forestID, f"Shapefile fields: {shapefile_src.fields}")
            fields = shapefile_src.fields[1:]  # Skip the DeletionFlag field
            field_names = [field[0] for field in fields]

            with shapefile.Writer(output_shapefile) as output:
                log(forestID, f"Writing the intersection to: {output_shapefile}")
                output.fields = fields
                log(forestID, "Processing shape records...")
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
                        log(forestID, f"Error processing shape record: {e}")
    except Exception as e:
        log(forestID, f"Error reading shapefile: {e}")
    
    # Create the .prj file
    prj_path = output_shapefile.replace('.shp', '.prj')
    with open(prj_path, 'w') as prj_file:
        prj_file.write(prj_content)
    log(forestID, f"Projection file saved at {prj_path}")

def calculate_bounds(multipolygon):
    envelope = multipolygon.GetEnvelope()
    return envelope

def vectorize(geojson_dict, forestID):
    gdal.SetConfigOption('OGR_GEOMETRY_ACCEPT_UNCLOSED_RING', 'NO')
    
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for feature in geojson_dict['features']:
        geometry_json = json.dumps(feature['geometry'])
        ogr_geom = ogr.CreateGeometryFromJson(geometry_json)
        
        if ogr_geom is None:
            log(forestID, "Failed to create geometry from GeoJSON.")
            response = {
                'statusCode': 400,
                'body': json.dumps({'message': 'Failed to create geometry from GeoJSON.'})
            }
            return add_cors_headers(response)
        
        bounds = calculate_bounds(ogr_geom)
        
        min_x, max_x = min(min_x, bounds[0]), max(max_x, bounds[1])
        min_y, max_y = min(min_y, bounds[2]), max(max_y, bounds[3])
    
    combined_bounds_STR = f"{min_y},{min_x},{max_y},{max_x}"
    log(forestID, f"Combined bounds: {combined_bounds_STR}")
    
    downloaded_svg_path = "/tmp/downloaded_image.svg"
    s3_key_cut = f"{s3_folder_cut}{forestID}_HK_image_cut.svg"
    
    try:
        download_svg_from_s3(bucket_name, s3_key_cut, downloaded_svg_path, forestID)
        log(forestID, f"Downloaded SVG file from S3: {s3_key_cut}")
        downloaded_shp_path = "/tmp/downloaded_image.shp"
        log(forestID, f"Parsing SVG file: {downloaded_svg_path}")
        # Parse the SVG with the bounding box and image size and write to shapefile
        polygons = parse_svg(downloaded_svg_path, (1024, 1024), [min_x, min_y, max_x, max_y])
        log(forestID, f"Number of unique polygons: {len(polygons)}")
        
        log(forestID, f"Writing polygons to shapefile: {downloaded_shp_path}")
        write_polygons_to_shapefile(polygons, downloaded_shp_path)
        intersected_shp_path = "/tmp/intersection_image.shp"
        intersected_dbf_path = "/tmp/intersection_image.dbf"
        intersected_shx_path = "/tmp/intersection_image.shx"
        intersected_prj_path = "/tmp/intersection_image.prj"
        
        log(forestID, f"Intersecting shapefile with GeoJSON: {downloaded_shp_path}")
        intersect_shapefile_with_geojson(downloaded_shp_path, geojson_dict, intersected_shp_path, forestID)

        log(forestID, "Uploading intersection shapefile to S3...")
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
        
        log(forestID, f"Intersection shapefile saved at {s3_url_shp}")
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
        log(forestID, f"Error during SVG processing: {str(e)}")
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
        if not geojson_dict:
            response = {
                'statusCode': 400,
                'body': json.dumps({'message': 'Invalid GeoJSON data'})
            }
            return add_cors_headers(response)
            
        forestID = geojson_dict.get('forestID')
        if not forestID:
            response = {
                'statusCode': 400,
                'body': json.dumps({'message': 'Missing forestID'})
            }
            return add_cors_headers(response)
        
        log(forestID, "Received API request.")
        if geojson_dict['type'] != 'FeatureCollection':
            log(forestID, "Invalid GeoJSON data. Must be a FeatureCollection.")
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
        if not message_body:
            response = {
                'statusCode': 400,
                'body': json.dumps({'message': 'Missing message body'})
            }
            return add_cors_headers(response)
        
        geojson_dict = json.loads(message_body)
        if not geojson_dict:
            response = {
                'statusCode': 400,
                'body': json.dumps({'message': 'Invalid message body'})
            }
            return add_cors_headers(response)

        forestID = geojson_dict.get('forestID')
        if not forestID:
            response = {
                'statusCode': 400,
                'body': json.dumps({'message': 'Missing forestID'})
            }
            return add_cors_headers(response)
        
        log(forestID, "Processing SQS message.")
        if geojson_dict['type'] != 'FeatureCollection':
            log(forestID, "Invalid GeoJSON data. Must be a FeatureCollection.")
            response = {
                'statusCode': 400,
                'body': json.dumps({'message': 'Invalid GeoJSON data. Must be a FeatureCollection.'})
            }
            return add_cors_headers(response)
        
    return vectorize(geojson_dict, forestID)
    
def lambda_handler(event, context):
    # Check if the event is from API Gateway
    if 'httpMethod' in event:
        return handle_api_event(event)
    
    # Check if the event is from SQS
    elif 'Records' in event and event['Records'][0]['eventSource'] == 'aws:sqs':
        return handle_sqs_event(event)
    
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'message': 'Unsupported event source'})
        }