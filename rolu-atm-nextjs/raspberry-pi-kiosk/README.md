# 🥧 RoluATM Raspberry Pi Kiosk

This directory contains the complete Raspberry Pi kiosk system that handles PIN verification and cash dispensing for the RoluATM system.

## 🏗️ System Architecture

```
Cloud Backend → PIN Request → Raspberry Pi → PIN Input → Cash Dispenser → Completion Notification
```

## 📋 Hardware Requirements

### Required Components:
- **Raspberry Pi 4** (4GB+ RAM recommended)
- **MicroSD Card** (32GB+ Class 10)
- **7" Touchscreen Display** (800x480 recommended)
- **Cash Dispenser Module** (with relay control)
- **Status LED** (Green/Red)
- **Buzzer** (for audio feedback)
- **Relay Module** (for cash dispenser control)
- **Jumper Wires** and **Breadboard**

### GPIO Pin Connections:
```
GPIO 18 → Cash Dispenser Relay (IN)
GPIO 24 → Status LED (Anode)
GPIO 23 → Buzzer (Positive)
GND     → All Ground connections
5V      → Relay Module VCC
```

## 🚀 Installation

### 1. Prepare Raspberry Pi

```bash
# Flash Raspberry Pi OS to SD card
# Enable SSH and I2C in raspi-config
sudo raspi-config

# Update system
sudo apt update && sudo apt upgrade -y
```

### 2. Clone and Setup

```bash
# Copy kiosk files to Raspberry Pi
scp -r raspberry-pi-kiosk/ pi@[PI_IP]:/home/pi/rolu-kiosk/

# SSH into Raspberry Pi
ssh pi@[PI_IP]

# Navigate to kiosk directory
cd /home/pi/rolu-kiosk

# Run installation script
chmod +x install.sh
./install.sh
```

### 3. Configure Environment

Edit `.env` file with your specific configuration:

```bash
nano .env
```

```env
# Cloud API Configuration
CLOUD_API_URL=https://your-vercel-app.vercel.app
KIOSK_ID=kiosk_001
KIOSK_PORT=5000

# Hardware Configuration (adjust GPIO pins as needed)
DISPENSER_RELAY_PIN=18
STATUS_LED_PIN=24
BUZZER_PIN=23
```

### 4. Start the Service

```bash
# Reboot to apply all changes
sudo reboot

# Check service status
sudo systemctl status rolu-kiosk

# View real-time logs
sudo journalctl -u rolu-kiosk -f
```

## 🔧 Hardware Setup

### Cash Dispenser Connection:
```
Raspberry Pi GPIO 18 → Relay Module IN
Relay Module COM → Cash Dispenser Control Wire
Relay Module NO → Cash Dispenser Power (+)
Cash Dispenser Ground → Raspberry Pi GND
```

### Status LED Connection:
```
Raspberry Pi GPIO 24 → LED Anode (long leg)
LED Cathode (short leg) → 220Ω Resistor → GND
```

### Buzzer Connection:
```
Raspberry Pi GPIO 23 → Buzzer Positive
Buzzer Negative → GND
```

## 📱 Kiosk Interface

The kiosk displays different screens based on the current state:

### 1. Ready Screen
- Shows "RoluATM Ready for Withdrawals"
- Displays kiosk ID
- Green status LED

### 2. PIN Input Screen
- Shows withdrawal amount
- 6-digit PIN input field
- On-screen keypad (or physical keypad)
- Instructions for user

### 3. Dispensing Screen
- Shows "Dispensing Cash..."
- Amount being dispensed
- Progress indicator
- Dispensing sound effects

### 4. Success Screen
- "Transaction Complete!"
- Amount dispensed
- Thank you message
- Success sound

### 5. Error Screens
- PIN incorrect
- PIN expired
- Dispenser error
- Too many attempts

## 🔄 Complete Transaction Flow

