# RoluATM Cloud API

This project provides the cloud backend and mini-app interface for the RoluATM, a World ID-verified cryptocurrency ATM.

## 🚀 Features

-   **World ID Integration**: Ensures each user can only perform actions a limited number of times, preventing abuse.
-   **Secure Payments**: Integrated with World App for secure USDC transactions.
-   **Real-time Kiosk Monitoring**: (Future) SSE endpoint for real-time updates from the ATM hardware.
-   **FastAPI Backend**: Built with modern, high-performance Python.

## 🛠️ Setup and Installation

### 1. Prerequisites

-   Python 3.9+
-   A [Vercel](https://vercel.com) account for deployment.
-   A [Worldcoin Developer Account](https://developer.worldcoin.org/).

### 2. Environment Variables

This project requires several environment variables to function correctly. Create a `.env` file in the root of your project:

```
# .env file

# --- Worldcoin Developer Portal ---
# Your Application ID from the Worldcoin Developer Portal
WORLD_ID_APP_ID="app_xxxxxxxxxxxxxxxxxxxxxxxx"

# An Action ID created in the portal for the "withdraw-cash" action
WORLD_ID_ACTION="withdraw-cash"

# A Server-side API Key from the Worldcoin Developer Portal
# This is a secret and should be kept safe!
WORLD_API_KEY="wk_xxxxxxxxxxxxxxxxxxxxxxxx"


# --- RoluATM Configuration ---
# The public wallet address where the ATM will receive USDC funds
ROLU_WALLET_ADDRESS="0x........................................"

# (Optional) For production database connection
# DATABASE_URL="postgresql://user:password@host:port/database"
```

**Where to find these values:**

-   `WORLD_ID_APP_ID`: In your app's page on the Worldcoin Developer Portal.
-   `WORLD_ID_ACTION`: Create a new, unique action in the "Actions" section of your app in the portal. Name it `withdraw-cash`.
-   `WORLD_API_KEY`: Generate a new API key in the "Settings" of your app in the portal. Treat this like a password.
-   `ROLU_WALLET_ADDRESS`: This is the public address of the wallet you control, which will receive the funds from users. **You must whitelist this address in the Developer Portal.**

### 3. Installation

Clone the repository and install dependencies:

```bash
git clone <your-repo-url>
cd RoluATM-new
pip install -r requirements.txt
```

### 4. Running Locally

Use `uvicorn` to run the FastAPI server:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at `http://localhost:8000`.

### 5. Deployment

This project is optimized for deployment on [Vercel](https://vercel.com). Simply connect your GitHub repository to a new Vercel project.

**Important**: You must add the environment variables from your `.env` file to the "Environment Variables" section of your project settings in Vercel.

## API Endpoints

-   `/`: Serves the main RoluATM Mini App interface.
-   `/world-app.json`: World App manifest file.
-   `/api/verify-world-id`: Backend endpoint to verify World ID proofs.
-   `/api/initiate-payment`: Starts the payment process.
-   `/api/confirm-payment`: Confirms the payment on the blockchain.
-   `/health`: Health check endpoint.

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request.