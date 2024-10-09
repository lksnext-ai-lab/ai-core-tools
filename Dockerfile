# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY ./app /app/app

# Ensure the alembic directory is copied correctly
COPY ./alembic /app/alembic
COPY alembic.ini /app/alembic.ini


# Install system dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

# Expose port 5000 to the outside world
EXPOSE 5000

ENV SQLALCHEMY_DATABASE_URI='postgresql://iacore:iacore@postgres:5432/iacore'

CMD ["sh", "-c", "alembic upgrade head && cd app && flask run --host=0.0.0.0"]
#CMD ["ls", "-la"]