1. **Cloud Backend** sends PIN request to kiosk
2. **Kiosk** displays PIN input screen
3. **User** enters 6-digit PIN on keypad/touchscreen
4. **Kiosk** validates PIN and expiry time
5. **Cash Dispenser** activates and dispenses cash
6. **Kiosk** sends completion notification to cloud
7. **Cloud Backend** updates withdrawal status

## 🛠️ API Endpoints

### Kiosk Server Endpoints:

#### POST `/pin-request`
Receives PIN requests from cloud backend.

**Request:**
```json
{
  "withdrawalId": "uuid",
  "amount": 50.00,
  "pin": "123456",
  "expiresAt": "2024-01-01T12:00:00Z",
  "walletAddress": "0x..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "PIN request received"
}
```

#### GET `/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "kiosk_id": "kiosk_001",
  "timestamp": "2024-01-01T12:00:00Z",
  "active_withdrawals": 1,
  "is_dispensing": false
}
```

## 🔍 Monitoring & Debugging

### View Logs:
```bash
# Real-time logs
sudo journalctl -u rolu-kiosk -f

# Recent logs
sudo journalctl -u rolu-kiosk --since "1 hour ago"

# Error logs only
sudo journalctl -u rolu-kiosk -p err
```

### Test Kiosk:
```bash
# Health check
curl http://localhost:5000/health

# Test PIN request (for debugging)
curl -X POST http://localhost:5000/pin-request \
  -H "Content-Type: application/json" \
  -d '{
    "withdrawalId": "test-123",
    "amount": 20.00,
    "pin": "123456",
    "expiresAt": "2024-12-31T23:59:59Z",
    "walletAddress": "0x123..."
  }'
```

### GPIO Testing:
```bash
# Test GPIO pins (run as root)
sudo python3 -c "
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.OUT)
GPIO.output(18, GPIO.HIGH)
time.sleep(2)
GPIO.output(18, GPIO.LOW)
GPIO.cleanup()
print('GPIO test complete')
"
```

## 🔒 Security Considerations

1. **Network Security:**
   - Use HTTPS for all cloud communication
   - Implement API authentication
   - Firewall configuration

2. **Physical Security:**
   - Secure kiosk enclosure
   - Tamper detection
   - Camera monitoring

3. **Software Security:**
   - Regular system updates
   - Secure PIN handling
   - Audit logging

## 🚨 Troubleshooting

### Common Issues:

#### Service Won't Start:
```bash
# Check service status
sudo systemctl status rolu-kiosk

# Check Python path
which python3

# Check permissions
ls -la /home/pi/rolu-kiosk/
```

#### GPIO Errors:
```bash
# Check GPIO permissions
groups pi

# Add user to gpio group
sudo usermod -a -G gpio pi

# Reboot after adding to group
sudo reboot
```

#### Display Issues:
```bash
# Check display connection
sudo dmesg | grep -i display

# Test pygame
python3 -c "import pygame; print('Pygame OK')"
```

#### Network Issues:
```bash
# Test cloud connectivity
curl -I https://your-vercel-app.vercel.app

# Check DNS resolution
nslookup your-vercel-app.vercel.app
```

## 📞 Support

For technical support:
1. Check the logs first: `sudo journalctl -u rolu-kiosk -f`
2. Verify hardware connections
3. Test individual components
4. Check cloud backend connectivity

## 🔄 Updates

To update the kiosk software:

```bash
# Stop service
sudo systemctl stop rolu-kiosk

# Update code
git pull origin main

# Restart service
sudo systemctl start rolu-kiosk

# Check status
sudo systemctl status rolu-kiosk
```

## 📊 Production Deployment

For production deployment:

1. **Hardware Hardening:**
   - Industrial-grade components
   - Surge protection
   - UPS backup power

2. **Software Hardening:**
   - Read-only filesystem
   - Automatic updates
   - Remote monitoring

3. **Monitoring:**
   - Health check alerts
   - Performance monitoring
   - Error reporting

4. **Maintenance:**
   - Regular cash refills
   - Hardware inspection
   - Software updates 