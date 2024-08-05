import os
import geopandas as gpd
import pandas as pd
from flask import Blueprint, Flask, request, jsonify
import psycopg2

main = Blueprint('main', __name__)

# Load the vector layers
HK_SHP_path = gpd.read_file('/Users/hesam.ossanloo/Projects/Startup/SkogApp/skogapp-dashboard/skogapp-api/local-py-scripts/outputs/vectorize/intersected_image_w_info.shp')
SR16_intersect_GeoJSON_path = gpd.read_file('/Users/hesam.ossanloo/Downloads/Startup/SkogApp/Mads/QGIS/Data/SR16/Knut/SR16_intersect.geojson')

# Print columns to ensure correct names
print("HK_SHP Columns: ", HK_SHP_path.columns)
print("SR16_intersect_GeoJSON Columns: ", SR16_intersect_GeoJSON_path.columns)

# Ensure both layers are in the same CRS
HK_SHP_path = HK_SHP_path.to_crs(SR16_intersect_GeoJSON_path.crs)

# Perform the spatial join to calculate the overlap
joined = gpd.overlay(HK_SHP_path, SR16_intersect_GeoJSON_path, how='intersection')

# Print joined columns to check if 'teig_best_' is present The reason they are cut is that in shp file
# the column names are cut to 10 characters
print("Joined Layer Columns: ", joined.columns)

# Calculate the area of each intersection
joined['intersection_area'] = joined.area

# Calculate the percentage of overlap relative to the area of the polygons in the first layer
first_layer_areas = HK_SHP_path[['teig_best_', 'geometry']].copy()
first_layer_areas['first_layer_area'] = first_layer_areas.geometry.area

# Merge the first layer areas into the joined dataframe to calculate overlap percentages
joined = joined.merge(first_layer_areas[['teig_best_', 'first_layer_area']], on='teig_best_')
joined['overlap_percentage'] = (joined['intersection_area'] / joined['first_layer_area']) * 100

# List of attributes to be averaged
attributes = ['srvolmb', 'srvolub', 'srbmo', 'srbmu', 'srhoydem', 'srdiam', 'srdiam_ge8', 
              'srgrflate', 'srhoydeo', 'srtrean', 'srtrean_ge8', 'srtrean_ge10', 
              'srtrean_ge16', 'srlai', 'srkronedek']

# Calculate weighted averages
for attr in attributes:
    joined[attr] = joined[attr] * joined['overlap_percentage']

# Group by teig_best_ to aggregate the required values
grouped = joined.groupby('teig_best_').agg(
    {**{attr: 'sum' for attr in attributes}, 'overlap_percentage': 'sum'}
).reset_index()

# Normalize the attributes by the overlap percentage sum to get the average values
for attr in attributes:
    grouped[attr] = grouped[attr] / grouped['overlap_percentage']

# Function to get prod_lokalid with overlap percentage
def get_prod_lokalid_overlap(df):
    return ', '.join(f"({row['prod_lokalid']} & {row['overlap_percentage']:.2f}%)" for idx, row in df.iterrows())

# Add the prod_lokalid with the overlap percentage
prod_lokalid_overlap = joined.groupby('teig_best_').apply(get_prod_lokalid_overlap).reset_index()
prod_lokalid_overlap.columns = ['teig_best_', 'prod_lokalid_overlap']

# Merge the aggregated data with prod_lokalid_overlap
final_df = pd.merge(grouped, prod_lokalid_overlap, on='teig_best_')

# Drop the overlap_percentage column as it's no longer needed
final_df = final_df.drop(columns=['overlap_percentage'])

# Rename the column teig_best_ to bestand_id
final_df = final_df.rename(columns={'teig_best_': 'bestand_id'})

# Save the result to a CSV file
final_df.to_csv('SR16-HK-intersection.csv', index=False)

print("CSV file with merged attributes has been created successfully.")
