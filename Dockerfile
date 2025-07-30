# 1. Base image
FROM python:3.11-slim

# 2. Set working directory
WORKDIR /app

# 3. Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy application code
COPY . .

# 5. Expose Flask port
EXPOSE 5000

# 6. Environment variables
ENV FLASK_APP=run.py
ENV FLASK_ENV=production

# 7. Launch the app
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "run:app"]
