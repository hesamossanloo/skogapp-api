FROM ghcr.io/lambgeo/lambda-gdal:3.8-python3.11

ENV PACKAGE_PREFIX=/var/task
ENV GDAL_DATA=/var/task/share/gdal
ENV PROJ_LIB=/var/task/share/proj

# Install zip utility using yum
RUN yum update -y && yum install -y zip && yum clean all

# Copy any local files to the package
COPY code/lambda_function.py ${PACKAGE_PREFIX}/lambda_function.py

# Install necessary requirements to `/var/task`
RUN pip install gdal==3.8.3 pyshp -t ${PACKAGE_PREFIX}/

# Reduce size of the C libs
RUN cd $PREFIX && find lib -name \*.so\* -exec strip {} \;

# Create package.zip
# Archive python code (installed in $PACKAGE_PREFIX/)
RUN cd $PACKAGE_PREFIX && zip -r9q /tmp/package.zip * -x "*/__pycache__/*"

# Archive GDAL libs (in $PREFIX/lib $PREFIX/bin $PREFIX/share)
RUN cd $PREFIX && zip -r9q --symlinks /tmp/package.zip lib/*.so* share
RUN cd $PREFIX && zip -r9q --symlinks /tmp/package.zip bin/gdal* bin/ogr* bin/geos* bin/nearblack

# Set the environment variables for GDAL and PROJ
ENV PATH="${PREFIX}/bin:${PATH}"
ENV LD_LIBRARY_PATH="${PREFIX}/lib:${LD_LIBRARY_PATH}"