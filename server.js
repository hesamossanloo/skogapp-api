const express = require('express');
const axios = require('axios');
const proj4 = require('proj4');
const app = express();
const port = 3001;

// Define the source and destination projections
// EPSG:3857 (Web Mercator) and EPSG:4326 (WGS 84) are predefined in proj4
const sourceProjection = 'EPSG:3857';
const destinationProjection = 'EPSG:4326';

app.get('/wms-test', async (req, res) => {
  // Extract the BBOX parameter from the query string
  let { BBOX, ...otherParams } = req.query;

  // Reproject the BBOX if it's present
  if (BBOX) {
    const bboxValues = BBOX.split(',').map(value => parseFloat(value));
    const [minX, minY, maxX, maxY] = bboxValues;

    // Reproject the min and max points of the BBOX
    const [reprojectedMinX, reprojectedMinY] = proj4(sourceProjection, destinationProjection, [minX, minY]);
    const [reprojectedMaxX, reprojectedMaxY] = proj4(sourceProjection, destinationProjection, [maxX, maxY]);

    // Replace the BBOX parameter with the reprojected values
    BBOX = [reprojectedMinX, reprojectedMinY, reprojectedMaxX, reprojectedMaxY].join(',');
  }

  // Reconstruct the query string with the reprojected BBOX and other parameters
  const queryString = new URLSearchParams({ BBOX, ...otherParams }).toString();
  const wmsUrl = `https://services.geodataonline.no/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer?${queryString}`;

  try {
    const response = await axios.get(wmsUrl, {
      responseType: 'arraybuffer',
    });

    // Forward the response headers and body to the client
    res.set('Content-Type', response.headers['content-type']);
    res.send(response.data);
  } catch (error) {
    console.error('Failed to proxy WMS request:', error);
    res.status(500).send('Failed to load data');
  }
});

app.listen(port, () => {
  console.log(`Proxy server listening at http://localhost:${port}`);
});