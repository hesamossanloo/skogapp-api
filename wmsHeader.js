import cors from 'cors';
import dotenv from 'dotenv';
import express from 'express';
import fetch from 'node-fetch';
import proj4 from 'proj4';
dotenv.config();

const app = express();
const PORT = process.env.PORT || 5001;

// Replace with your WMS server URL and credentials
const MYAUTHTOKEN = process.env.EXPRESS_APP_GEODATA_BASIC_AUTH;
const WMS_SERVER_URL = 'https://services.geodataonline.no/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer'
// const WMS_SERVER_URL_GET_CAPABILITIES = 'https://services.geodataonline.no/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer'
// const WMS_SERVER_URL_WITH_PARAMS = 'https://services.geodataonline.no:443/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&BBOX=11.68743995561395188%2C59.92689139667997011%2C11.7470358956665315%2C59.95852442175434049&CRS=CRS%3A84&WIDTH=2265&HEIGHT=1202&LAYERS=0&STYLES=&FORMAT=image%2Fjpeg&DPI=72&MAP_RESOLUTION=72&FORMAT_OPTIONS=dpi%3A72'

// Define the source and destination projections
// EPSG:3857 (Web Mercator) and EPSG:4326 (WGS 84) are predefined in proj4
const sourceProjection = 'EPSG:3857';
const destinationProjection = 'EPSG:4326';

// Basic Auth Header
const headers = {
  'Authorization': `Basic ${MYAUTHTOKEN}`
};
// CORS Configuration
const corsOptions = {
    // Configure based on your security requirements
    origin: '*', // This allows all origins. For production, specify your domain(s)
    optionsSuccessStatus: 200 // For legacy browser support
};

app.use(cors(corsOptions));
app.use('/wms', async (req, res) => {
    try {
        let { bbox, ...otherParams } = req.query;
        // Extract the BBOX parameter from the query string
        // Reproject the BBOX if it's present
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
        // BBOX: 59.92689139667997011%2C11.68743995561395188%2C59.95852442175434049%2C11.7470358956665315
        // Reconstruct the query string with the reprojected BBOX and other parameters
        const uppercaseParams = Object.fromEntries(
            Object.entries({ bbox, ...otherParams }).map(([key, value]) => [key.toUpperCase(), value])
        );
        const queryString = new URLSearchParams(uppercaseParams).toString();
        const fullUrl = `${WMS_SERVER_URL}?${queryString}`;
        const response = await fetch(fullUrl, { headers });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.buffer();
        res.setHeader('Content-Type', response.headers.get('Content-Type'));
        res.send(data);
    } catch (error) {
        console.error('Error in proxy:', error.message);
        res.status(500).send(`Error in proxy server: ${error.message}`);
    }
});

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});
