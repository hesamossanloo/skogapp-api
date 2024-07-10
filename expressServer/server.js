import express from 'express';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
const port = 3001;

// Serve static files from the 'public' directory
app.use(express.static(join(__dirname, 'public')));

app.listen(port, () => {
  console.log(`SLD server listening at http://localhost:${port}`);
});