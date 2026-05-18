#!/usr/bin/env python3
"""Test leaderboard API"""
import asyncio
import sys
sys.path.insert(0, '/home/shiro/Projects/Kiro-Kroxy')

from kiro_proxy.portal import db as portal_db

async def test_leaderboard():
    print("Testing leaderboard API...")

    # Test get_today_checkin_leaderboard
    result = await portal_db.get_today_checkin_leaderboard(limit=10)

    print(f"\n✓ API Response:")
    print(f"  Date: {result.get('date')}")
    print(f"  Total Count: {result.get('total_count')}")
    print(f"  OK: {result.get('ok')}")

    if result.get('leaderboard'):
        print(f"\n✓ Leaderboard (Top 10):")
        for item in result['leaderboard'][:10]:
            rank_emoji = "🥇" if item['rank'] == 1 else "🥈" if item['rank'] == 2 else "🥉" if item['rank'] == 3 else "  "
            print(f"  {rank_emoji} #{item['rank']} - {item['student_id']} ({item.get('display_name', 'N/A')}): {item['tokens_awarded']:,} tokens")
    else:
        print("\n  No checkin records today")

    print("\n✓ Test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_leaderboard())
