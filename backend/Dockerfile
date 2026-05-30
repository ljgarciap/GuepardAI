FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libreoffice-draw \
    libreoffice-impress \
    fontconfig \
    fonts-liberation \
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    fontforge \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium


# Copy application code
COPY . .

# Create persistent directories
RUN mkdir -p uploads data

# Expose port
EXPOSE 8000

# Start application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
