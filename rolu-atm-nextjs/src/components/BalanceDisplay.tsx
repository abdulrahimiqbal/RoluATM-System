interface User {
  id: string;
  verification_level?: string;
  nullifier_hash?: string;
  wallet_address?: string;
}

interface BalanceDisplayProps {
  balance: number;
  user: User | null;
  onRefresh?: () => void;
}

export const BalanceDisplay = ({ balance, user, onRefresh }: BalanceDisplayProps) => {
  const formatAddress = (address: string) => {
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  };

  const formatNullifier = (hash: string) => {
    return `${hash.slice(0, 6)}...${hash.slice(-4)}`;
  };

  return (
    <div className="text-center space-y-4">
      <div className="bg-gradient-to-r from-green-400 to-emerald-500 text-white p-6 rounded-lg shadow-lg">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm opacity-90">Total Balance (USDC)</p>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="text-white/80 hover:text-white transition-colors p-1 rounded"
              title="Refresh balance"
            >
              🔄
            </button>
          )}
        </div>
        <p className="text-4xl font-bold">${balance.toFixed(2)}</p>
        {user?.wallet_address && (
          <p className="text-xs opacity-75 mt-2">
            💰 Converted from your crypto assets
          </p>
        )}
      </div>
      
      {user && (
        <div className="bg-gray-50 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-center space-x-2">
            <span className="text-lg">
              {user.wallet_address ? '💰' : user.verification_level === 'orb' ? '🌍' : '📱'}
            </span>
            <span className="text-sm font-medium text-gray-700">
              {user.wallet_address ? 'Wallet Connected' : 
               user.verification_level === 'orb' ? 'Orb Verified' : 'Device Verified'}
            </span>
          </div>
          
          <div className="text-xs text-gray-500">
            {user.wallet_address ? (
              <p>Wallet: {formatAddress(user.wallet_address)}</p>
            ) : user.nullifier_hash ? (
              <p>Account ID: {formatNullifier(user.nullifier_hash)}</p>
            ) : (
              <p>Account ID: {user.id.slice(0, 8)}...</p>
            )}
          </div>
        </div>
      )}

      <div className="text-xs text-gray-400 space-y-1">
        {user?.wallet_address ? (
          <>
            <p>💡 Balance includes ETH, USDC, WLD & other tokens</p>
            <p>🔄 Converted to USDC at current market rates</p>
            <p>🏧 Withdraw cash from any RoluATM location</p>
          </>
        ) : (
          <>
            <p>💡 This is your wallet balance</p>
            <p>Withdraw cash from any RoluATM location</p>
          </>
        )}
      </div>
    </div>
  );
}; 