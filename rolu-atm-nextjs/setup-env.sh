#!/bin/bash
# RoluATM Environment Setup Script

echo "🎯 RoluATM Environment Setup"
echo "================================"

# Check if .env.local exists
if [ -f ".env.local" ]; then
    echo "⚠️ .env.local already exists. Backing up to .env.local.backup"
    cp .env.local .env.local.backup
fi

echo "📝 Creating .env.local file..."

# Generate a secure JWT secret
JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n')

# Create .env.local file
cat > .env.local << EOF
# World Network Configuration
APP_ID=app_263013ca6f702add37ad338fa43d4307
DEV_PORTAL_API_KEY=your_actual_world_id_developer_portal_api_key_here

# JWT Secret (auto-generated)
JWT_SECRET=${JWT_SECRET}

# Kiosk Configuration (update with your Raspberry Pi IP)
KIOSK_API_URL=http://192.168.1.100:5000

# Development/Production Mode
NODE_ENV=development
EOF

echo "✅ .env.local created successfully!"
echo ""
echo "🔐 IMPORTANT: You need to update these values:"
echo ""
echo "1. 📋 Get your World ID Developer Portal API Key:"
echo "   - Go to: https://developer.worldcoin.org/"
echo "   - Navigate to your app: app_263013ca6f702add37ad338fa43d4307"
echo "   - Go to 'API Keys' section"
echo "   - Copy your API key"
echo "   - Replace 'your_actual_world_id_developer_portal_api_key_here' in .env.local"
echo ""
echo "2. 🥧 Update Raspberry Pi IP address:"
echo "   - Find your Raspberry Pi's IP address"
echo "   - Replace '192.168.1.100' in KIOSK_API_URL with actual IP"
echo ""
echo "3. 🚀 For production deployment:"
echo "   - Change NODE_ENV to 'production'"
echo "   - Use production-grade secrets"
echo ""

# Check if required tools are installed
echo "🔍 Checking dependencies..."

if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js first."
    exit 1
fi

if ! command -v npm &> /dev/null; then
    echo "❌ npm not found. Please install npm first."
    exit 1
fi

echo "✅ Node.js and npm found"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

echo ""
echo "🎯 Next Steps:"
echo "1. Edit .env.local with your actual API key"
echo "2. Set up your Raspberry Pi kiosk (see raspberry-pi-kiosk/README.md)"
echo "3. Run the development server: npm run dev"
echo "4. Test the complete flow: World App → Withdraw → Kiosk → Cash"
echo ""
echo "📖 Full setup instructions: SETUP_INSTRUCTIONS.md" 