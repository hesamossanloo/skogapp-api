import os
from osgeo import ogr, osr
from shapely.geometry import Polygon, LinearRing
import xml.etree.ElementTree as ET

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

# Example usage
script_dir = os.path.dirname(os.path.abspath(__file__))
shp_file_name = 'output1.shp'
shp_file_path = os.path.join(script_dir, f"outputs/vectorize/{shp_file_name}")

svg_file_name = 'HOuJBvE84aPWtDJCym19nt1sUep1_HK_image_cut'
svg_path = os.path.join(script_dir, f"outputs/vectorize/{svg_file_name}.svg")

image_size = (1024, 1024)
# 59.91293019437413,11.67197776005428,59.93019418583705,11.692333790821172
# [min_x, min_y, max_x, max_y]
bbox = [11.684437282975667, 59.92796113169163, 11.749939392271136, 59.95933664178191]

# Parse the SVG with the bounding box and image size
polygons = parse_svg(svg_path, image_size, bbox)
print(f"Number of unique polygons: {len(polygons)}")
write_polygons_to_shapefile(polygons, shp_file_path)
print(f"Shapefile created at: {shp_file_path}")