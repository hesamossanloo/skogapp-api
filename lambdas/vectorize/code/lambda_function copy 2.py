import json
import xml.etree.ElementTree as ET
from osgeo import ogr, gdal
from urllib.parse import urlencode
import requests
import re
import shapefile
from shapely.geometry import shape, mapping
from shapely.validation import make_valid

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response

def svg_to_shp(svg_path, shp_path, bbox, image_size):
    try:
        # Parse the SVG file
        tree = ET.parse(svg_path)
        root = tree.getroot()
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}

        # Create a new shapefile
        with shapefile.Writer(shp_path, shapefile.POLYGON) as shp:
            shp.field('bestand_id', 'N')

            for i, element in enumerate(root.findall('.//svg:path', namespaces)):
                d = element.attrib.get('d', '')
                if d:
                    coordinates = parse_svg_path(d)
                    geo_coords = pixel_to_geo(coordinates, bbox, image_size)

                    # Define the polygon
                    polygon = [geo_coords]
                    shp.poly(polygon)
                    shp.record(i)

        # Create a projection file
        prj_content = """GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]"""
        with open(f"{shp_path.replace('.shp', '.prj')}", 'w') as prj:
            prj.write(prj_content)

        print(f"Shapefile created at {shp_path}")
    except Exception as e:
        print(f"Error converting SVG to SHP: {str(e)}")
        
def intersect_shapefile_with_geojson(shapefile_path, geojson_dict, output_shapefile):
    with shapefile.Reader(shapefile_path) as shp:
        fields = shp.fields[1:]  # Skip the DeletionFlag field
        field_names = [field[0] for field in fields]
        crs = shp.crs  # Assuming the shapefile has a CRS attribute

        with shapefile.Writer(output_shapefile) as writer:
            writer.fields = shp.fields

            for shape_rec in shp.iterShapeRecords():
                shape_geom = shape(shape_rec.shape.__geo_interface__)
                shape_geom = make_valid(shape_geom)  # Fix invalid geometry
                for geojson_feat in geojson_dict['features']:
                    geojson_geom = shape(geojson_feat['geometry'])
                    geojson_geom = make_valid(geojson_geom)  # Fix invalid geometry
                    if shape_geom.intersects(geojson_geom):
                        intersection = shape_geom.intersection(geojson_geom)
                        if intersection.is_empty:
                            continue
                        # Write the intersected part to the output shapefile
                        writer.record(*[shape_rec.record[field] for field in field_names])
                        writer.shape(mapping(intersection))
                        
# Function to calculate bounds of a MultiPolygon
def calculate_bounds(multipolygon):
    envelope = multipolygon.GetEnvelope()  # Returns a tuple (minX, maxX, minY, maxY)
    return envelope

# Function to convert pixel coordinates to geographic coordinates
def pixel_to_geo(pixel_coords, bbox, image_size):
    min_x, min_y, max_x, max_y = bbox
    img_width, img_height = image_size

    geo_coords = []
    for x, y in pixel_coords:
        x = float(x)
        y = float(y)
        img_width = float(img_width)
        img_height = float(img_height)
        
        geo_x = min_x + (x / img_width) * (max_x - min_x)
        geo_y = max_y - (y / img_height) * (max_y - min_y)
        geo_coords.append((geo_x, geo_y))

    return geo_coords

# Function to parse SVG path data
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
                coordinates.append(coordinates[0].copy())

    except StopIteration:
        pass
    
    return coordinates

def vectorize(event):
    gdal.SetConfigOption('OGR_GEOMETRY_ACCEPT_UNCLOSED_RING', 'NO')
    geojson_dict = json.loads(event['body'])

    if geojson_dict['type'] != 'FeatureCollection':
        print("The provided GeoJSON data is not a FeatureCollection.")
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
        "FORMAT": "image/svg+xml",
        "DPI": "144",
        "MAP_RESOLUTION": "144",
        "FORMAT_OPTIONS": "dpi:144",
        "TRANSPARENT": "TRUE"
    }

    # Combine all feature bounds into a single bounding box for WMS request
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
    WMS_params['BBOX'] = combined_bounds_STR
    encoded_params = urlencode(WMS_params, safe=',:')
    WMS_URL = base_URL + encoded_params
    print(f"WMS Source: {WMS_URL}")
    
    svg_path = "outputs/downloaded_image_SVG_SHP_V2.svg"

    response = requests.get(WMS_URL)
    if response.status_code == 200:
        with open(svg_path, 'wb') as file:
            file.write(response.content)
    else:
        print(f"Failed to download image. Status code: {response.status_code}")
        response = {
            'statusCode': response.status_code,
            'body': json.dumps({'message': 'Failed to download image.'})
        }
        return add_cors_headers(response)

    try:
        new_shp_path = "outputs/downloaded_image_SVG_SHP_V2.shp"
        svg_to_shp(svg_path, new_shp_path, [min_x, min_y, max_x, max_y], (1024, 1024))

        # Perform intersection directly with GeoJSON
        output_shp_path = "outputs/intersection_SVG_SHP_V2.shp"
        intersect_shapefile_with_geojson(new_shp_path, geojson_dict, output_shp_path)

        print(f"Intersection shapefile saved at {output_shp_path}")
        response = {
            'statusCode': 200,
            'body': json.dumps({'message': 'SVG processing and intersection completed successfully.', 'output_path': output_shp_path})
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