import { NextRequest, NextResponse } from 'next/server';
import { updateWithdrawal, updateUserBalance, getUserById } from '@/lib/database';

export async function POST(request: NextRequest) {
  try {
    console.log('🏧 Kiosk completion notification received');
    
    const { withdrawalId, kioskId, success, timestamp } = await request.json();

    console.log('📋 Completion details:', {
      withdrawalId,
      kioskId,
      success,
      timestamp
    });

    if (!withdrawalId || typeof success !== 'boolean') {
      console.log('❌ Missing required fields');
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    if (success) {
      // Mark withdrawal as completed and update user balance
      await updateWithdrawal(withdrawalId, {
        status: 'completed',
        kiosk_id: kioskId,
        dispensed_at: new Date()
      });

      console.log('✅ Withdrawal marked as completed');

      // TODO: In production, you might want to:
      // 1. Deduct the amount from user's actual wallet balance
      // 2. Record the transaction on blockchain
      // 3. Send confirmation notification to user
      // 4. Update analytics/reporting systems

    } else {
      // Mark withdrawal as failed
      await updateWithdrawal(withdrawalId, {
        status: 'failed',
        kiosk_id: kioskId
      });

      console.log('❌ Withdrawal marked as failed');

      // TODO: In production, you might want to:
      // 1. Refund the user if payment was already processed
      // 2. Send failure notification to user
      // 3. Log the failure for investigation
    }

    return NextResponse.json({
      success: true,
      message: 'Completion notification processed'
    });

  } catch (error) {
    console.error('❌ Kiosk completion processing error:', error);
    return NextResponse.json({ error: 'Failed to process completion' }, { status: 500 });
  }
} 