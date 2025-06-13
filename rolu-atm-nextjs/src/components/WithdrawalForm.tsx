'use client';

import { useState } from 'react';

interface WithdrawalFormProps {
  balance: number;
  onWithdrawal: () => void;
}

export const WithdrawalForm = ({ balance, onWithdrawal }: WithdrawalFormProps) => {
  const [amount, setAmount] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [status, setStatus] = useState('');

  const presetAmounts = [5, 10, 20, 50];

  const handleWithdraw = async (withdrawAmount: number) => {
    if (withdrawAmount > balance) {
      setStatus('❌ Insufficient balance');
      setTimeout(() => setStatus(''), 3000);
      return;
    }

    if (withdrawAmount <= 0) {
      setStatus('❌ Invalid amount');
      setTimeout(() => setStatus(''), 3000);
      return;
    }

    setIsProcessing(true);
    setStatus('🔄 Processing withdrawal...');

    try {
      console.log(`💰 Initiating withdrawal of $${withdrawAmount}`);
      
      const response = await fetch('/api/withdraw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: withdrawAmount })
      });

      console.log('📋 Withdrawal response status:', response.status);

      if (response.ok) {
        const result = await response.json();
        console.log('✅ Withdrawal successful:', result);
        
        setStatus('💰 Dispensing cash...');
        
        // Simulate cash dispensing time
        setTimeout(() => {
          setStatus('✅ Cash dispensed successfully!');
          onWithdrawal(); // Refresh balance
          setAmount('');
          
          // Clear success message after 5 seconds
          setTimeout(() => setStatus(''), 5000);
        }, 3000);
      } else {
        const error = await response.json();
        console.error('❌ Withdrawal failed:', error);
        setStatus(`❌ ${error.message || 'Withdrawal failed'}`);
        setTimeout(() => setStatus(''), 5000);
      }
    } catch (error) {
      console.error('❌ Withdrawal error:', error);
      setStatus('❌ Network error. Please try again.');
      setTimeout(() => setStatus(''), 5000);
    } finally {
      setIsProcessing(false);
    }
  };

  const isAmountValid = (amt: number) => amt > 0 && amt <= balance && amt <= 500;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-center text-gray-800">Withdraw Cash</h2>
      
      {/* Preset amounts */}
      <div className="grid grid-cols-2 gap-3">
        {presetAmounts.map((preset) => (
          <button
            key={preset}
            onClick={() => handleWithdraw(preset)}
            disabled={isProcessing || preset > balance}
            className={`py-3 px-4 rounded-lg font-medium transition-colors ${
              preset > balance
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50'
            }`}
          >
            ${preset}
          </button>
        ))}
      </div>

      {/* Custom amount */}
      <div className="space-y-3">
        <div className="relative">
          <span className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500">$</span>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Enter custom amount"
            max={Math.min(balance, 500)}
            min="1"
            step="0.01"
            className="w-full pl-8 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        
        <button
          onClick={() => handleWithdraw(parseFloat(amount))}
          disabled={isProcessing || !amount || !isAmountValid(parseFloat(amount))}
          className="w-full bg-green-500 text-white py-3 px-4 rounded-lg font-medium hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isProcessing ? (
            <div className="flex items-center justify-center space-x-2">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              <span>Processing...</span>
            </div>
          ) : (
            `Withdraw $${amount || '0.00'}`
          )}
        </button>
      </div>

      {/* Withdrawal limits info */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
        <p className="text-xs text-blue-600 text-center">
          💡 Daily limit: $500 • Available: ${Math.min(balance, 500).toFixed(2)}
        </p>
      </div>

      {/* Status */}
      {status && (
        <div className={`text-center p-3 rounded-lg ${
          status.includes('❌') 
            ? 'bg-red-50 border border-red-200 text-red-700'
            : status.includes('✅')
            ? 'bg-green-50 border border-green-200 text-green-700'
            : 'bg-blue-50 border border-blue-200 text-blue-700'
        }`}>
          <p className="text-sm font-medium">{status}</p>
        </div>
      )}
    </div>
  );
}; 