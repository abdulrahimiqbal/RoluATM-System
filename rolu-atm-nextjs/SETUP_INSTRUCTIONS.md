# 🎯 Complete RoluATM System Setup & Testing

## 🔐 Required Environment Variables

### 1. Create `.env.local` file:
```bash
# World Network Configuration
APP_ID=app_263013ca6f702add37ad338fa43d4307
DEV_PORTAL_API_KEY=your_actual_world_id_developer_portal_api_key

# JWT Secret (generate secure random string)
JWT_SECRET=your_super_secure_jwt_secret_at_least_32_characters_long

# Kiosk Configuration  
KIOSK_API_URL=http://[RASPBERRY_PI_IP]:5000

# Development/Production Mode
NODE_ENV=production
```

### 2. Get Your Developer Portal API Key:
1. Go to [World ID Developer Portal](https://developer.worldcoin.org/)
2. Navigate to your app: `app_263013ca6f702add37ad338fa43d4307`
3. Go to "API Keys" section
4. Copy your API key
5. Paste it as `DEV_PORTAL_API_KEY` in `.env.local`

## 🥧 Raspberry Pi Setup

### 1. Hardware Requirements:
- Raspberry Pi 4 (4GB+ recommended)
- 7" Touchscreen display
- Cash dispenser module (bill dispenser)
- Relay module (for dispenser control)
- Jumper wires and breadboard

### 2. GPIO Connections:
```
Raspberry Pi GPIO 18 → Relay Module IN
Relay Module COM → Cash Dispenser Control Wire
Relay Module NO → Cash Dispenser Power (+12V)
Cash Dispenser GND → Common Ground
Status LED → GPIO 24 (with 220Ω resistor)
Buzzer → GPIO 23
```

### 3. Install Kiosk Software:
```bash
# Copy files to Raspberry Pi
scp -r raspberry-pi-kiosk/ pi@[PI_IP]:/home/pi/rolu-kiosk/

# SSH into Pi and install
ssh pi@[PI_IP]
cd /home/pi/rolu-kiosk
chmod +x install.sh
./install.sh

# Edit environment with your cloud URL
nano .env
# Set CLOUD_API_URL=https://your-vercel-app.vercel.app

# Reboot and start
sudo reboot
```

## 🧪 Complete End-to-End Test

### Test Flow:
```
📱 World App → 💰 Withdraw → ⛓️ USDC Transaction → 
☁️ Cloud Monitors → 🔑 PIN Generated → 📡 Sent to Kiosk → 
🥧 User Enters PIN → ⚡ GPIO Activates → 💰 Cash Dispensed
```

### 1. Pre-Test Checklist:
- [ ] `.env.local` configured with real API keys
- [ ] Raspberry Pi running with kiosk service active
- [ ] Cash dispenser loaded with bills
- [ ] GPIO connections verified
- [ ] Network connectivity between cloud and kiosk

### 2. Test Steps:
1. **Open World App** on mobile device
2. **Navigate to RoluATM** (your deployed app URL)
3. **Connect Wallet** using SIWE authentication
4. **Check Balance** - should show real USDC value
5. **Enter Withdrawal Amount** (start with $20)
6. **Confirm Transaction** - MiniKit should prompt for approval
7. **Approve in World App** - sign the USDC transfer
8. **Wait for Confirmation** - cloud monitors transaction
9. **Go to Kiosk** - PIN input screen should appear
10. **Enter PIN** - 6-digit code from transaction
11. **Verify Cash Dispensed** - physical bills should dispense
12. **Check Completion** - transaction marked complete

### 3. Monitoring During Test:
```bash
# Monitor cloud logs (Vercel)
vercel logs --follow

# Monitor kiosk logs (on Raspberry Pi)
sudo journalctl -u rolu-kiosk -f

# Check kiosk health
curl http://[PI_IP]:5000/health
```

## 🔍 Troubleshooting

### Common Issues:

#### Transaction Monitoring Fails:
- Check DEV_PORTAL_API_KEY is correct
- Verify APP_ID matches your World ID app
- Check network connectivity

#### Kiosk Not Receiving PIN:
- Verify CLOUD_API_URL in kiosk .env
- Check firewall settings on Raspberry Pi
- Test direct API call to kiosk

#### Cash Dispenser Not Working:
- Check GPIO wiring (GPIO 18 to relay)
- Verify relay module power (5V)
- Test relay manually with multimeter
- Check cash dispenser power supply

#### PIN Input Not Working:
- Check kiosk display connection
- Verify pygame installation
- Test touchscreen calibration

## 🎯 Success Criteria

### Complete Test Success:
1. ✅ User initiates withdrawal in World App
2. ✅ USDC transaction confirmed on World Network
3. ✅ PIN generated and sent to kiosk
4. ✅ Kiosk displays PIN input screen
5. ✅ User enters correct PIN
6. ✅ Physical cash dispensed from machine
7. ✅ Transaction marked complete in system
8. ✅ User balance updated

### System is 100% Ready When:
- [ ] All environment variables configured
- [ ] Raspberry Pi kiosk operational
- [ ] Cash dispenser hardware connected
- [ ] End-to-end test successful
- [ ] Error handling verified
- [ ] Security measures in place

## 🚀 Production Deployment

Once testing is complete:
1. Deploy kiosks to target locations
2. Set up cash refill procedures
3. Monitor transaction volumes
4. Scale to additional locations

## 📞 Support

If you encounter issues:
1. Check logs first (cloud and kiosk)
2. Verify all connections and configuration
3. Test individual components separately
4. Document any errors for troubleshooting 