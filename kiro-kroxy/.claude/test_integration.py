#!/usr/bin/env python3
"""
Integration test for check-in API endpoints
Tests the fixed session token handling
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from kiro_proxy.portal import db as portal_db
from kiro_proxy.portal.auth import create_user_session, verify_user_session

async def test_session_token_fix():
    """Test that session tokens work correctly with check-in endpoints"""
    print("\n" + "="*60)
    print("INTEGRATION TEST: Session Token Fix")
    print("="*60)

    await portal_db.init_db()

    # Create test user
    print("\n[1] Creating test user...")
    result = await portal_db.create_user("integration_test_user", "password123")
    users = await portal_db.get_all_users()
    user = next((u for u in users if u["student_id"] == "integration_test_user"), None)
    user_id = user["id"]
    print(f"  User ID: {user_id}")

    # Create session token
    print("\n[2] Creating session token...")
    token = create_user_session(user_id, "integration_test_user")
    print(f"  Token: {token[:30]}...")

    # Verify token
    print("\n[3] Verifying token structure...")
    payload = verify_user_session(token)
    print(f"  Payload: {payload}")
    assert payload["uid"] == user_id, "uid mismatch"
    print(f"  ✓ Token has uid={payload['uid']}")

    # Simulate what the endpoint does
    print("\n[4] Simulating endpoint behavior...")
    user_from_token = payload
    print(f"  user_from_token['uid'] = {user_from_token['uid']}")

    # Test check-in with the token's uid
    print("\n[5] Testing check-in with token uid...")
    result = await portal_db.checkin_user(user_from_token["uid"])
    print(f"  Result: {result}")
    assert result["ok"], f"Check-in failed: {result}"
    print(f"  ✓ Check-in succeeded with tokens: {result['tokens_awarded']}")

    # Test status with token uid
    print("\n[6] Testing status with token uid...")
    from datetime import date
    today = date.today().isoformat()
    result = await portal_db.get_checkin_status(user_from_token["uid"], today)
    print(f"  Result: {result}")
    assert result["checked_in"], "Should be checked in"
    print(f"  ✓ Status check succeeded")

    # Test history with token uid
    print("\n[7] Testing history with token uid...")
    result = await portal_db.get_checkin_history(user_from_token["uid"])
    print(f"  Result: {result}")
    assert len(result["history"]) > 0, "Should have history"
    print(f"  ✓ History retrieved: {result['total_count']} check-ins")

    print("\n✓ All integration tests passed!")
    return 0

async def main():
    try:
        return await test_session_token_fix()
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
