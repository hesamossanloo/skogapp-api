min_x, min_y, max_x, max_y = map_extent_bbox
width = 1024  # Replace with actual width from WMS_params
height = 1024  # Replace with actual height from WMS_params

try:
    with shapefile.Reader(shapefile_path) as shapefile_src:
        fields = shapefile_src.fields[1:]  # Skip the DeletionFlag field
        field_names = [field[0] for field in fields]

        with shapefile.Writer(output_shapefile) as output:
            output.fields = fields
            for attr_name in ['leveranseid', 'prosjekt', 'kommune', 'hogstkl_verdi', 'bonitet_beskrivelse', 'bontre_beskrivelse', 'areal', 'arealm2', 'alder', 'alder_korr', 'regaar_korr', 'regdato', 'sl_sdeid', 'teig_best_nr']:
                output.field(attr_name, 'C')

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
                            # print(f"Skipping invalid GeoJSON geometry: {geojson_geom}")
                            continue

                        if shape_geom.intersects(geojson_geom):
                            intersection = shape_geom.intersection(geojson_geom)
                            if intersection.is_empty:
                                continue
                            
                            # Calculate the centroid of the intersection
                            centroid = intersection.centroid
                            pixel_x, pixel_y = calculate_pixel_coordinates(map_extent_bbox, width, height, centroid)
                            
                            # Fetch WMS info for the intersected polygon
                            wms_params = {
                                'SERVICE': 'WMS',
                                'VERSION': '1.3.0',
                                'REQUEST': 'GetFeatureInfo',
                                'LAYERS': 'hogstklasser',
                                'QUERY_LAYERS': 'hogstklasser',
                                'BBOX': f"{min_y},{min_x},{max_y},{max_x}",
                                'WIDTH': width,
                                'HEIGHT': height,
                                'INFO_FORMAT': 'application/vnd.ogc.gml',
                                'I': pixel_x,
                                'J': pixel_y,
                                'CRS': 'EPSG:4326'
                            }
                            wms_info = fetch_wms_info(wms_url, wms_params)
                            wms_attributes = parse_gml(wms_info)
                            
                            # Write the intersected part to the output shapefile
                            record = shape_rec.record.as_dict()
                            record['featureInfos'] = wms_attributes
                            record['featureInfos']['bestand_id'] = shape_rec.record['bestand_id']
                            output.record(**record)
                            output.shape(intersection.__geo_interface__)