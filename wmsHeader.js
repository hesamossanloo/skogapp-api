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
const WMS_SERVER_URL = 'https://services.geodataonline.no:443/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer'
const WMS_SERVER_URL_HARDCODE = 'https://services.geodataonline.no:443/arcgis/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer/WMSServer?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&BBOX=59.92689139667997011%2C11.6875331258577333%2C59.95852442175434049%2C11.74712906591031469&CRS=EPSG%3A4326&WIDTH=4000&HEIGHT=4000&LAYERS=0&STYLES=&FORMAT=image%2Fjpeg&DPI=72&MAP_RESOLUTION=72&FORMAT_OPTIONS=dpi%3A72'

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
    let { bbox, crs, ...otherParams } = req.query;
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
        res.setHeader('Content-Type', response.headers.get('Content-Type'));
        res.send(data);
    } catch (error) {
        console.error('Error in proxy:', error.message);
        res.status(500).send(`Error in proxy server: ${error.message}`);
    }
});
app.use('/test', async (req, res) => {
    try {
        const response = await fetch(WMS_SERVER_URL_HARDCODE, { headers });

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
