import { NextRequest, NextResponse } from 'next/server';
import { verifyAuthToken } from '@/lib/auth';
import { getUserById, createWithdrawal } from '@/lib/database';
import { monitorTransaction } from '@/lib/transaction-monitor';

export async function POST(request: NextRequest) {
  try {
    console.log('🚀 Withdrawal initiation request received');
    
    const token = request.cookies.get('auth-token')?.value;
    if (!token) {
      console.log('❌ No auth token found');
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const decoded = verifyAuthToken(token);
    const { transactionId, amount } = await request.json();

    if (!transactionId || !amount) {
      console.log('❌ Missing required fields');
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    const user = await getUserById(decoded.userId);
    if (!user) {
      console.log('❌ User not found');
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    if (!user.wallet_address) {
      console.log('❌ No wallet address found for user');
      return NextResponse.json({ error: 'No wallet connected' }, { status: 400 });
    }

    const walletAddress = user.wallet_address;

    console.log('📋 Withdrawal details:', {
      transactionId: transactionId,
      amount: amount,
      walletAddress: walletAddress?.slice(0, 8) + '...'
    });

    if (amount <= 0) {
      console.log('❌ Invalid amount');
      return NextResponse.json({ error: 'Invalid amount' }, { status: 400 });
    }

    if (amount > 500) {
      console.log('❌ Amount exceeds limit');
      return NextResponse.json({ error: 'Amount exceeds daily limit of $500' }, { status: 400 });
    }

    // Check sufficient balance (this is the converted USDC balance)
    if (user.balance < amount) {
      console.log('❌ Insufficient balance:', user.balance, 'requested:', amount);
      return NextResponse.json({ error: 'Insufficient balance' }, { status: 400 });
    }

    // Create withdrawal record
    const withdrawal = await createWithdrawal({
      transaction_id: transactionId,
      user_id: user.id,
      wallet_address: walletAddress,
      amount: amount,
      status: 'pending'
    });

    console.log('📝 Withdrawal record created:', withdrawal.id);

    // Start monitoring transaction in background
    // Note: In production, this should be handled by a background job queue
    setImmediate(() => {
      monitorTransaction(transactionId, withdrawal.id).catch(error => {
        console.error('❌ Transaction monitoring failed:', error);
      });
    });

    console.log('🔍 Transaction monitoring started');

    return NextResponse.json({
      success: true,
      withdrawalId: withdrawal.id,
      message: 'Withdrawal initiated. Transaction is being processed...'
    });

  } catch (error) {
    console.error('❌ Withdrawal initiation error:', error);
    return NextResponse.json({ error: 'Failed to initiate withdrawal' }, { status: 500 });
  }
} 