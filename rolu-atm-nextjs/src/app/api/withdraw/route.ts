import { NextRequest, NextResponse } from 'next/server';
import { verifyAuthToken } from '@/lib/auth';
import { getUserById, updateUserBalance, createTransaction, updateTransactionStatus } from '@/lib/database';

// Mock hardware integration for development
async function triggerCashDispense(amount: number, transactionId: string): Promise<{ success: boolean; message?: string }> {
  const isMockHardware = process.env.MOCK_HARDWARE === 'true';
  
  if (isMockHardware) {
    console.log('🧪 Mock hardware: simulating cash dispensing...');
    // Simulate dispensing delay
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Simulate 95% success rate
    const success = Math.random() > 0.05;
    
    if (success) {
      console.log('✅ Mock hardware: cash dispensed successfully');
      return { success: true };
    } else {
      console.log('❌ Mock hardware: dispensing failed');
      return { success: false, message: 'Hardware malfunction' };
    }
  }

  // Real hardware integration (for production)
  try {
    const kioskUrl = process.env.KIOSK_PI_URL;
    if (!kioskUrl) {
      throw new Error('KIOSK_PI_URL not configured');
    }

    console.log('🏧 Triggering real cash dispense...');
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout
    
    const response = await fetch(`${kioskUrl}/api/withdraw`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        amount_usd: amount,
        session_id: transactionId
      }),
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);

    if (response.ok) {
      console.log('✅ Real hardware: cash dispensed successfully');
      return { success: true };
    } else {
      const error = await response.json();
      console.error('❌ Real hardware: dispensing failed:', error);
      return { success: false, message: error.message || 'Hardware error' };
    }
  } catch (error) {
    console.error('❌ Hardware communication error:', error);
    return { success: false, message: 'Hardware unavailable' };
  }
}

export async function POST(request: NextRequest) {
  try {
    console.log('💰 Withdrawal request received');
    
    const token = request.cookies.get('auth-token')?.value;
    if (!token) {
      console.log('❌ No auth token found');
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const decoded = verifyAuthToken(token);
    const { amount } = await request.json();

    console.log('💵 Withdrawal amount:', amount);

    if (!amount || amount <= 0) {
      return NextResponse.json({ error: 'Invalid amount' }, { status: 400 });
    }

    if (amount > 500) {
      return NextResponse.json({ error: 'Amount exceeds daily limit of $500' }, { status: 400 });
    }

    const user = await getUserById(decoded.userId);
    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    if (user.balance < amount) {
      console.log('❌ Insufficient balance:', user.balance, 'requested:', amount);
      return NextResponse.json({ error: 'Insufficient balance' }, { status: 400 });
    }

    // Create transaction record
    const transaction = await createTransaction({
      user_id: user.id,
      amount: amount,
      type: 'withdrawal',
      status: 'processing'
    });

    console.log('📝 Transaction created:', transaction.id);

    // Update balance first (optimistic)
    const newBalance = user.balance - amount;
    await updateUserBalance(user.id, newBalance);

    console.log('💰 Balance updated:', user.balance, '→', newBalance);

    // Trigger hardware dispensing
    const dispenseResult = await triggerCashDispense(amount, transaction.id);

    if (dispenseResult.success) {
      // Mark transaction as completed
      await updateTransactionStatus(transaction.id, 'completed');
      
      console.log('🎉 Withdrawal successful:', transaction.id);
      
      return NextResponse.json({
        success: true,
        transaction_id: transaction.id,
        amount: amount,
        new_balance: newBalance,
        message: 'Cash dispensed successfully'
      });
    } else {
      // Refund balance if dispensing failed
      await updateUserBalance(user.id, user.balance);
      await updateTransactionStatus(transaction.id, 'failed');
      
      console.error('❌ Cash dispensing failed:', dispenseResult.message);
      
      return NextResponse.json(
        { error: dispenseResult.message || 'Cash dispensing failed' },
        { status: 500 }
      );
    }
  } catch (error) {
    console.error('❌ Withdrawal error:', error);
    return NextResponse.json(
      { error: 'Withdrawal processing failed' },
      { status: 500 }
    );
  }
} 