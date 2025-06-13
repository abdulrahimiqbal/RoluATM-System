import { NextRequest, NextResponse } from 'next/server';
import { verifyWorldIdProof } from '@/lib/worldid';
import { createUser, getUserByNullifier } from '@/lib/database';
import { createJWTToken } from '@/lib/auth';

export async function POST(request: NextRequest) {
  try {
    console.log('🔐 Authentication request received');
    
    const { worldIdProof, action } = await request.json();

    if (!worldIdProof || !action) {
      console.error('❌ Missing worldIdProof or action');
      return NextResponse.json(
        { error: 'World ID proof and action are required' },
        { status: 400 }
      );
    }

    console.log('📝 Verifying World ID proof for action:', action);
    
    // Verify the World ID proof
    const isValid = await verifyWorldIdProof(worldIdProof, action);
    if (!isValid) {
      console.error('❌ World ID verification failed');
      return NextResponse.json(
        { error: 'World ID verification failed' },
        { status: 401 }
      );
    }

    const nullifierHash = worldIdProof.nullifier_hash;
    console.log('🔍 Looking up user with nullifier:', nullifierHash.slice(0, 8) + '...');
    
    // Get or create user based on nullifier hash
    let user = await getUserByNullifier(nullifierHash);
    if (!user) {
      console.log('👤 Creating new user...');
      user = await createUser({
        nullifier_hash: nullifierHash,
        verification_level: worldIdProof.verification_level,
        initial_balance: 100.00 // Starting balance in USD
      });
    } else {
      console.log('✅ Existing user found:', user.id);
    }

    // Create JWT token
    const token = createJWTToken(user.id, nullifierHash);

    // Create response with user data
    const response = NextResponse.json({ 
      success: true, 
      user: {
        id: user.id,
        verification_level: user.verification_level,
        nullifier_hash: user.nullifier_hash
      }
    });

    // Set HTTP-only cookie
    response.cookies.set('auth-token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      maxAge: 24 * 60 * 60, // 24 hours
      path: '/',
      sameSite: 'lax'
    });

    console.log('🎉 Authentication successful for user:', user.id);
    return response;
  } catch (error) {
    console.error('❌ Authentication error:', error);
    return NextResponse.json(
      { error: 'Authentication failed' },
      { status: 500 }
    );
  }
} 