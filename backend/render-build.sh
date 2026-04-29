#!/usr/bin/env bash

# 1. Exit immediately if any command fails
set -o errexit

# 2. Update package lists
echo "Updating package lists..."
apt-get update

# 3. Install FFmpeg
# This is mandatory for pydub to handle non-WAV formats (MP3, OGG, WebM, etc.)
echo "Installing ffmpeg..."
apt-get install -y ffmpeg

# 4. (Optional) Verify installation
echo "Checking ffmpeg version..."
ffmpeg -version

echo "Build script completed successfully."
