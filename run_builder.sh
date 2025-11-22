#!/bin/bash

# Build the Docker image
echo "Building Docker image..."
docker build -t android-kernel-builder .

# Create source directory if it doesn't exist
mkdir -p kernel_source

# Run the container
# We mount the current directory to /kernel/workspace to persist artifacts and source
echo "Starting Docker container..."
docker run -it --rm \
    -v /Volumes/android-kernel/kernel_source:/kernel/source \
    -v $(pwd)/scripts:/kernel/scripts \
    android-kernel-builder \
    /bin/bash
