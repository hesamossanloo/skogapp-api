import os
from osgeo import gdal, ogr, osr
import numpy as np
import cv2

def preprocess_raster(raster_path, processed_path):
    # Open the raster file using GDAL
    src_ds = gdal.Open(raster_path)
    if src_ds is None:
        raise FileNotFoundError(f"Could not open {raster_path}")

    # Read the raster data into a NumPy array (assume 3 bands for RGB)
    raster = np.dstack([src_ds.GetRasterBand(i + 1).ReadAsArray() for i in range(3)])

    # Convert the raster from BGR to RGB
    raster_rgb = cv2.cvtColor(raster, cv2.COLOR_BGR2RGB)

    # Define the grey color range in RGB format
    lower_grey_rgb = np.array([85, 85, 85])  # Approx lower bound for grey
    upper_grey_rgb = np.array([113, 109, 111])  # Approx upper bound for grey

    # Create a binary mask where grey colors become white (255) and all others become black (0)
    mask = cv2.inRange(raster_rgb, lower_grey_rgb, upper_grey_rgb)

    # Thin the grey borders to a single-pixel width
    thin = cv2.ximgproc.thinning(mask, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)

    # Invert colors for polygonization
    inverted = cv2.bitwise_not(thin)

    # Save the processed image as a TIF file using GDAL
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(processed_path, src_ds.RasterXSize, src_ds.RasterYSize, 1, gdal.GDT_Byte)
    out_ds.GetRasterBand(1).WriteArray(inverted)
    out_ds.SetGeoTransform(src_ds.GetGeoTransform())
    out_ds.SetProjection(src_ds.GetProjection())
    out_ds.FlushCache()
    out_ds = None
    src_ds = None

def raster_to_vector(raster_path, vector_path):
    # Open the raster file
    src_ds = gdal.Open(raster_path)
    if src_ds is None:
        raise FileNotFoundError(f"Could not open {raster_path}")

    # Get the raster band
    src_band = src_ds.GetRasterBand(1)

    # Create output shapefile
    driver = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(vector_path):
        driver.DeleteDataSource(vector_path)
    out_ds = driver.CreateDataSource(vector_path)
    srs = osr.SpatialReference()
    srs.ImportFromWkt(src_ds.GetProjectionRef())
    out_layer = out_ds.CreateLayer("polygonized", srs=srs, geom_type=ogr.wkbPolygon)

    # Add a new field
    new_field = ogr.FieldDefn('DN', ogr.OFTInteger)
    out_layer.CreateField(new_field)

    # Polygonize
    gdal.Polygonize(src_band, src_band, out_layer, 0, [], callback=None)

    # Close datasets
    out_ds = None
    src_ds = None

    print(f"Vector file saved at {vector_path}")

# Example usage
preprocess_raster('outputs/cut_image.tif', 'outputs/processed_image.tif')
raster_to_vector('outputs/processed_image.tif', 'outputs/output_vector.shp')