#!/bin/bash

# Ollama Chatbot Startup Script for Raspberry Pi 5

echo "Starting Ollama Chatbot Server..."

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production

# Check if Ollama is running
echo "Checking Ollama service..."
if ! pgrep -x "ollama" > /dev/null; then
    echo "Starting Ollama service..."
    ollama serve &
    sleep 5
fi

# Pull required models if they don't exist
echo "Checking for required models..."
models=("llama2" "mistral" "phi")
for model in "${models[@]}"; do
    if ! ollama list | grep -q "$model"; then
        echo "Pulling $model model..."
        ollama pull "$model"
    fi
done

# Start the Flask application with Gunicorn
echo "Starting Flask application with Gunicorn..."
gunicorn --config gunicorn.conf.py app:app

echo "Server started on http://0.0.0.0:8080"
