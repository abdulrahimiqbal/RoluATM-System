#!/bin/bash
# RoluATM Raspberry Pi Kiosk Installation Script

echo "🥧 Installing RoluATM Kiosk System..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
sudo apt install -y python3-pip python3-venv python3-dev

# Install system dependencies for pygame and GPIO
echo "🔧 Installing system dependencies..."
sudo apt install -y \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libfreetype6-dev \
    libportmidi-dev \
    libjpeg-dev \
    python3-numpy \
    cython3

# Create virtual environment
echo "🌐 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python packages
echo "📚 Installing Python packages..."
pip install -r requirements.txt

# Create systemd service
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/rolu-kiosk.service > /dev/null <<EOF
[Unit]
Description=RoluATM Kiosk Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rolu-kiosk
Environment=PATH=/home/pi/rolu-kiosk/venv/bin
ExecStart=/home/pi/rolu-kiosk/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create environment file
echo "📝 Creating environment configuration..."
tee .env > /dev/null <<EOF
# Cloud API Configuration
CLOUD_API_URL=https://rolu-atm-nextjs-i8kebj4yf-rolu.vercel.app
KIOSK_ID=kiosk_001
KIOSK_PORT=5000

# Hardware Configuration
DISPENSER_RELAY_PIN=18
STATUS_LED_PIN=24
BUZZER_PIN=23

# Display Configuration
DISPLAY_WIDTH=800
DISPLAY_HEIGHT=480
EOF

# Set permissions
echo "🔐 Setting permissions..."
chmod +x main.py
sudo chown -R pi:pi /home/pi/rolu-kiosk

# Enable and start service
echo "🚀 Enabling kiosk service..."
sudo systemctl daemon-reload
sudo systemctl enable rolu-kiosk.service

# Configure GPIO permissions
echo "⚡ Configuring GPIO permissions..."
sudo usermod -a -G gpio pi

# Install additional tools
echo "🛠️ Installing additional tools..."
sudo apt install -y htop nano curl

echo "✅ Installation complete!"
echo ""
echo "📋 Next steps:"
echo "1. Reboot the Raspberry Pi: sudo reboot"
echo "2. Check service status: sudo systemctl status rolu-kiosk"
echo "3. View logs: sudo journalctl -u rolu-kiosk -f"
echo "4. Test kiosk: curl http://localhost:5000/health"
echo ""
echo "🔧 Hardware connections:"
echo "- Cash dispenser relay: GPIO 18"
echo "- Status LED: GPIO 24"
echo "- Buzzer: GPIO 23"
echo ""
echo "🌐 Kiosk will be available at: http://[PI_IP]:5000" 