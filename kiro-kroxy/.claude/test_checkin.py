#!/usr/bin/env python3
"""
Comprehensive check-in feature test suite
Tests database operations, API endpoints, and edge cases
"""
import asyncio
import sys
from pathlib import Path
from datetime import date, timedelta

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kiro_proxy.portal import db as portal_db
from kiro_proxy.portal.auth import create_user_session, verify_user_session

async def test_db_operations():
    """Test database check-in operations"""
    print("\n" + "="*60)
    print("TEST 1: Database Operations")
    print("="*60)

    # Initialize DB
    await portal_db.init_db()

    # Create test user
    print("\n[1.1] Creating test user...")
    result = await portal_db.create_user("test_user_001", "password123", "Test User")
    print(f"  Result: {result}")
    assert result["ok"], "Failed to create user"

    # Get user
    users = await portal_db.get_all_users()
    test_user = next((u for u in users if u["student_id"] == "test_user_001"), None)
    assert test_user, "User not found"
    user_id = test_user["id"]
    print(f"  User ID: {user_id}")

    # Test 1.2: First check-in
    print("\n[1.2] Testing first check-in...")
    result = await portal_db.checkin_user(user_id)
    print(f"  Result: {result}")
    assert result["ok"], f"First check-in failed: {result}"
    assert result["tokens_awarded"] > 0, "No tokens awarded"
    print(f"  ✓ Tokens awarded: {result['tokens_awarded']}")
    print(f"  ✓ New total: {result['new_total']}")

    # Test 1.3: Duplicate check-in (same day)
    print("\n[1.3] Testing duplicate check-in (same day)...")
    result = await portal_db.checkin_user(user_id)
    print(f"  Result: {result}")
    assert not result["ok"], "Should reject duplicate check-in"
    assert result.get("already_checked_in"), "Should indicate already checked in"
    print(f"  ✓ Correctly rejected: {result['error']}")

    # Test 1.4: Check-in status
    print("\n[1.4] Testing check-in status query...")
    today = date.today().isoformat()
    result = await portal_db.get_checkin_status(user_id, today)
    print(f"  Result: {result}")
    assert result["checked_in"], "Should show checked in"
    assert result["tokens_awarded"] > 0, "Should have tokens"
    print(f"  ✓ Status: checked_in={result['checked_in']}, tokens={result['tokens_awarded']}")

    # Test 1.5: Check-in history
    print("\n[1.5] Testing check-in history...")
    result = await portal_db.get_checkin_history(user_id)
    print(f"  Result: {result}")
    assert len(result["history"]) > 0, "Should have history"
    assert result["total_count"] > 0, "Should have count"
    assert result["total_tokens_earned"] > 0, "Should have earned tokens"
    print(f"  ✓ History count: {result['total_count']}")
    print(f"  ✓ Total tokens earned: {result['total_tokens_earned']}")

    # Test 1.6: Config operations
    print("\n[1.6] Testing config get...")
    config = await portal_db.get_checkin_config()
    print(f"  Config: {config}")
    assert config["min_tokens"] > 0, "min_tokens should be positive"
    assert config["max_tokens"] >= config["min_tokens"], "max should be >= min"
    print(f"  ✓ Config: min={config['min_tokens']}, max={config['max_tokens']}")

    # Test 1.7: Config update
    print("\n[1.7] Testing config update...")
    result = await portal_db.update_checkin_config(2000, 8000, "test_admin")
    print(f"  Result: {result}")
    assert result["ok"], f"Config update failed: {result}"
    config = await portal_db.get_checkin_config()
    assert config["min_tokens"] == 2000, "min_tokens not updated"
    assert config["max_tokens"] == 8000, "max_tokens not updated"
    print(f"  ✓ Config updated: min={config['min_tokens']}, max={config['max_tokens']}")

    # Test 1.8: Config validation
    print("\n[1.8] Testing config validation...")
    result = await portal_db.update_checkin_config(0, 5000, "test_admin")
    print(f"  Result: {result}")
    assert not result["ok"], "Should reject min_tokens <= 0"
    print(f"  ✓ Correctly rejected invalid config: {result['error']}")

    result = await portal_db.update_checkin_config(5000, 2000, "test_admin")
    print(f"  Result: {result}")
    assert not result["ok"], "Should reject max < min"
    print(f"  ✓ Correctly rejected max < min: {result['error']}")

    # Test 1.9: Stats
    print("\n[1.9] Testing check-in stats...")
    result = await portal_db.get_checkin_stats(7)
    print(f"  Result: {result}")
    assert "stats" in result, "Should have stats"
    assert "summary" in result, "Should have summary"
    print(f"  ✓ Stats retrieved: {len(result['stats'])} days")

    print("\n✓ All database tests passed!")
    return user_id

