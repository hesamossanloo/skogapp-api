FROM public.ecr.aws/lambda/python:3.11

# Install zip utility using yum
RUN yum update -y && yum install -y zip && yum clean all

# Install the necessary dependencies
RUN pip install pandas requests -t ${LAMBDA_TASK_ROOT}
# RUN pip install pandas fiona pyairtable -t ${LAMBDA_TASK_ROOT}

# Copy the Lambda function code into the container
COPY code/lambda_function.py ${LAMBDA_TASK_ROOT}
COPY code/Bio_growth.py ${LAMBDA_TASK_ROOT}
COPY code/Bonitetstabell_calculations-Furu_H40.csv ${LAMBDA_TASK_ROOT}
COPY code/Bonitetstabell_calculations-Gran_H40.csv ${LAMBDA_TASK_ROOT}

# Create a zip file of the function code and dependencies
RUN zip -r9 /tmp/package.zip .

# define the entrypoint for lambda
CMD [ "lambda_function.lambda_handler" ]