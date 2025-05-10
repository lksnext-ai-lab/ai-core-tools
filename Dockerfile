# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

ENV DATABASE_NAME=""
ENV DATABASE_PORT=""
ENV DATABASE_USER=""
ENV DATABASE_PASSWORD=""
ENV DATABASE_HOST=""
ENV PYTHONPATH=/:/app:$PYTHONPATH

# Copy the current directory contents into the container at /app
COPY ./app /app

# Ensure the alembic directory is copied correctly
COPY ./alembic /alembic
COPY alembic.ini /alembic.ini

# Install system dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libmariadb-dev \
    libpq-dev \
    python3-dev \
    gcc \
    g++ \
    musl-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Instala primero las dependencias normales
RUN pip install --no-cache-dir -r ./requirements.txt
# Luego instala huggingface-hub sin dependencias
RUN pip install --no-cache-dir --no-deps huggingface-hub==0.27.1
RUN pip install -U flask-openapi3[swagger]
# Expose port 4321 to the outside world
EXPOSE 4321

CMD ["sh", "-c", "cd / && alembic upgrade head && cd /app && flask run --host=0.0.0.0 --port=4321"]