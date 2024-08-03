# The GDAL challange 
was solved by following this:
https://github.com/lambgeo/docker-lambda

# STEP 1: Build Lambdas
You Lambda shoul have this structure:
`lambdas/filter/code/`:

`lambda_function.py`,
`template.yml`

Create an S3 bucket for you lambda packages
Go into the `code` folder
and run this command:
```
sam build
```
After that `.aws-sam` folder is created under `code`. Check if you have al lthe necessary libs and py files.

# STEP 2: Package Lambdas
After a successfull build. You should use the name of the S3 bucket you created earlier and create a package for your lambda, by running this:
```
sam package --output-template-file packaged.yaml --s3-bucket skogapp-sam-lambda-deployments
```
Wait for the successful packaging.
You will now notice a new file called `packaged.yaml` under `code` fodler.

# STEP 3: Deploy Lambdas
Now that you have the package run this command to deploy th elambda:
```
sam deploy --template-file packaged.yaml --stack-name SkogAppStack --capabilities CAPABILITY_IAM
```

Remember all these commands should be run while you are in the `code` folder. Unless the `sam` command won't find the `template.yml` file.

# Test Lambdas
you can define a json test file somewhere and invoke your lambda like this:
```
sam local invoke SkogAppTeigFilter -e tests/lambda/events/local_test_event.json
```


docker build --platform linux/amd64 --tag skogapp-featureinfo:latest .
docker build --platform linux/amd64 --tag skogapp-vectorize:latest .
docker build --platform linux/amd64 --tag skogapp-cut:latest .
docker run --platform linux/amd64 --name lambda skogapp-featureinfo:latest
docker run --name lambda -w /var/task --volume $(pwd):/local -itd skogapp-vectorize:latest bash
docker run --name lambda -w /var/task --volume $(pwd):/local -itd skogapp-cut:latest bash
docker exec -it lambda bash
python -c "import numpy; print(numpy.__version__)"
python -c "from osgeo import gdal; print(gdal.__version__)"
python -c "import xml.etree.ElementTree as ET"
python -c "from urllib.parse import urlencode"
python -c "import shapefile; import re; from shapely.geometry import shape, mapping"
python -c "import shapefile; import requests"
python /var/task/lambda_function.py event.json
docker cp lambda:/tmp/package.zip SkogAppHKFeatureInfo-V1.zip
docker cp lambda:/tmp/package.zip SkogAppHKCut-V1.zip
docker cp lambda:/tmp/package.zip SkogAppHKVectorize-V6.zip
docker stop lambda
docker rm lambda