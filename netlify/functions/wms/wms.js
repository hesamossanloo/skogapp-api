import dotenv from 'dotenv';
import fetch from 'node-fetch';
import proj4 from 'proj4';
dotenv.config();

// Replace with your WMS server URL and credentials
const MYAUTHTOKEN = process.env.GEODATA_BASIC_AUTH;
const WMS_SERVER_URL = 'https://services.geodataonline.no:443/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer'

// Basic Auth Header
const headers = {
  'Authorization': `Basic ${MYAUTHTOKEN}`
};
// CORS Configuration
const corsResponseHeader = {
    'Access-Control-Allow-Origin': '*', // Allow all domains
    // Add other CORS headers as needed
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Credentials': 'true', // If your client needs to send cookies
}

const handler = async (event) => {
    const { queryStringParameters } = event;
    let { bbox, crs, ...otherParams } = queryStringParameters;
    crs = 'EPSG:4326'
    if (bbox) {
        // Split the BBOX string into individual numbers and parse them as floats
        const bboxValues = bbox.split(',').map(value => parseFloat(value));
        
        // Assuming bboxValues are in the order [minX, minY, maxX, maxY] for the source CRS
        const [minX, minY, maxX, maxY] = bboxValues;

        // Transform the coordinates to EPSG:4326
        // Note: proj4js uses the order [longitude, latitude] for EPSG:4326
        const bottomLeft = proj4('EPSG:3857', 'EPSG:4326', [minX, minY]);
        const topRight = proj4('EPSG:3857', 'EPSG:4326', [maxX, maxY]);

        // Construct the BBOX in the correct order for EPSG:4326: lat_min, lon_min, lat_max, lon_max
        bbox = `${bottomLeft[1]},${bottomLeft[0]},${topRight[1]},${topRight[0]}`;
    }

    const queryString = new URLSearchParams({ bbox, crs, ...otherParams }).toString();
    try {
        const url = `${WMS_SERVER_URL}?${queryString}`
        const response = await fetch(url, { headers });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.buffer();
        return {
            statusCode: 200,
            headers: {
              'Content-Type': response.headers.get('Content-Type'),
              ...corsResponseHeader
            },
            body: data.toString('base64'),
            isBase64Encoded: true,
          };
    } catch (error) {
        console.error('Error in proxy:', error.message);
        return {
            statusCode: 500,
            headers: { 'Content-Type': 'image/jpeg', ...corsResponseHeader }, // Adjust the Content-Type as necessary
            body: `Error in proxy server: ${error.message}`,
        };
    }
};

export { handler };
