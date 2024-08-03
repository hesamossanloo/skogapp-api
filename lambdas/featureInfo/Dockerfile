FROM public.ecr.aws/lambda/python:3.11

# Install zip utility using yum
RUN yum update -y && yum install -y zip && yum clean all

# Install the necessary dependencies
RUN pip install requests pyshp -t ${LAMBDA_TASK_ROOT}

# Copy the Lambda function code into the container
COPY code/lambda_function.py ${LAMBDA_TASK_ROOT}

# Create a zip file of the function code and dependencies
RUN zip -r9 /tmp/package.zip .

