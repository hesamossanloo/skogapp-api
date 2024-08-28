import os
from flask import Flask, request, jsonify
import json
import xml.etree.ElementTree as ET
from osgeo import ogr, gdal, osr
from urllib.parse import urlencode
import requests

import shapefile
shapefile.VERBOSE = False

from shapely.geometry import shape, Polygon, MultiPolygon, LinearRing
from shapely.validation import make_valid, explain_validity
from shapely.ops import unary_union

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Define paths relative to the script's directory
forestID = "hDVCY6kT3XbEUu7FjcevxdgFash1"
downloaded_svg_from_cut_path = os.path.join(script_dir, f"outputs/vectorize/{forestID}.svg")
shp_from_svg_cut_path = os.path.join(script_dir, f"outputs/vectorize/{forestID}_whole_image.shp")
save_intersected_geojson_shp_path = os.path.join(script_dir, f"outputs/vectorize/{forestID}_intersected_image.shp")

# Create a projection file
prj_content = """GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]"""
        
app = Flask(__name__)

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
    print(f"Number of paths: {len(paths)}")
    count = 0
    for path in paths:
        print(f"Processing path {count}")
        try:
            if len(path) > 1:
                # First ring is the exterior, the rest are holes
                exterior = LinearRing(path[0])
                holes = [LinearRing(hole) for hole in path[1:] if len(hole) > 3]  # Ensure holes are valid rings
                polygon = Polygon(shell=exterior, holes=holes)
            else:
                # Only one ring, no holes
                exterior = LinearRing(path[0])
                polygon = Polygon(shell=exterior)

            # Validate and fix the polygon if necessary
            if not polygon.is_valid:
                print(f"Invalid polygon detected: {explain_validity(polygon)}")
                polygon = polygon.buffer(0)  # Attempt to fix the polygon
                if not polygon.is_valid:
                    print(f"Polygon could not be fixed with buffer(0): {explain_validity(polygon)}")
                    polygon = unary_union([polygon])  # Attempt to fix with unary_union
                    if not polygon.is_valid:
                        print(f"Polygon could not be fixed with unary_union: {explain_validity(polygon)}")
                        continue  # Skip this polygon if it cannot be fixed

            # Simplify the polygon slightly to remove small variations
            simplified_polygon = polygon.simplify(simplify_tolerance, preserve_topology=True)

            # Normalize the polygon by buffering with a small distance and then reversing the buffer
            normalized_polygon = simplified_polygon.buffer(tolerance).buffer(-tolerance)

            # Check if this normalized polygon is equal to any existing one
            is_duplicate = any(existing_polygon.equals(normalized_polygon) for existing_polygon in unique_polygons)

            if not is_duplicate:
                unique_polygons.append(normalized_polygon)
            print(f"Finished processing path {count}\n")
            count += 1
        except Exception as e:
            print(f"Exception occurred: {e}")
            continue

    return unique_polygons

def write_polygons_to_shapefile(polygons, shp_file_path):
    driver = ogr.GetDriverByName("ESRI Shapefile")
    print(f"Writing polygons to shapefile: {shp_file_path}")
    data_source = driver.CreateDataSource(shp_file_path)
    
    spatial_ref = osr.SpatialReference()
    spatial_ref.ImportFromEPSG(4326)
    
    layer = data_source.CreateLayer("layer", geom_type=ogr.wkbPolygon, srs=spatial_ref)
    
    field_name = ogr.FieldDefn("ID", ogr.OFTInteger)
    layer.CreateField(field_name)
    
    for i, polygon in enumerate(polygons):
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("ID", i + 1)
        
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
        
