'use client';

import { useState } from 'react';
import { MiniKit, Tokens } from '@worldcoin/minikit-js';
import { WORLD_CHAIN_CONTRACTS, ERC20_ABI, ROLU_TREASURY_ADDRESS, toUSDCUnits } from '@/lib/contracts';

interface WithdrawalFormProps {
  balance: number;
  onWithdrawal: () => void;
}

export const WithdrawalForm = ({ balance, onWithdrawal }: WithdrawalFormProps) => {
  const [amount, setAmount] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [status, setStatus] = useState('');
  const [currentStep, setCurrentStep] = useState<'input' | 'transaction' | 'monitoring' | 'pin' | 'complete'>('input');

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
    setCurrentStep('transaction');
    setStatus('🔄 Creating World Network transaction...');

    try {
      console.log(`💰 Initiating World Network withdrawal of $${withdrawAmount}`);
      
      // Check if MiniKit is available
      if (!MiniKit.isInstalled()) {
        throw new Error('Please open this app in World App');
      }

      // Create World Network transaction
      console.log('🌐 Sending USDC transfer transaction...');
      
      // Log transaction details for debugging
      const transferAmount = toUSDCUnits(withdrawAmount);
      console.log('🔍 Transaction details:');
      console.log('  - Contract:', WORLD_CHAIN_CONTRACTS.USDC);
      console.log('  - To Address:', ROLU_TREASURY_ADDRESS);
      console.log('  - Amount (raw):', withdrawAmount);
      console.log('  - Amount (USDC units):', transferAmount);
      console.log('  - User balance:', balance);
      
      // Try sendTransaction first (requires contract whitelisting)
      let finalPayload;
      try {
        const response = await MiniKit.commandsAsync.sendTransaction({
          transaction: [
            {
              address: WORLD_CHAIN_CONTRACTS.USDC,
              abi: ERC20_ABI,
              functionName: 'transfer',
              args: [
                ROLU_TREASURY_ADDRESS,
                transferAmount
              ]
            }
          ]
        });
        finalPayload = response.finalPayload;
        
        // Check if sendTransaction returned an error (it doesn't throw, it returns error status)
        if (finalPayload.status === 'error' && finalPayload.error_code === 'invalid_contract') {
          console.log('📧 sendTransaction returned invalid_contract error, trying Pay command...');
          console.log('Error details:', finalPayload);
          
          // Fallback to Pay command (simpler, works with whitelisted addresses)
          const payResponse = await MiniKit.commandsAsync.pay({
            reference: `rolu-withdrawal-${Date.now()}`,
            to: ROLU_TREASURY_ADDRESS,
            tokens: [
              {
                symbol: Tokens.USDC,
                token_amount: transferAmount
              }
            ],
            description: `RoluATM withdrawal of $${withdrawAmount}`
          });
          finalPayload = payResponse.finalPayload;
          console.log('📧 Pay command response:', finalPayload);
        }
      } catch (sendTransactionError) {
        console.log('📧 sendTransaction threw an exception, trying Pay command...');
        console.log('Error:', sendTransactionError);
        
        // Fallback to Pay command (simpler, works with whitelisted addresses)
        const payResponse = await MiniKit.commandsAsync.pay({
          reference: `rolu-withdrawal-${Date.now()}`,
          to: ROLU_TREASURY_ADDRESS,
          tokens: [
            {
              symbol: Tokens.USDC,
              token_amount: transferAmount
            }
          ],
          description: `RoluATM withdrawal of $${withdrawAmount}`
        });
        finalPayload = payResponse.finalPayload;
        console.log('📧 Pay command response:', finalPayload);
      }

      console.log('📋 Transaction response:', finalPayload);

      if (finalPayload.status === 'success') {
        console.log('✅ Transaction created successfully:', finalPayload.transaction_id);
        
        setCurrentStep('monitoring');
        setStatus('⛓️ Transaction submitted. Waiting for confirmation...');
        
        // Send transaction to backend for monitoring
        const response = await fetch('/api/initiate-withdrawal', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            transactionId: finalPayload.transaction_id,
            amount: withdrawAmount
          })
        });

        console.log('📋 Backend response status:', response.status);

        if (response.ok) {
          const result = await response.json();
          console.log('✅ Withdrawal monitoring started:', result);
          
          setCurrentStep('pin');
          setStatus('🔑 Transaction confirmed! PIN will be sent to kiosk shortly...');
          
          // Simulate PIN generation and kiosk notification
          setTimeout(() => {
            setCurrentStep('complete');
            setStatus('🏧 Please go to the nearest RoluATM and enter your PIN to collect cash!');
            onWithdrawal(); // Refresh balance
            setAmount('');
            
            // Reset after 10 seconds
            setTimeout(() => {
              setStatus('');
              setCurrentStep('input');
            }, 10000);
          }, 3000);
        } else {
          const error = await response.json();
          console.error('❌ Backend error:', error);
          setStatus(`❌ ${error.error || 'Failed to process withdrawal'}`);
          setTimeout(() => {
            setStatus('');
            setCurrentStep('input');
          }, 5000);
        }
      } else {
        console.error('❌ Transaction failed:', finalPayload);
        setStatus(`❌ Transaction failed: ${finalPayload.status}`);
        setTimeout(() => {
          setStatus('');
          setCurrentStep('input');
        }, 5000);
      }
    } catch (error) {
      console.error('❌ Withdrawal error:', error);
      setStatus(`❌ ${error instanceof Error ? error.message : 'Transaction failed'}`);
      setTimeout(() => {
        setStatus('');
        setCurrentStep('input');
      }, 5000);
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
          <div className="flex items-center justify-center space-x-2">
            {currentStep === 'transaction' && <span className="animate-spin">🔄</span>}
            {currentStep === 'monitoring' && <span className="animate-pulse">⛓️</span>}
            {currentStep === 'pin' && <span>🔑</span>}
            {currentStep === 'complete' && <span>🏧</span>}
            <p className="text-sm font-medium">{status}</p>
          </div>
        </div>
      )}
    </div>
  );
}; 