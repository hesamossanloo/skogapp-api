import os
from flask import Flask, request, jsonify
import json
import xml.etree.ElementTree as ET
from osgeo import ogr, gdal, osr
from urllib.parse import urlencode
import requests
import re

app = Flask(__name__)

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

# Function to check if path coordinates intersect with the GeoJSON feature
def path_intersects_geojson(coordinates, geojson_feature):
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in coordinates:
        ring.AddPoint(x, y)
    if (coordinates[0][0], coordinates[0][1]) != (coordinates[-1][0], coordinates[-1][1]):
        ring.AddPoint(coordinates[0][0], coordinates[0][1])
    path_geom = ogr.Geometry(ogr.wkbPolygon)
    path_geom.AddGeometry(ring)
    
    geometry_json = json.dumps(geojson_feature['geometry'])
    ogr_geom = ogr.CreateGeometryFromJson(geometry_json)
    
    intersects = path_geom.Intersects(ogr_geom)

    return intersects

@app.route('/cut', methods=['POST'])
def cut():
    geojson_dict = request.json
    
    if geojson_dict['type'] != 'FeatureCollection':
        return jsonify({'message': 'Invalid GeoJSON data. Must be a FeatureCollection.'})

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

    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for feature in geojson_dict['features']:
        geometry_json = json.dumps(feature['geometry'])
        ogr_geom = ogr.CreateGeometryFromJson(geometry_json)
        
        if ogr_geom is None:
            return jsonify({'message': 'Failed to create geometry from GeoJSON.'})
        
        bounds = calculate_bounds(ogr_geom)
        min_x, max_x = min(min_x, bounds[0]), max(max_x, bounds[1])
        min_y, max_y = min(min_y, bounds[2]), max(max_y, bounds[3])
    
    combined_bounds_STR = f"{min_y},{min_x},{max_y},{max_x}"
    print("Combined Bounds Str:", combined_bounds_STR)
    WMS_params['BBOX'] = combined_bounds_STR
    encoded_params = urlencode(WMS_params, safe=',:')
    WMS_URL = base_URL + encoded_params
    
    svg_path = "outputs/downloaded_image.svg"

    response = requests.get(WMS_URL)
    if response.status_code == 200:
        with open(svg_path, 'wb') as file:
            file.write(response.content)
    else:
        return jsonify({'message': 'Failed to download image.', 'status_code': response.status_code})

    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}
        
        extracted_features = []
        for element in root.findall('.//svg:path', namespaces):
            d = element.attrib.get('d', '')
            if d:
                coordinates = parse_svg_path(d)
                geo_coords = pixel_to_geo(coordinates, [min_x, min_y, max_x, max_y], (1024, 1024))

                for feature in geojson_dict['features']:
                    if path_intersects_geojson(geo_coords, feature):
                        extracted_features.append(element)
                        break

        new_svg = ET.Element('svg', root.attrib)
        for feature in extracted_features:
            new_svg.append(feature)
        
        new_svg_path = "outputs/extracted_features_V2.svg"
        ET.ElementTree(new_svg).write(new_svg_path)

        return jsonify({'message': 'SVG processing completed successfully.', 'output_path': new_svg_path})
    except Exception as e:
        return jsonify({'message': 'SVG processing failed.', 'error': str(e)})

if __name__ == '__main__':
    gdal.SetConfigOption('OGR_GEOMETRY_ACCEPT_UNCLOSED_RING', 'NO')
    app.run(debug=True)