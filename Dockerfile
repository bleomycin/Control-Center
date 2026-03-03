FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Build Tailwind CSS (download binary, compile, remove binary)
# python:3.12-slim has neither curl nor wget, so use Python to download
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64', '/tmp/tailwindcss')" \
    && chmod +x /tmp/tailwindcss \
    && /tmp/tailwindcss -i static/css/input.css -o static/css/tailwind.css --minify \
    && rm /tmp/tailwindcss

# Create directories for persistent data, media, and static files
RUN mkdir -p /app/data /app/media /app/staticfiles

# Make entrypoint executable
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
