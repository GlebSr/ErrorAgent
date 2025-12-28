#!/bin/bash

# ErrorAgent Quick Start Script

echo "🔍 ErrorAgent - Quick Start"
echo "=============================="
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate venv
echo ""
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "✓ Dependencies installed"

# Check for OpenAI API key
echo ""
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY not set"
    echo "   ErrorAgent will work with limited functionality."
    echo "   For full semantic search, set: export OPENAI_API_KEY=your-key"
else
    echo "✓ OPENAI_API_KEY is set"
fi

# Display next steps
echo ""
echo "=============================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Activate environment: source venv/bin/activate"
echo "  2. Run UI:              streamlit run src/ui/app_streamlit.py"
echo "  3. Or try example:      python example.py"
echo ""
echo "For more info, see README.md"
