import shapefile
from osgeo import osr
import os
from flask import Flask, request, jsonify
import json
import xml.etree.ElementTree as ET
from osgeo import ogr, gdal, osr
from urllib.parse import urlencode
import requests
import re

def svg_to_shp(svg_path, shp_path, bbox, image_size):
    try:
        # Parse the SVG file
        tree = ET.parse(svg_path)
        root = tree.getroot()
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}

        # Create a new shapefile
        with shapefile.Writer(shp_path, shapefile.POLYGON) as shp:
            shp.field('ID', 'N')

            for element in root.findall('.//svg:path', namespaces):
                d = element.attrib.get('d', '')
                if d:
                    coordinates = parse_svg_path(d)
                    geo_coords = pixel_to_geo(coordinates, bbox, image_size)

                    # Define the polygon
                    polygon = [geo_coords]
                    shp.poly(polygon)
                    shp.record(1)

        # Create a projection file
        prj_content = """GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]"""
        with open(f"{shp_path.replace('.shp', '.prj')}", 'w') as prj:
            prj.write(prj_content)

        print(f"Shapefile created at {shp_path}")
    except Exception as e:
        print(f"Error converting SVG to SHP: {str(e)}")

new_svg_path = "outputs/extracted_features_V2.svg"
new_shp_path = "outputs/extracted_features_V2.shp"
svg_to_shp(new_svg_path, new_shp_path, [min_x, min_y, max_x, max_y], (1024, 1024))