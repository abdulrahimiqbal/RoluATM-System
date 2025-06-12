# RoluATM - World ID Verified Cryptocurrency ATM

A modern World Mini App that provides secure, World ID-verified cash withdrawal from cryptocurrency using the latest MiniKit SDK and World App integration.

## 🚀 Features

- **World ID Verification**: Secure proof-of-personhood using the latest World ID API v2
- **MiniKit Integration**: Built with the latest `@worldcoin/minikit-js` SDK
- **Secure Payments**: USDC transactions through World App's native payment system
- **Modern API**: FastAPI backend with comprehensive error handling
- **Real-time Updates**: SSE endpoints for kiosk monitoring
- **Mobile-First**: Optimized for World App's mobile environment

## 🛠️ Setup and Installation

### 1. Prerequisites

- Python 3.9+
- [Vercel](https://vercel.com) account for deployment
- [World Developer Account](https://developer.worldcoin.org/)
- [Neon Database](https://neon.tech/) for production data storage

### 2. Environment Variables

Create a `.env` file with the following required variables:

```env
# --- World Developer Portal Configuration ---
# Your App ID from the World Developer Portal
WORLD_ID_APP_ID="app_263013ca6f702add37ad338fa43d4307"

# Action ID for cash withdrawal (create in Developer Portal)
WORLD_ID_ACTION="withdraw-cash"

# Server-side API Key from World Developer Portal (keep secret!)
WORLD_API_KEY="wk_xxxxxxxxxxxxxxxxxxxxxxxx"

# --- RoluATM Configuration ---
# Wallet address to receive USDC payments (must be whitelisted in Developer Portal)
ROLU_WALLET_ADDRESS="0x742fd484b63E7C9b7f34FAb65A8c165B7cd5C5e8"

# --- Database Configuration ---
# Neon PostgreSQL connection string for production
NEON_DATABASE_URL="postgresql://user:password@host:port/database"
```

### 3. World Developer Portal Setup

1. **Create a World App** in the [Developer Portal](https://developer.worldcoin.org/)
2. **Add an Incognito Action**:
   - Name: `withdraw-cash`
   - Description: "Verify identity for cash withdrawal"
   - Max verifications per user: `5` (or your preferred limit)
3. **Whitelist your wallet address** in the app settings
4. **Generate an API key** for backend verification
5. **Set your app URL** to your Vercel deployment URL

### 4. Installation

```bash
git clone <your-repo-url>
cd RoluATM-new
pip install -r cloud-api/requirements.txt
```

### 5. Running Locally

```bash
cd cloud-api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at `http://localhost:8000`.

### 6. Deployment to Vercel

1. Connect your GitHub repository to Vercel
2. Set the **Root Directory** to `cloud-api`
3. Add all environment variables to Vercel's Environment Variables section
4. Deploy and test with the World App

## 📱 Testing in World App

### Method 1: QR Code Testing
1. Visit `/test-qr` on your deployed app
2. Scan the QR code with World App
3. Test the complete flow

### Method 2: Direct URL
Use the World App deep link format:
```
worldapp://mini-app?app_id=app_263013ca6f702add37ad338fa43d4307
```

## 🔧 API Endpoints

### Core Mini App Endpoints
- `GET /` - Main RoluATM Mini App interface
- `GET /world-app.json` - World App manifest
- `GET /rolu-miniapp.html` - Standalone mini app (latest MiniKit)

### Payment Flow API
- `POST /api/initiate-payment` - Verify World ID and initiate payment
- `POST /api/confirm-payment` - Confirm payment completion
- `GET /payment-success/{session_id}` - Payment success page

### Utility Endpoints
- `GET /health` - Health check
- `GET /status` - API status and configuration
- `GET /test-qr` - QR code testing interface

## 🔄 Payment Flow

1. **User scans QR code** → Opens mini app in World App
2. **World ID Verification** → User verifies identity with World ID
3. **Payment Authorization** → User authorizes USDC payment
4. **Backend Confirmation** → Server confirms transaction
5. **Cash Dispensing** → ATM dispenses quarters

## 🛡️ Security Features

- **Backend World ID Verification**: All proofs verified server-side
- **Secure API Keys**: Environment-based configuration
- **Error Handling**: Comprehensive error responses
- **Rate Limiting**: World ID action limits prevent abuse
- **Wallet Whitelisting**: Only approved addresses can receive funds

## 🔧 Latest Updates (2025)

### Frontend Modernization
- ✅ Updated to latest MiniKit SDK (`@latest`)
- ✅ Fixed `commandsAsync` API usage
- ✅ Proper error handling for command availability
- ✅ Modern initialization flow

### Backend Improvements
- ✅ Updated World ID API v2 endpoint
- ✅ Enhanced payload validation
- ✅ Better error handling and logging
- ✅ Modern payment confirmation flow

### Manifest Updates
- ✅ Updated world-app.json for latest requirements
- ✅ Added app_id and version fields
- ✅ Specified minimum World App version

## 🐛 Troubleshooting

### "Verify command is not supported"
- Ensure you're using the latest World App version
- Check that your app is properly configured in Developer Portal
- Verify MiniKit is loading correctly

### Payment Issues
- Confirm wallet address is whitelisted in Developer Portal
- Check WORLD_API_KEY is valid and has proper permissions
- Verify USDC balance in user's World App wallet

### Development Issues
- Use `/test-qr` endpoint for testing
- Check browser console for MiniKit errors
- Verify all environment variables are set

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Test thoroughly with World App
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.