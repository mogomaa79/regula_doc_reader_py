#!/bin/bash

# Setup script for Regula Document Reader Project
echo "Setting up Regula Document Reader environment..."

# Create conda environment if it doesn't exist
conda create -n regula_doc_reader python=3.13 -y

# Activate environment
conda activate regula_doc_reader

# Install required packages
/opt/anaconda3/envs/regula_doc_reader/bin/pip install regula-documentreader-webclient

echo "✅ Environment setup complete!"
echo ""
echo "To use this environment:"
echo "1. conda activate regula_doc_reader"
echo "2. python main.py <path_to_image_file>"
echo ""
echo "Note: Make sure the Regula DocumentReader API server is running on localhost:8080"
