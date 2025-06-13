import { NextRequest, NextResponse } from 'next/server';
import { verifyAuthToken } from '@/lib/auth';
import { getWithdrawal } from '@/lib/database';

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    console.log('📋 Withdrawal status check for:', params.id);
    
    const token = request.cookies.get('auth-token')?.value;
    if (!token) {
      console.log('❌ No auth token found');
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const decoded = verifyAuthToken(token);
    const withdrawal = await getWithdrawal(params.id);

    if (!withdrawal) {
      console.log('❌ Withdrawal not found');
      return NextResponse.json({ error: 'Withdrawal not found' }, { status: 404 });
    }

    // Verify withdrawal belongs to authenticated user
    if (withdrawal.user_id !== decoded.userId) {
      console.log('❌ Withdrawal access denied');
      return NextResponse.json({ error: 'Access denied' }, { status: 403 });
    }

    console.log('✅ Withdrawal status:', withdrawal.status);

    return NextResponse.json({
      id: withdrawal.id,
      status: withdrawal.status,
      amount: withdrawal.amount,
      transaction_id: withdrawal.transaction_id,
      transaction_hash: withdrawal.transaction_hash,
      pin: withdrawal.status === 'pin_sent' ? withdrawal.pin : undefined,
      pin_expires_at: withdrawal.pin_expires_at,
      created_at: withdrawal.created_at,
      updated_at: withdrawal.updated_at
    });

  } catch (error) {
    console.error('❌ Withdrawal status error:', error);
    return NextResponse.json({ error: 'Failed to get withdrawal status' }, { status: 500 });
  }
} 