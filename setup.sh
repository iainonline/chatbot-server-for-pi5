#!/bin/bash

# Ollama Chatbot Quick Setup Script
# This script sets up the chatbot application for first-time use

set -e

echo "🤖 Ollama Chatbot Setup Script"
echo "================================"

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: Please run this script from the Pi5-LLM directory"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt

# Initialize database
echo "🗄️ Initializing database..."
python -c "from app import app, db; app.app_context().push(); db.create_all(); print('Database initialized!')"

# Check if Ollama is installed
echo "🔍 Checking Ollama installation..."
if command -v ollama &> /dev/null; then
    echo "✅ Ollama is installed"
    
    # Check if Ollama service is running
    if pgrep -x "ollama" > /dev/null; then
        echo "✅ Ollama service is running"
    else
        echo "⚠️ Ollama service is not running. Starting it..."
        ollama serve &
        sleep 3
    fi
    
    # Check available models
    echo "📋 Available Ollama models:"
    ollama list
    
    # Suggest pulling basic models if none exist
    if [ $(ollama list | wc -l) -le 1 ]; then
        echo "📥 No models found. Would you like to pull some basic models?"
        echo "Recommended models: llama2, mistral, phi"
        echo "Run: ollama pull llama2"
        echo "Run: ollama pull mistral"
        echo "Run: ollama pull phi"
    fi
else
    echo "❌ Ollama is not installed. Please install it first:"
    echo "curl -fsSL https://ollama.ai/install.sh | sh"
    exit 1
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "🚀 To start the chatbot:"
echo "   Development mode: python app.py"
echo "   Production mode:  ./start_server.sh"
echo ""
echo "🌐 Access the chatbot at: http://localhost:8080"
echo "👤 Default admin login: admin / admin123"
echo "⚠️ Important: Change the admin password after first login!"
echo ""
echo "📚 For more information, see README.md"
