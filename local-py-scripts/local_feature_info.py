import os
import shapefile
from flask import Flask, jsonify
import requests
import xml.etree.ElementTree as ET
from shapely.geometry import shape
from shapely.validation import make_valid
from shapely.ops import transform
import pyproj

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Define paths relative to the script's directory
intersected_geojson_shp_path = os.path.join(script_dir, "outputs/vectorize/intersected_image.shp")
intersected_geojson_prj_path = os.path.join(script_dir, "outputs/vectorize/intersected_image.prj")
intersected_geojson_shp_w_info_path = os.path.join(script_dir, "outputs/vectorize/intersected_image_w_info.shp")
intersected_geojson_prj_w_info_path = os.path.join(script_dir, "outputs/vectorize/intersected_image_w_info.prj")

app = Flask(__name__)

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

@app.route('/featureInfo', methods=['POST'])
def featureInfo():
    try:
        # Read the shapefile
        sf = shapefile.Reader(intersected_geojson_shp_path)
        writer = shapefile.Writer(intersected_geojson_shp_w_info_path)
        
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
        
        # Read the content of the original .prj file
        with open(intersected_geojson_prj_path, 'r') as prj_file:
            prj_content = prj_file.read()

        # Write the content to the new .prj file at local_out_prj_path
        with open(intersected_geojson_prj_w_info_path, 'w') as out_prj_file:
            out_prj_file.write(prj_content)

        return jsonify({'message': 'Feature info request successful and shapefile updated.'})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'message': 'Feature info request failed.'})

if __name__ == '__main__':
    app.run(debug=True)