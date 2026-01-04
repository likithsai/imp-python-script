FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    patchelf \
    binutils \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy script
COPY src/ ./src/

# Install Python dependencies
# Add all packages your script needs here
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pyinstaller

# Build executable
RUN pyinstaller \
    --clean \
    --onefile \
    --name optimise_video \
    ./src/optimise_video.py

# Output only the binary
CMD ["cp", "/app/dist/optimise_video", "/output/optimise_video"]