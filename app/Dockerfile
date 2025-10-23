# Use the official lightweight Python image.
FROM python:3.11-slim

# Set workdir
WORKDIR /app

# Install system deps (if you need any: e.g. libpq-dev, build-essential)
# RUN apt-get update && apt-get install -y --no-install-recommends ...

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY . .

# Expose the port your Flask app listens on
EXPOSE 5000

# Default command
CMD ["gunicorn", "run:create_app()", "--bind", "0.0.0.0:5000", "--workers", "2"]
