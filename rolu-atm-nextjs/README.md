# RoluATM - World ID Cash Withdrawal System

A modern, secure cash withdrawal system using World ID verification and blockchain technology.

## 🏧 Features

- **World ID Authentication**: Secure sign-in using World ID verification
- **Balance Management**: View and manage your World ID balance
- **Cash Withdrawal**: Withdraw cash from physical ATM locations
- **Hardware Integration**: Connects to Raspberry Pi + TFlex cash dispensers
- **Mobile-First Design**: Optimized for World App mobile interface
- **Real-time Updates**: Live transaction status and balance updates

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ and npm
- World ID App ID and API key
- (Optional) Raspberry Pi with TFlex hardware for physical cash dispensing

### Installation

1. **Clone and install dependencies:**
   ```bash
   cd rolu-atm-nextjs
   npm install
   ```

2. **Configure environment variables:**
   ```bash
   # Copy the example environment file
   cp .env.local.example .env.local
   
   # Edit .env.local with your configuration:
   NEXT_PUBLIC_WORLD_ID_APP_ID=app_your_world_id_app_id_here
   WORLD_ID_API_KEY=your_world_id_api_key
   JWT_SECRET=your_super_secret_jwt_key
   MOCK_HARDWARE=true  # Set to false for real hardware
   ```

3. **Start the development server:**
   ```bash
   npm run dev
   ```

4. **Open in World App:**
   - Navigate to `http://localhost:3000` in World App
   - Or scan QR code to test in World App mobile

## 📱 User Flow

### 1. Sign In with World ID
- User opens the app in World App
- Clicks "Sign In with World ID"
- Completes World ID verification (Orb or Device)
- Account created automatically with $100 starting balance

### 2. View Balance
- See current World ID balance
- View account verification status
- Check withdrawal limits and available funds

### 3. Withdraw Cash
- Select preset amounts ($5, $10, $20, $50)
- Or enter custom amount (up to $500 daily limit)
- Confirm withdrawal
- Cash dispensed from physical ATM (or simulated in development)

## 🔧 Technical Architecture

### Frontend (Next.js)
```
src/
├── app/
│   ├── page.tsx              # Sign-in page
│   ├── balance/page.tsx      # Balance & withdrawal page
│   └── api/                  # API routes
│       ├── auth/route.ts     # World ID authentication
│       ├── balance/route.ts  # Balance retrieval
│       └── withdraw/route.ts # Cash withdrawal
├── components/
│   ├── WorldIdSignIn.tsx     # World ID authentication
│   ├── BalanceDisplay.tsx    # Balance display
│   ├── WithdrawalForm.tsx    # Withdrawal interface
│   └── providers/
│       └── minikit-provider.tsx # MiniKit initialization
└── lib/
    ├── worldid.ts           # World ID verification
    ├── auth.ts              # JWT authentication
    └── database.ts          # Database operations
```

### Backend Integration
- **Authentication**: JWT tokens with HTTP-only cookies
- **World ID Verification**: Server-side proof verification
- **Hardware Communication**: REST API to Raspberry Pi
- **Database**: In-memory storage (development) / Neon Postgres (production)

### Hardware Integration
- **Raspberry Pi**: Runs Flask backend for hardware control
- **TFlex Dispenser**: Physical cash dispensing mechanism
- **Mock Mode**: Simulated hardware for development/testing

## 🔐 Security Features

- **World ID Verification**: Privacy-preserving identity verification
- **JWT Authentication**: Secure session management
- **HTTP-Only Cookies**: XSS protection
- **Server-Side Validation**: All transactions verified server-side
- **Hardware Isolation**: Separate Pi backend for hardware control

## 🧪 Testing

### Development Mode
- Set `MOCK_HARDWARE=true` in `.env.local`
- Hardware operations are simulated
- 95% success rate simulation for testing error handling

### World App Testing
1. **Local Testing**: Use `http://localhost:3000` in World App
2. **QR Code**: Generate QR code for mobile testing
3. **World ID Simulator**: Use World ID simulator for development

### API Testing
```bash
# Test authentication
curl -X POST http://localhost:3000/api/auth \
  -H "Content-Type: application/json" \
  -d '{"worldIdProof": {...}, "action": "rolu-atm-signin"}'

# Test balance (requires auth cookie)
curl http://localhost:3000/api/balance

# Test withdrawal (requires auth cookie)
curl -X POST http://localhost:3000/api/withdraw \
  -H "Content-Type: application/json" \
  -d '{"amount": 10}'
```

## 🚀 Deployment

### Vercel Deployment
1. **Connect to Vercel:**
   ```bash
   npm install -g vercel
   vercel
   ```

2. **Configure environment variables in Vercel dashboard:**
   - `NEXT_PUBLIC_WORLD_ID_APP_ID`
   - `WORLD_ID_API_KEY`
   - `JWT_SECRET`
   - `KIOSK_PI_URL` (for production hardware)

3. **Deploy:**
   ```bash
   vercel --prod
   ```

### Hardware Setup
1. **Raspberry Pi Configuration:**
   - Install Python Flask backend
   - Connect TFlex hardware
   - Configure network connectivity

2. **Environment Variables:**
   ```bash
   # On Raspberry Pi
   export CLOUD_API_URL=https://your-vercel-app.vercel.app
   export KIOSK_ID=kiosk-001
   export SERIAL_PORT=/dev/ttyACM0
   ```

## 📊 Monitoring

### Development
- Console logs for all operations
- Real-time transaction status
- Balance updates
- Error handling and display

### Production
- Prometheus metrics (on Pi)
- Transaction logging
- Hardware status monitoring
- Cloud connectivity checks

## 🔄 Database Schema

### Users Table
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    nullifier_hash VARCHAR(255) UNIQUE NOT NULL,
    verification_level VARCHAR(20) NOT NULL,
    balance DECIMAL(10,2) DEFAULT 100.00,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Transactions Table
```sql
CREATE TABLE transactions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    amount DECIMAL(10,2) NOT NULL,
    type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🛠️ Development

### Adding New Features
1. **Frontend**: Add components in `src/components/`
2. **API**: Add routes in `src/app/api/`
3. **Database**: Update schema in `src/lib/database.ts`
4. **Hardware**: Extend Pi backend for new hardware features

### Testing Checklist
- [ ] World ID authentication works
- [ ] Balance display is accurate
- [ ] Withdrawal flow completes
- [ ] Error handling works
- [ ] Mobile responsiveness
- [ ] Hardware integration (if applicable)

## 📞 Support

For issues or questions:
1. Check console logs for error details
2. Verify environment variables are set
3. Test with `MOCK_HARDWARE=true` first
4. Check World ID Developer Portal configuration

## 🔗 Related Projects

- **Original RoluATM**: Python FastAPI backend in `../cloud-api/`
- **Hardware Backend**: Raspberry Pi Flask app in `../kiosk-pi/`
- **Rolu Platform**: Educational gaming platform with World ID integration

---

**Built with ❤️ using Next.js, World ID, and modern web technologies.**
