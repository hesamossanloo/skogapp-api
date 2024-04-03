import dotenv from 'dotenv';
import fetch from 'node-fetch';
dotenv.config();

// Replace with your WMS server URL and credentials
const MYAUTHTOKEN = process.env.GEODATA_BASIC_AUTH;
const WMS_SERVER_URL_HARDCODE = 'https://services.geodataonline.no:443/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&BBOX=59.92689139667997011%2C11.6875331258577333%2C59.95852442175434049%2C11.74712906591031469&CRS=EPSG%3A4326&WIDTH=4000&HEIGHT=4000&LAYERS=0&STYLES=&FORMAT=image%2Fjpeg&DPI=72&MAP_RESOLUTION=72&FORMAT_OPTIONS=dpi%3A72'

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
const controller = new AbortController();
const timeout = setTimeout(() => {
  controller.abort();
}, 10000); // timeout after 10 seconds
const handler = async (event) => {
    try {
        const response = await fetch(WMS_SERVER_URL_HARDCODE, { headers, signal: controller.signal });
        // clear the timeout if the request completes successfully
        clearTimeout(timeout);
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
