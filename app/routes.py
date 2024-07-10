import os
import time
import geopandas as gpd
from flask import Blueprint, request, jsonify

main = Blueprint('main', __name__)

gdb_path_akerhus = '/Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/Kartverket/Matrikkel_32_Akershus_25833.gdb'


def create_query(inputs):
    queries = []
    for input_str in inputs:
        # Split on the first '-' only
        parts = input_str.split('-', 1)
        if len(parts) == 2:
            kommunenummer, matrikkelnummertekst = parts
            query = f"(kommunenummer == '{kommunenummer}') & (matrikkelnummertekst == '{
                matrikkelnummertekst}')"
            queries.append(query)
        else:
            # Handle the case where the input does not conform to expected format
            print(f"Invalid input format: {input_str}")
    return " | ".join(queries)


@main.route('/filter', methods=['POST'])
def filter_features():
    data = request.get_json()
    inputs = data.get('inputs', [])
    layer_name = 'teig'

    query = create_query(inputs)

    # Read, Filter and Project Akerhus
    start_time_akerhus = time.time()
    gdf_akerhus = gpd.read_file(gdb_path_akerhus, layer=layer_name)
    filtered_gdf_akerhus = gdf_akerhus.query(query)
    if filtered_gdf_akerhus.crs != 'epsg:4326':
        filtered_gdf_akerhus = filtered_gdf_akerhus.to_crs('epsg:4326')

    output_geojson_path_akerhus = os.path.join(
        'outputs', 'output_4326_akerhus.geojson')
    filtered_gdf_akerhus.to_file(output_geojson_path_akerhus, driver='GeoJSON')

    end_time_akerhus = time.time()
    elapsed_time_akerhus = end_time_akerhus - start_time_akerhus

    # print the elapsed time for each query
    print(f"Elapsed time to prepare Akerhus: {elapsed_time_akerhus}")

    response = {
        'filtered_features_akerhus': filtered_gdf_akerhus.astype(str).to_json(),
        'output_file_akerhus': output_geojson_path_akerhus,
        'elapsed_time_to_prep_akerhus': elapsed_time_akerhus,
    }
    return jsonify(response)
