fetch('https://toblyuimg8.execute-api.eu-north-1.amazonaws.com/dev/wms')
  .then(response => response.json())
  .then(data => console.log(data))
  .catch((error) => {
    console.error('Error:', error);
  });