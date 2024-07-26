import os
from flask import Flask, jsonify
from osgeo import gdal, ogr, osr

app = Flask(__name__)

@app.route('/vectorize', methods=['GET'])
def vectorize():
    # Define the geo referenced output file path
    cut_image_put = "output_image.png"

    try:
        # Open the raster file
        raster_ds = gdal.Open(cut_image_put, gdal.GA_ReadOnly)
        # Get the first band (assuming the polygons are defined in the first band)
        band = raster_ds.GetRasterBand(1)
        
        # Create an output shapefile
        driver = ogr.GetDriverByName('ESRI Shapefile')
        out_shapefile = 'vectorized_polygons.shp'
        if os.path.exists(out_shapefile):
            driver.DeleteDataSource(out_shapefile)
        out_ds = driver.CreateDataSource(out_shapefile)

        # Create the spatial reference, WGS84
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)  # Adjust the EPSG code to match your raster's projection

        # Create the layer
        out_layer = out_ds.CreateLayer('polygons', srs, geom_type=ogr.wkbPolygon)

        # Add an ID field
        field_defn = ogr.FieldDefn('ID', ogr.OFTInteger)
        out_layer.CreateField(field_defn)

        # Use gdal.Polygonize to vectorize the polygons
        gdal.Polygonize(band, None, out_layer, 0, [], callback=None)

        # Close the datasets
        raster_ds = None
        out_ds = None

        print("Vectorization complete. Output saved to:", out_shapefile)
        return jsonify({'message': 'Vectorization complete.', 'output_path': out_shapefile})
    except Exception as e:
        print("Error during image processing:", str(e))
        return jsonify({'message': 'Image processing failed.', 'error': str(e)})
if __name__ == '__main__':
    app.run(debug=True)