async def test_session_structure():
    """Test session token structure"""
    print("\n" + "="*60)
    print("TEST 2: Session Structure")
    print("="*60)

    # Create session
    print("\n[2.1] Creating user session...")
    token = create_user_session(123, "test_sid")
    print(f"  Token: {token[:30]}...")

    # Verify session
    print("\n[2.2] Verifying session...")
    payload = verify_user_session(token)
    print(f"  Payload: {payload}")
    assert payload is not None, "Session verification failed"
    assert payload.get("uid") == 123, "uid mismatch"
    assert payload.get("sid") == "test_sid", "sid mismatch"
    assert payload.get("role") == "user", "role mismatch"
    print(f"  ✓ Session valid: uid={payload['uid']}, sid={payload['sid']}")

    print("\n✓ Session structure tests passed!")

async def test_concurrent_checkin():
    """Test concurrent check-in attempts"""
    print("\n" + "="*60)
    print("TEST 3: Concurrent Check-in")
    print("="*60)

    await portal_db.init_db()

    # Create test user
    print("\n[3.1] Creating test user for concurrent test...")
    result = await portal_db.create_user("concurrent_user", "password123")
    users = await portal_db.get_all_users()
    user = next((u for u in users if u["student_id"] == "concurrent_user"), None)
    user_id = user["id"]
    print(f"  User ID: {user_id}")

    # Simulate concurrent check-ins
    print("\n[3.2] Simulating concurrent check-in requests...")
    tasks = [portal_db.checkin_user(user_id) for _ in range(5)]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r.get("ok"))
    fail_count = sum(1 for r in results if not r.get("ok"))

    print(f"  Results: {success_count} success, {fail_count} failed")
    assert success_count == 1, f"Expected 1 success, got {success_count}"
    assert fail_count == 4, f"Expected 4 failures, got {fail_count}"
    print(f"  ✓ Correctly handled concurrent requests")

    print("\n✓ Concurrent check-in tests passed!")

async def test_edge_cases():
    """Test edge cases and boundary conditions"""
    print("\n" + "="*60)
    print("TEST 4: Edge Cases")
    print("="*60)

    await portal_db.init_db()

    # Test 4.1: Config with min == max
    print("\n[4.1] Testing config with min == max...")
    result = await portal_db.update_checkin_config(5000, 5000, "admin")
    print(f"  Result: {result}")
    assert result["ok"], "Should allow min == max"
    print(f"  ✓ Config accepted: min=max=5000")

    # Test 4.2: Very large config values
    print("\n[4.2] Testing very large config values...")
    result = await portal_db.update_checkin_config(1000000, 10000000, "admin")
    print(f"  Result: {result}")
    assert result["ok"], "Should allow large values"
    print(f"  ✓ Large config accepted: min=1M, max=10M")

    # Test 4.3: Check-in with large config
    print("\n[4.3] Testing check-in with large config...")
    result = await portal_db.create_user("edge_user", "password123")
    users = await portal_db.get_all_users()
    user = next((u for u in users if u["student_id"] == "edge_user"), None)
    result = await portal_db.checkin_user(user["id"])
    print(f"  Result: {result}")
    assert result["ok"], "Check-in should succeed"
    assert 1000000 <= result["tokens_awarded"] <= 10000000, "Tokens out of range"
    print(f"  ✓ Check-in succeeded with tokens: {result['tokens_awarded']}")

    print("\n✓ Edge case tests passed!")

async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("CHECK-IN FEATURE TEST SUITE")
    print("="*60)

    try:
        await test_session_structure()
        user_id = await test_db_operations()
        await test_concurrent_checkin()
        await test_edge_cases()

        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED!")
        print("="*60)
        return 0
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
