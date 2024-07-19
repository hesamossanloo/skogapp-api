# Use the AWS Lambda Python 3.12 base image
FROM public.ecr.aws/lambda/python:3.11

# Add a build argument to invalidate the cache
ARG CACHEBUST=1

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install the specified packages directly into the Lambda task root without using cache
RUN pip install --no-cache-dir --target ${LAMBDA_TASK_ROOT} -r requirements.txt

# Copy the rest of the application code
COPY app ${LAMBDA_TASK_ROOT}/app
COPY run.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "run.lambda_handler" ]