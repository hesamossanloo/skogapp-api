import os
from flask import Flask, request, jsonify
import json
from osgeo import gdal, ogr
from urllib.parse import urlencode
import requests

app = Flask(__name__)

# Function to calculate bounds of a MultiPolygon
def calculate_bounds(multipolygon):
    envelope = multipolygon.GetEnvelope()  # Returns a tuple (minX, maxX, minY, maxY)
    return envelope

@app.route('/cut', methods=['POST'])
def cut():
    # Parse the GeoJSON from the request
    geojson_dict = request.json
    
    # Initialize variables for combined bounds
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    
    # Check if the GeoJSON data is a FeatureCollection
    if geojson_dict['type'] == 'FeatureCollection':
        for feature in geojson_dict['features']:
            # Extract the geometry part of the feature as a JSON string
            geometry_json = json.dumps(feature['geometry'])
            
            # Create an OGR geometry from the geometry JSON string
            ogr_geom = ogr.CreateGeometryFromJson(geometry_json)
            
            if ogr_geom is None:
                print("Failed to create geometry from GeoJSON.")
                return jsonify({'message': 'Failed to create geometry from GeoJSON.'})
            else:
                # Calculate bounds for the current feature
                bounds = calculate_bounds(ogr_geom)
                print("Bounds:", bounds)
                
                # Update combined bounds
                min_x, max_x = min(min_x, bounds[0]), max(max_x, bounds[1])
                min_y, max_y = min(min_y, bounds[2]), max(max_y, bounds[3])
                
        # Format combined_bounds as "min_y,min_x,max_y,max_x"
        combined_bounds_STR = f"{min_y},{min_x},{max_y},{max_x}"
        print("Combined Bounds Str:", combined_bounds_STR)
        
        # Use the combined bounds to cut the image
        # For example: cut_image(image_path, combined_bounds)
    else:
        print("The provided GeoJSON data is not a FeatureCollection.")
        return jsonify({'message': 'Invalid GeoJSON data. Must be a FeatureCollection.'})
            
    # Define the WMS URL and parameters
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
        "FORMAT": "image/png",
        "DPI": "144",
        "MAP_RESOLUTION": "144",
        "FORMAT_OPTIONS": "dpi:144",
        "TRANSPARENT": "TRUE"
    }
    # Update the WMS parameters to include the bounding box
    WMS_params['BBOX'] = combined_bounds_STR
    
    # Encode the URL parameters
    encoded_params = urlencode(WMS_params, safe=',:')
    
    
    # Combine the encoded parameters with the base URL
    # wms_source = f"{wms_url}&{'&'.join([f'{key}={value}' for key, value in encoded_params.items()])}"
    WMS_URL = base_URL + encoded_params
    print("WMS Source:", WMS_URL)
    
    # Specify the output path in a local directory
    downloaded_path = "outputs/downloaded_image.png"
    output_path = "outputs/cut_image.tif"

    response = requests.get(WMS_URL)
    if response.status_code == 200:
        with open(downloaded_path, 'wb') as file:
            file.write(response.content)
    else:
        print(f"Failed to download image. Status code: {response.status_code}")
        return jsonify({'message': 'Failed to download image.', 'status_code': response.status_code})
    gdal.UseExceptions()
    try:
        geojson_STR = json.dumps(geojson_dict)  # Convert dict to string to work with GDAL
        # Save the GeoJSON to a virtual file in memory
        geojson_vsimem_path = '/vsimem/temp_geojson.json'
        gdal.FileFromMemBuffer(geojson_vsimem_path, geojson_STR)
        
        # Define the output file path
        georeferenced_downloaded_path = "georeferenced_downloaded_image.tif"  # Change this to your desired output file path
        # Open the source image
        src_ds = gdal.Open(downloaded_path, gdal.GA_ReadOnly)
        
        # Parse the bounding box string
        min_y, min_x, max_y, max_x = map(float, combined_bounds_STR.split(','))
        # Get the size of the image
        src_width = src_ds.RasterXSize
        src_height = src_ds.RasterYSize
        # Calculate the resolution (assuming the image covers the entire bounding box)
        res_x = (max_x - min_x) / src_width
        res_y = (max_y - min_y) / src_height
        # Define the geotransform
        geotransform = (min_x, res_x, 0, max_y, 0, -res_y)
        
        # Set the geotransform and projection on the downloaded image
        dst_ds = gdal.GetDriverByName('GTiff').Create(georeferenced_downloaded_path, src_width, src_height, 3, gdal.GDT_Byte)
        dst_ds.SetGeoTransform(geotransform)
        dst_ds.SetProjection(src_ds.GetProjection())
        # Copy bands and set nodata value for each band
        nodata_value = 0
        for i in range(3):
            band = src_ds.GetRasterBand(i + 1).ReadAsArray()
            dst_band = dst_ds.GetRasterBand(i + 1)
            dst_band.WriteArray(band)
            dst_band.SetNoDataValue(nodata_value)

        # Close datasets to flush to disk
        src_ds = None
        dst_ds = None  

        # Use GDAL to fetch and cut the image from the WMS using the updated bounding box and the GeoJSON as a cutline
        result = gdal.Warp(output_path,  # Destination path for the warped output
                   srcDSOrSrcDSTab=georeferenced_downloaded_path,  # Source dataset path
                   format='GTiff',
                   dstNodata=nodata_value,
                   outputBounds=[min_x, min_y, max_x, max_y],
                   cutlineDSName=geojson_vsimem_path,  # GeoJSON cutline for cropping
                   cropToCutline=True,
                   dstSRS='EPSG:4326',  # Desired projection for the output
                   srcSRS='EPSG:4326')  # Source projection, if known and necessary to specify
        
        if not result:
            raise Exception("GDAL Warp operation failed.")
    
        # Cleanup the virtual file
        gdal.Unlink(geojson_vsimem_path)
        
        return jsonify({'message': 'Image processing completed successfully.', 'output_path': downloaded_path})
    except Exception as e:
        print("Error during image processing:", str(e))
        return jsonify({'message': 'Image processing failed.', 'error': str(e)})
        
if __name__ == '__main__':
    app.run(debug=True)