import fetch from 'node-fetch';
import proj4 from 'proj4';
const MYAUTHTOKEN = process.env.GEODATA_BASIC_AUTH;
// const WMS_SERVER_URL_HARDCODE = 'https://services.geodataonline.no:443/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&BBOX=59.93480248245968056%2C11.70243211087088042%2C59.95061899469754962%2C11.73223008089716934&CRS=EPSG%3A4326&WIDTH=2261&HEIGHT=1200&LAYERS=0&STYLES=&FORMAT=image%2Fjpeg&DPI=72&MAP_RESOLUTION=72&FORMAT_OPTIONS=dpi%3A72'
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
}
export const lambdaHandler = async (event, context) => {
    try {
        const { queryStringParameters } = event;
        let { bbox, BBOX, crs, CRS, ...otherParams } = queryStringParameters;
        bbox = bbox || BBOX;
        crs = crs || CRS;
        console.log('queryStringParameters: ',queryStringParameters);
        console.log('BBOX Before: ', bbox);
        console.log('CRS Before: ',crs);
        if (!queryStringParameters || !bbox || !crs) {
            return {
                statusCode: 400,
                headers: { 'Content-Type': 'text/plain', ...corsResponseHeader },
                body: 'Missing required parameters: bbox and/or crs',
            };
        }
        if (bbox && (crs !== 'EPSG:4326' && crs!=="EPSG%3A4326")) {
            crs = 'EPSG:4326';
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
        console.log('CRS After: ',crs);
        console.log('BBOX After: ', bbox);
        const queryString = new URLSearchParams({ bbox, crs, ...otherParams }).toString();
        
        const url = `${WMS_SERVER_URL}?${queryString}`
        console.log('URL:', url);
        const response = await fetch(url, { headers });
        
        // clear the timeout if the request completes successfully
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const arrayBuffer = await response.arrayBuffer();
        const data = Buffer.from(arrayBuffer).toString('base64');

        return {
            statusCode: 200,
            headers: {
                'Content-Type': response.headers.get('Content-Type'),
                ...corsResponseHeader
            },
            body: data,
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