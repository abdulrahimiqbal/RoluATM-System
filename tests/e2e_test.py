#!/usr/bin/env python3
"""
End-to-End Test Suite for RoluATM System

Tests the complete transaction flow:
1. Frontend loads and displays welcome screen
2. User selects amount
3. World ID verification (mocked)
4. Cloud API processes transaction
5. Kiosk dispenses coins
6. Transaction completes

Requires all services to be running:
- Cloud API (Vercel or local)
- Kiosk backend (Flask)
- Kiosk frontend (served)
"""

import asyncio
import aiohttp
import time
import json
import sys
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class TestConfig:
    """Test configuration"""
    cloud_api_url: str = "https://your-app.vercel.app"
    kiosk_api_url: str = "http://localhost:5000"
    frontend_url: str = "http://localhost:3000"
    timeout: int = 30


class RoluATME2ETest:
    """End-to-end test suite"""
    
    def __init__(self, config: TestConfig):
        self.config = config
        self.session_id = f"e2e_test_{int(time.time())}"
        self.results = []
    
    async def test_system_health(self) -> bool:
        """Test that all system components are healthy"""
        print("🔍 Testing system health...")
        
        async with aiohttp.ClientSession() as session:
            # Test cloud API
            try:
                async with session.get(f"{self.config.cloud_api_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"✅ Cloud API healthy: {data.get('status')}")
                    else:
                        print(f"❌ Cloud API unhealthy: {resp.status}")
                        return False
            except Exception as e:
                print(f"❌ Cloud API unreachable: {e}")
                return False
            
            # Test kiosk backend
            try:
                async with session.get(f"{self.config.kiosk_api_url}/api/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"✅ Kiosk backend healthy: {data.get('status', 'unknown')}")
                    else:
                        print(f"❌ Kiosk backend unhealthy: {resp.status}")
                        return False
            except Exception as e:
                print(f"❌ Kiosk backend unreachable: {e}")
                return False
            
            # Test frontend
            try:
                async with session.get(self.config.frontend_url) as resp:
                    if resp.status == 200:
                        print("✅ Frontend accessible")
                    else:
                        print(f"❌ Frontend inaccessible: {resp.status}")
                        return False
            except Exception as e:
                print(f"❌ Frontend unreachable: {e}")
                return False
        
        return True
    
    async def test_world_id_verification(self) -> bool:
        """Test World ID verification flow"""
        print("🌍 Testing World ID verification...")
        
        # Mock World ID payload
        mock_payload = {
            "merkle_root": "0x1234567890abcdef" * 4,
            "nullifier_hash": "0xabcdef1234567890" * 4,
            "proof": "0x" + "a" * 256,
            "verification_level": "orb"
        }
        
        request_data = {
            "session_id": self.session_id,
            "world_id_payload": mock_payload,
            "amount_usd": 5.0
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.config.cloud_api_url}/verify-worldid",
                    json=request_data,
                    timeout=self.config.timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            print(f"✅ World ID verification successful: {data.get('session_id')}")
                            return True
                        else:
                            print(f"❌ World ID verification failed: {data}")
                            return False
                    else:
                        error_text = await resp.text()
                        print(f"❌ World ID verification error {resp.status}: {error_text}")
                        return False
            except Exception as e:
                print(f"❌ World ID verification exception: {e}")
                return False
    
    async def test_withdrawal_process(self) -> bool:
        """Test coin withdrawal process"""
        print("🪙 Testing withdrawal process...")
        
        request_data = {
            "amount_usd": 5.0,
            "session_id": self.session_id
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                # Test kiosk withdrawal API
                async with session.post(
                    f"{self.config.kiosk_api_url}/api/withdraw",
                    json=request_data,
                    timeout=self.config.timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            print(f"✅ Withdrawal successful: {data.get('transaction_id')}")
                            return True
                        else:
                            print(f"❌ Withdrawal failed: {data}")
                            return False
                    else:
                        error_text = await resp.text()
                        print(f"❌ Withdrawal error {resp.status}: {error_text}")
                        return False
            except Exception as e:
                print(f"❌ Withdrawal exception: {e}")
                return False
    
    async def test_metrics_collection(self) -> bool:
        """Test metrics collection"""
        print("📊 Testing metrics collection...")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.config.kiosk_api_url}/metrics") as resp:
                    if resp.status == 200:
                        metrics_text = await resp.text()
                        
                        # Check for key metrics
                        required_metrics = [
                            'roluatm_requests_total',
                            'roluatm_hardware_status',
                            'roluatm_cloud_status'
                        ]
                        
                        missing_metrics = [m for m in required_metrics if m not in metrics_text]
                        
                        if not missing_metrics:
                            print("✅ All required metrics present")
                            return True
                        else:
                            print(f"❌ Missing metrics: {missing_metrics}")
                            return False
                    else:
                        print(f"❌ Metrics endpoint error: {resp.status}")
                        return False
            except Exception as e:
                print(f"❌ Metrics collection exception: {e}")
                return False
    
    async def test_error_handling(self) -> bool:
        """Test error handling scenarios"""
        print("🚨 Testing error handling...")
        
        test_cases = [
            {
                "name": "Invalid amount",
                "endpoint": f"{self.config.kiosk_api_url}/api/withdraw",
                "data": {"amount_usd": -1, "session_id": "test"},
                "expected_status": 400
            },
            {
                "name": "Missing session ID",
                "endpoint": f"{self.config.kiosk_api_url}/api/withdraw",
                "data": {"amount_usd": 5.0},
                "expected_status": 400
            },
            {
                "name": "Unknown endpoint",
                "endpoint": f"{self.config.kiosk_api_url}/api/unknown",
                "data": {},
                "expected_status": 404
            }
        ]
        
        async with aiohttp.ClientSession() as session:
            for case in test_cases:
                try:
                    if case["data"]:
                        async with session.post(case["endpoint"], json=case["data"]) as resp:
                            if resp.status == case["expected_status"]:
                                print(f"✅ {case['name']}: Correct error handling")
                            else:
                                print(f"❌ {case['name']}: Expected {case['expected_status']}, got {resp.status}")
                                return False
                    else:
                        async with session.get(case["endpoint"]) as resp:
                            if resp.status == case["expected_status"]:
                                print(f"✅ {case['name']}: Correct error handling")
                            else:
                                print(f"❌ {case['name']}: Expected {case['expected_status']}, got {resp.status}")
                                return False
                except Exception as e:
                    print(f"❌ {case['name']}: Exception {e}")
                    return False
        
        return True
    
    async def run_all_tests(self) -> bool:
        """Run complete E2E test suite"""
        print("🚀 Starting RoluATM E2E Test Suite")
        print("=" * 50)
        
        tests = [
            ("System Health", self.test_system_health),
            ("World ID Verification", self.test_world_id_verification),
            ("Withdrawal Process", self.test_withdrawal_process),
            ("Metrics Collection", self.test_metrics_collection),
            ("Error Handling", self.test_error_handling),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n📋 Running: {test_name}")
            try:
                result = await test_func()
                if result:
                    passed += 1
                    print(f"✅ {test_name}: PASSED")
                else:
                    print(f"❌ {test_name}: FAILED")
            except Exception as e:
                print(f"💥 {test_name}: CRASHED - {e}")
        
        print("\n" + "=" * 50)
        print(f"📊 Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED - System is ready for production!")
            return True
        else:
            print(f"⚠️  {total - passed} tests failed - Please fix issues before deployment")
            return False


async def main():
    """Main test runner"""
    if len(sys.argv) > 1:
        config = TestConfig(
            cloud_api_url=sys.argv[1] if len(sys.argv) > 1 else TestConfig.cloud_api_url,
            kiosk_api_url=sys.argv[2] if len(sys.argv) > 2 else TestConfig.kiosk_api_url,
            frontend_url=sys.argv[3] if len(sys.argv) > 3 else TestConfig.frontend_url
        )
    else:
        config = TestConfig()
    
    print(f"🔧 Test Configuration:")
    print(f"   Cloud API: {config.cloud_api_url}")
    print(f"   Kiosk API: {config.kiosk_api_url}")
    print(f"   Frontend:  {config.frontend_url}")
    
    tester = RoluATME2ETest(config)
    success = await tester.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main()) 