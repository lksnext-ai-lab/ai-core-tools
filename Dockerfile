# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

ENV DATABASE_NAME=""
ENV DATABASE_PORT=""
ENV DATABASE_USER=""
ENV DATABASE_PASSWORD=""

# Copy the current directory contents into the container at /app
COPY ./app /app/app
COPY .env /app/.env
# Ensure the alembic directory is copied correctly
COPY ./alembic /app/alembic
COPY alembic.ini /app/alembic.ini


# Install system dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libmariadb-dev \
    libpq-dev \
    python3-dev \
    gcc \
    python3-dev \
    musl-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

# Expose port 4321 to the outside world
EXPOSE 4321

CMD ["sh", "-c", "alembic upgrade head && cd app && flask run --host=0.0.0.0 --port=4321"]