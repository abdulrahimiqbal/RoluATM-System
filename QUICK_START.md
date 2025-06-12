# 🚀 RoluATM Quick Start Guide

Get your RoluATM system up and running in under 30 minutes!

## ⚡ One-Command Deployment

### For Complete System (Cloud + Kiosk)
```bash
./scripts/deploy.sh --production
```

### For Cloud API Only
```bash
cd cloud-api && vercel --prod
```

### For Kiosk Only (if cloud is already deployed)
```bash
./scripts/deploy.sh --cloud-url https://your-vercel-app.vercel.app
```

## 📋 Prerequisites

### Software Requirements
- **Node.js 16+** - For React frontend
- **Python 3.8+** - For backend services
- **Git** - For version control
- **Vercel CLI** - For cloud deployment (auto-installed)

### Hardware Requirements (Kiosk)
- **Raspberry Pi 4** (4GB+ recommended)
- **7" touchscreen display**
- **Telequip T-Flex coin mechanism**
- **USB-A to USB-B cable** (for coin mechanism)

### Accounts Needed
- **Vercel account** - For cloud hosting
- **Neon database** - For PostgreSQL storage
- **World ID app** - For user verification

## 🔧 Step-by-Step Setup

### 1. Clone and Setup
```bash
git clone <your-repo-url> roluatm
cd roluatm
```

### 2. Configure Environment Variables

#### For Vercel (Cloud API)
Set these in your Vercel dashboard:
```
NEON_DATABASE_URL=postgresql://username:password@host/database
WORLD_ID_APP_ID=app_263013ca6f702add37ad338fa43d4307
WORLD_ID_ACTION=withdraw-cash
```

#### For Kiosk (Auto-created by deployment script)
```bash
# Will be created automatically as kiosk-pi/.env
CLOUD_API_URL=https://your-vercel-app.vercel.app
KIOSK_ID=kiosk-001
SERIAL_PORT=/dev/ttyACM0
```

### 3. Deploy Cloud API
```bash
cd cloud-api
npm install -g vercel  # If not already installed
vercel --prod
```

### 4. Deploy Kiosk (on Raspberry Pi)
```bash
./scripts/deploy.sh --cloud-url https://your-vercel-app.vercel.app --production
```

### 5. Verify Deployment
```bash
# Check all services
curl https://your-vercel-app.vercel.app/health
curl http://localhost:5000/api/health
curl http://localhost:3000

# Run E2E tests
python3 tests/e2e_test.py https://your-vercel-app.vercel.app
```

## 🔍 Quick Verification Checklist

- [ ] **Cloud API responds** at `https://your-app.vercel.app/test`
- [ ] **Kiosk backend running** at `http://localhost:5000/api/health`  
- [ ] **Frontend accessible** at `http://localhost:3000`
- [ ] **Hardware connected** (T-Flex shows in `/dev/ttyACM0`)
- [ ] **Services enabled** (`systemctl status roluatm-backend`)
- [ ] **Monitoring active** (if enabled) at `http://localhost:3001`

## 🚨 Common Issues & Solutions

### "Module not found" errors
```bash
# Reinstall dependencies
cd kiosk-pi/backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install
```

### Vercel deployment fails
```bash
# Check Node.js version
node --version  # Should be 16+

# Check Vercel CLI
npm install -g vercel@latest
vercel whoami
```

### Hardware not detected
```bash
# Check USB connection
lsusb | grep -i telequip

# Check serial port
ls -la /dev/ttyACM*

# Test with different port
SERIAL_PORT=/dev/ttyUSB0 ./scripts/deploy.sh --cloud-url <URL>
```

### Services won't start
```bash
# Check logs
sudo journalctl -u roluatm-backend -f
sudo journalctl -u roluatm-frontend -f

# Restart services
sudo systemctl restart roluatm-backend roluatm-frontend
```

## 📊 Monitoring & Management

### Service Management
```bash
# View status
sudo systemctl status roluatm-backend roluatm-frontend

# View logs
sudo journalctl -u roluatm-backend -f

# Restart services
sudo systemctl restart roluatm-backend
```

### Monitoring Access
- **Grafana:** http://localhost:3001 (admin/admin123)
- **Prometheus:** http://localhost:9090
- **Metrics:** http://localhost:5000/metrics

### Performance Testing
```bash
# Run load test
cd tests && python3 load_test.py http://localhost:5000

# Monitor during operation
htop
iotop
```

## 🔐 Security Checklist

- [ ] **Change default passwords** (Grafana, etc.)
- [ ] **Configure firewall** (`ufw enable`)
- [ ] **Set up SSL certificates** (if using custom domain)
- [ ] **Enable rate limiting** in production
- [ ] **Review CORS settings** for frontend
- [ ] **Set up backup procedures**

## 🆘 Support & Troubleshooting

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
sudo systemctl restart roluatm-backend
```

### System Information
```bash
# Gather system info for support
./scripts/system_info.sh > support_info.txt
```

### Emergency Reset
```bash
# Stop all services
sudo systemctl stop roluatm-backend roluatm-frontend kiosk-chromium

# Reset and redeploy
./scripts/deploy.sh --cloud-url <URL> --skip-tests
```

## 📞 Getting Help

1. **Check logs first:** `sudo journalctl -u roluatm-backend -f`
2. **Run diagnostics:** `python3 tests/e2e_test.py`
3. **Review deployment checklist:** `cat deployment-checklist.md`
4. **Check hardware:** Ensure T-Flex is connected and powered

---

## 🎉 Success!

Once deployed, your RoluATM system will:
- ✅ Accept World ID verification
- ✅ Process coin exchanges 
- ✅ Monitor hardware status
- ✅ Log all transactions
- ✅ Provide real-time metrics
- ✅ Auto-restart on failures

**Your ATM is now ready for operation!** 🏧 