#!/bin/bash

# RoluATM Kiosk Systemd Services Installation Script
# This script installs and configures systemd services for the kiosk

set -e

echo "Installing RoluATM Kiosk systemd services..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "This script should not be run as root. Please run as the pi user with sudo."
   exit 1
fi

# Ensure we're in the right directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIOSK_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "Script directory: $SCRIPT_DIR"
echo "Kiosk directory: $KIOSK_DIR"
echo "Project root: $PROJECT_ROOT"

# Create necessary directories
echo "Creating directories..."
sudo mkdir -p /opt/roluatm
sudo mkdir -p /opt/roluatm/kiosk-pi/backend/logs
sudo chown -R pi:pi /opt/roluatm

# Copy project files if not already in /opt/roluatm
if [[ "$PROJECT_ROOT" != "/opt/roluatm" ]]; then
    echo "Copying project files to /opt/roluatm..."
    sudo cp -r "$PROJECT_ROOT"/* /opt/roluatm/
    sudo chown -R pi:pi /opt/roluatm
fi

# Install systemd service files
echo "Installing systemd service files..."
sudo cp "$SCRIPT_DIR/worldcash.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/kiosk-chromium.service" /etc/systemd/system/

# Set correct permissions
sudo chmod 644 /etc/systemd/system/worldcash.service
sudo chmod 644 /etc/systemd/system/kiosk-chromium.service

# Add pi user to dialout group for serial access
echo "Adding pi user to dialout group..."
sudo usermod -a -G dialout pi

# Create log directory
sudo mkdir -p /opt/roluatm/kiosk-pi/backend/logs
sudo chown pi:pi /opt/roluatm/kiosk-pi/backend/logs

# Check for environment file
if [[ ! -f "/opt/roluatm/kiosk-pi/.env" ]]; then
    echo "WARNING: Environment file not found at /opt/roluatm/kiosk-pi/.env"
    if [[ -f "/opt/roluatm/kiosk-pi/.env.example" ]]; then
        echo "Copying .env.example to .env - please edit with your configuration"
        cp "/opt/roluatm/kiosk-pi/.env.example" "/opt/roluatm/kiosk-pi/.env"
        chown pi:pi "/opt/roluatm/kiosk-pi/.env"
    fi
fi

# Setup Python virtual environment if it doesn't exist
if [[ ! -d "/opt/roluatm/kiosk-pi/backend/venv" ]]; then
    echo "Creating Python virtual environment..."
    cd /opt/roluatm/kiosk-pi/backend
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    chown -R pi:pi venv
fi

# Build frontend if package.json exists
if [[ -f "/opt/roluatm/kiosk-pi/frontend/package.json" ]]; then
    echo "Building frontend..."
    cd /opt/roluatm/kiosk-pi/frontend
    if command -v npm >/dev/null 2>&1; then
        npm install
        npm run build
        chown -R pi:pi node_modules dist
    else
        echo "WARNING: npm not found. Please install Node.js and build the frontend manually."
    fi
fi

# Setup nginx or simple HTTP server for frontend
echo "Configuring frontend server..."
if command -v nginx >/dev/null 2>&1; then
    # Configure nginx
    sudo tee /etc/nginx/sites-available/roluatm-kiosk > /dev/null <<EOF
server {
    listen 3000;
    listen [::]:3000;
    
    root /opt/roluatm/kiosk-pi/frontend/dist;
    index index.html;
    
    server_name localhost;
    
    location / {
        try_files \$uri \$uri/ /index.html;
    }
    
    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    
    sudo ln -sf /etc/nginx/sites-available/roluatm-kiosk /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    echo "Configured nginx to serve frontend on port 3000"
else
    echo "WARNING: nginx not found. Frontend will need to be served manually."
fi

# Reload systemd and enable services
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling services..."
sudo systemctl enable worldcash.service
sudo systemctl enable kiosk-chromium.service

# Test hardware connection
echo "Testing hardware connection..."
if [[ -e "/dev/ttyACM0" ]]; then
    echo "✓ T-Flex device found at /dev/ttyACM0"
    ls -la /dev/ttyACM0
else
    echo "⚠ T-Flex device not found at /dev/ttyACM0"
    echo "Please connect the Telequip T-Flex mechanism via USB"
fi

# Configure X11 for kiosk mode
echo "Configuring X11 for kiosk mode..."
if [[ -f "/home/pi/.xinitrc" ]]; then
    echo "Backing up existing .xinitrc"
    cp /home/pi/.xinitrc /home/pi/.xinitrc.backup
fi

# Create .xinitrc for kiosk mode
cat > /home/pi/.xinitrc << 'EOF'
#!/bin/sh
# RoluATM Kiosk X11 configuration

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Hide cursor after 1 second of inactivity
unclutter -idle 1 &

# Start window manager
exec openbox-session
EOF

chmod +x /home/pi/.xinitrc

# Configure autostart for X11
mkdir -p /home/pi/.config/openbox
cat > /home/pi/.config/openbox/autostart << 'EOF'
# RoluATM Kiosk Openbox autostart

# Disable screen blanking
xset s off &
xset -dpms &
xset s noblank &

# Hide cursor
unclutter -idle 1 &

# Start kiosk service (chromium will be started by systemd)
EOF

echo "Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit /opt/roluatm/kiosk-pi/.env with your configuration"
echo "2. Test the backend: sudo systemctl start worldcash.service"
echo "3. Check logs: sudo journalctl -u worldcash.service -f"
echo "4. Test the kiosk: sudo systemctl start kiosk-chromium.service"
echo "5. Enable automatic startup: systemctl enable worldcash.service kiosk-chromium.service"
echo ""
echo "Hardware requirements:"
echo "- Telequip T-Flex connected to /dev/ttyACM0"
echo "- Internet connection for cloud API"
echo "- 7\" touchscreen display"
echo ""
echo "To start services now:"
echo "  sudo systemctl start worldcash.service"
echo "  sudo systemctl start kiosk-chromium.service"
echo ""
echo "To check status:"
echo "  sudo systemctl status worldcash.service"
echo "  sudo systemctl status kiosk-chromium.service" 