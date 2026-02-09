FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Build Tailwind CSS (download binary, compile, remove binary)
RUN curl -sLo /tmp/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64 \
    && chmod +x /tmp/tailwindcss \
    && /tmp/tailwindcss -i static/css/input.css -o static/css/tailwind.css --minify \
    && rm /tmp/tailwindcss

# Create directories for persistent data, media, and static files
RUN mkdir -p /app/data /app/media /app/staticfiles

# Make entrypoint executable
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