def intersect_shapefile_with_geojson(shapefile_path, geojson_dict, output_shapefile):
    try:
        with shapefile.Reader(shapefile_path) as shapefile_src:
            fields = shapefile_src.fields[1:]  # Skip the DeletionFlag field
            field_names = [field[0] for field in fields]

            with shapefile.Writer(output_shapefile) as output:
                output.fields = fields
                intersection_count = 0  # Initialize the counter

                for shape_rec in shapefile_src.shapeRecords():
                    try:
                        shape_geom = shape(shape_rec.shape.__geo_interface__)
                        shape_geom = make_valid(shape_geom)  # Fix invalid geometry
                        
                        # Ensure the geometry is a valid Polygon or MultiPolygon
                        if not isinstance(shape_geom, (Polygon, MultiPolygon)):
                            continue

                        for geojson_feat in geojson_dict['features']:
                            geojson_geom = shape(geojson_feat['geometry'])
                            geojson_geom = make_valid(geojson_geom)  # Fix invalid geometry
                            
                            # Ensure the GeoJSON geometry is a valid Polygon or MultiPolygon
                            if not isinstance(geojson_geom, (Polygon, MultiPolygon)):
                                continue

                            if shape_geom.intersects(geojson_geom):
                                intersection = shape_geom.intersection(geojson_geom)
                                if intersection.is_empty:
                                    continue
                                
                                output.shape(intersection.__geo_interface__)
                                output.record(*[shape_rec.record[field] for field in field_names])
                                intersection_count += 1  # Increment the counter                                
                    except Exception as e:
                        print(f"Error processing shape record: {e}")
    except Exception as e:
        print(f"Error reading shapefile: {e}")

    # Create the .prj file
    prj_path = output_shapefile.replace('.shp', '.prj')
    with open(prj_path, 'w') as prj_file:
        prj_file.write(prj_content)
    print(f"Projection file saved at {prj_path}")
    
    # Print the number of features after intersection
    print(f"Number of features after intersection: {intersection_count}")
                        
# Function to calculate bounds of a MultiPolygon
def calculate_map_extent_bounds(multipolygon):
    envelope = multipolygon.GetEnvelope()  # Returns a tuple (minX, maxX, minY, maxY)
    return envelope

@app.route('/vectorize', methods=['POST'])
def vectorize():
    onlyIntersect = request.args.get('onlyIntersect')
    geojson_dict = request.json

    if geojson_dict['type'] != 'FeatureCollection':
        print("The provided GeoJSON data is not a FeatureCollection.")
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

    # Combine all feature bounds into a single bounding box for WMS request
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for feature in geojson_dict['features']:
        geometry_json = json.dumps(feature['geometry'])
        ogr_geom = ogr.CreateGeometryFromJson(geometry_json)
        
        if ogr_geom is None:
            print("Failed to create geometry from GeoJSON.")
            return jsonify({'message': 'Failed to create geometry from GeoJSON.'})
        
        bounds = calculate_map_extent_bounds(ogr_geom)
        print(f"Bounds: {bounds}")
        
        min_x, max_x = min(min_x, bounds[0]), max(max_x, bounds[1])
        min_y, max_y = min(min_y, bounds[2]), max(max_y, bounds[3])
    
    combined_bounds_STR = f"{min_y},{min_x},{max_y},{max_x}"
    print(f"Combined Bounds Str: {combined_bounds_STR}")
    WMS_params['BBOX'] = combined_bounds_STR
    encoded_params = urlencode(WMS_params, safe=',:')
    WMS_URL = base_URL + encoded_params
    print(f"WMS Source: {WMS_URL}")
    
    print(f"Current Working Directory: {os.getcwd()}")
    response = requests.get(WMS_URL)
    if response.status_code == 200:
        with open(downloaded_svg_from_cut_path, 'wb') as file:
            file.write(response.content)
    else:
        print(f"Failed to download image. Status code: {response.status_code}")
        return jsonify({'message': 'Failed to download image.', 'status_code': response.status_code})

    try:
        if onlyIntersect != 'true':
            # Parse the SVG with the bounding box and image size and write to shapefile
            polygons = parse_svg(downloaded_svg_from_cut_path, (1024, 1024), [min_x, min_y, max_x, max_y])
            print(f"Number of unique polygons: {len(polygons)}")
            write_polygons_to_shapefile(polygons, shp_from_svg_cut_path)

        # Perform intersection drectly with GeoJSON
        intersect_shapefile_with_geojson(shp_from_svg_cut_path, geojson_dict, save_intersected_geojson_shp_path)

        print(f"Intersection shapefile saved at {save_intersected_geojson_shp_path}")
        return jsonify({'message': 'SVG processing and intersection completed successfully.', 'output_path': save_intersected_geojson_shp_path})
    except Exception as e:
        print(f"Error during SVG processing: {str(e)}")
        return jsonify({'message': 'SVG processing failed.', 'error': str(e)})

if __name__ == '__main__':
    gdal.SetConfigOption('OGR_GEOMETRY_ACCEPT_UNCLOSED_RING', 'NO')
    app.run(debug=True)