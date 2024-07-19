# How to build and deploy the Lambda manually
Becuase of the different OS and CPU architecture of MacOS and AWS Linux for lambdas. The binares of the 
python libraries are treated differently and as a result Lambda environment doesn't recognise the imports.
Ergo we need to create some of the important dependencies as a Layer and some inside the Zip file

This means our main business logic stays within the /app/routes.py
The Lambda handler is defined inside the run.py

If we need more layers we define them inside the /lambda-layers and zip them from there

Here are the steps I took to create the zip file and the lambda along with some useful commands.

## STEP 1
I manually create a Lambda called test2 on aws following this article:
https://medium.com/@jenniferjasperse/how-to-use-postgres-with-aws-lambda-and-python-44e9d9154513
There I used the Lambda ENV VARS to define the DB credentials. Because using secrets didn't work.

When creating the Lambda test2 via the AWS Console. I just used the default VPS and chose the 3 subnets. And gave the Lambda the 
Basic execution role and the EC2 role. The IAM role is called test2-role-0ptzz2fc, Use this as a template to create similar roles and policies for the for new lambdas. Be careful in the roles and policies of the test2, the name opf the lambda is 
specifically written inthe policy. Make sure to change it so it reflects the name of the new lambda. Unless the CloudWatchLogs won't be created.

## STEP 2
I am not sure if this step was necessary but I did it anyways. I manually connected the RDS from within the Lambda and from the RDS page. Check them both and connect them to the corresponding Lambdas.

## STEP 3
### Build the Docker Image
docker build --platform linux/amd64 --build-arg CACHEBUST=$(date +%s) -t skogappteigfilter-image:test .

## STEP 4
### Create the Deployment Package
container_id=$(docker create skogappteigfilter-image:test)
docker cp $container_id:/var/task ./skogappteigfilter-lambda-package
docker rm $container_id
cd skogappteigfilter-lambda-package
zip -r9 ../zips/skogappteigfilter-lambda-package.zip .
cd ..

## STEP 5
### Update the Lambda Function Code
aws lambda update-function-code --function-name SkogAppTeigFilter --zip-file fileb://zips/skogappteigfilter-lambda-package.zip

## STEP 6
add the relevant layers to your lambda. In this case I added the shapely and psycopg2

## STEP 7
manually add the API Gateway as trigger.
Make it a REST API and not an HTTP API
.Make sure to have the API Proxy option enables and the next option chose the first one that says (recommended)

Also make sure that your endpoint is connected to the desired Lambda.