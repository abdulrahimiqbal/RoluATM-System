# RoluATM - Raspberry Pi ATM System

A production-ready ATM system with World ID integration, running on Raspberry Pi 4 with Telequip T-Flex coin mechanism.

## Architecture

- **kiosk-pi**: Raspberry Pi 4 B running React touchscreen UI + Flask backend
- **cloud-api**: Vercel-hosted FastAPI service with Neon Postgres database

## Hardware Requirements

### Main Components
- Raspberry Pi 4 Model B (4GB+ RAM)
- 7" Touchscreen Display (official RPi or compatible)
- Telequip T-Flex coin mechanism
- USB-C power supply (official RPi 4 power supply)
- MicroSD card (32GB+, Class 10)

### Wiring Diagram

```
Raspberry Pi 4 GPIO Layout:
┌─────────────────────────────────┐
│ 1  2  3  4  5  6  7  8  9  10   │
│ 11 12 13 14 15 16 17 18 19 20   │
│ 21 22 23 24 25 26 27 28 29 30   │
│ 31 32 33 34 35 36 37 38 39 40   │
└─────────────────────────────────┘

Telequip T-Flex Connections:
- USB-CDC: Connect to any USB port (appears as /dev/ttyACM0)
- Power: 12V DC supply (separate from Pi)
- Coin Output: Gravity-fed to collection tray

Touchscreen:
- DSI connector for display
- USB for touch input
- 5V power from Pi GPIO or USB
```

## Installation

### 1. Raspberry Pi Setup

```bash
# Flash Raspberry Pi OS Lite to SD card
# Enable SSH and configure WiFi during flash

# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3-pip python3-venv nodejs npm chromium-browser git

# Clone repository
git clone <repository-url> /opt/roluatm
cd /opt/roluatm
```

### 2. Kiosk Service Setup

```bash
cd /opt/roluatm/kiosk-pi

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install
npm run build

# Install systemd services
cd ../systemd
sudo ./install.sh
```

### 3. Environment Configuration

```bash
# Copy environment template
cp /opt/roluatm/kiosk-pi/.env.example /opt/roluatm/kiosk-pi/.env

# Edit configuration
sudo nano /opt/roluatm/kiosk-pi/.env
```

Required environment variables:
```
CLOUD_API_URL=https://your-vercel-app.vercel.app
KIOSK_ID=kiosk-001
SERIAL_PORT=/dev/ttyACM0
PROMETHEUS_PORT=9090
```

### 4. Start Services

```bash
# Enable and start services
sudo systemctl enable worldcash.service
sudo systemctl enable kiosk-chromium.service
sudo systemctl start worldcash.service
sudo systemctl start kiosk-chromium.service

# Check status
sudo systemctl status worldcash.service
sudo systemctl status kiosk-chromium.service
```

## Cloud API Deployment

### Vercel Setup

```bash
cd cloud-api

# Install Vercel CLI
npm install -g vercel

# Deploy
vercel --prod
```

### Environment Variables (Vercel)

Set these in your Vercel dashboard:
```
NEON_DATABASE_URL=postgresql://username:password@host/database
WORLD_ID_APP_ID=your_world_id_app_id
WORLD_ID_ACTION=your_world_id_action
```

## First-Run Tests

### 1. Hardware Test

```bash
# Test Telequip connection
cd /opt/roluatm/kiosk-pi/backend
source venv/bin/activate
python -c "
from tflex_driver import TFlexDriver
driver = TFlexDriver('/dev/ttyACM0')
driver.connect()
print('Coin mechanism status:', driver.get_status())
driver.disconnect()
"
```

### 2. Service Test

```bash
# Test backend API
curl http://localhost:5000/api/balance

# Test frontend
curl http://localhost:3000

# Test cloud API
curl https://your-vercel-app.vercel.app/health
```

### 3. End-to-End Test

1. Power on system
2. Wait for kiosk to boot to Chromium
3. Touch screen should show RoluATM interface
4. Test coin insertion (if hardware connected)
5. Verify World ID QR code generation
6. Check Prometheus metrics at http://localhost:9090/metrics

## Development

### Running Locally

```bash
# Backend (Terminal 1)
cd kiosk-pi/backend
source venv/bin/activate
python app.py

# Frontend (Terminal 2)
cd kiosk-pi/frontend
npm run dev

# Cloud API (Terminal 3)
cd cloud-api
uvicorn main:app --reload
```

### Testing

```bash
# Python tests
cd kiosk-pi/backend
pytest tests/

# React tests
cd kiosk-pi/frontend
npm test

# Cloud API tests
cd cloud-api
pytest tests/
```

## Troubleshooting

### Common Issues

1. **Telequip not detected**: Check USB connection and permissions
   ```bash
   sudo usermod -a -G dialout $USER
   ls -la /dev/ttyACM*
   ```

2. **Chromium not starting**: Check X11 permissions
   ```bash
   sudo systemctl status kiosk-chromium.service
   ```

3. **Cloud API unreachable**: Check network and SSL certificates
   ```bash
   curl -v https://your-vercel-app.vercel.app/health
   ```

### Logs

```bash
# System logs
sudo journalctl -u worldcash.service -f
sudo journalctl -u kiosk-chromium.service -f

# Application logs
tail -f /opt/roluatm/kiosk-pi/backend/logs/app.log
```

## Security Notes

- All secrets are stored in `.env` files (not committed to git)
- HTTPS required for production World ID integration
- Raspberry Pi should be on isolated network segment
- Regular security updates required

## Support

For hardware issues, consult Telequip T-Flex documentation.
For software issues, check the logs and GitHub issues. 