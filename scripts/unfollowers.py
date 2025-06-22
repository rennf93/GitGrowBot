#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from github import Github, GithubException
from collections import defaultdict

def main():
    # — Auth & client setup —
    token = os.getenv("PAT_TOKEN")  # Retrieve GitHub token from environment variables
    if not token:
        sys.exit("PAT_TOKEN environment variable is required")  # Exit if token is not found
    gh = Github(token)  # Initialize GitHub client
    me = gh.get_user()  # Get authenticated user

    # — Load whitelist as set for O(1) lookups —
    base_dir   = Path(__file__).parent.parent.resolve()  # Determine base directory of the repository
    white_path = base_dir / "config" / "whitelist.txt"  # Path to the whitelist configuration file
    whitelist = set()

    if white_path.exists():
        with white_path.open() as f:
            whitelist = {ln.strip().lower() for ln in f if ln.strip()}  # Load whitelist from file
        print(f"[INFO] Loaded {len(whitelist)} whitelisted users")
    else:
        print(f"[WARN] config/whitelist.txt not found, proceeding with empty whitelist")

    # — Fetch your followers and following with optimized data structures —
    try:
        print("[INFO] Fetching followers and following lists...")
        followers_set = {u.login.lower() for u in me.get_followers()}
        following_users = {u.login.lower(): u for u in me.get_following()}

        print(f"[INFO] Found {len(followers_set)} followers, following {len(following_users)} users")
    except GithubException as e:
        sys.exit(f"[ERROR] fetching follow lists: {e}")

    # — Compute who to unfollow using set operations for O(1) performance —
    me_login_lower = me.login.lower()

    # Users to unfollow: following but not followers, not whitelisted, not self
    to_unfollow_set = (
        set(following_users.keys()) -
        followers_set -
        whitelist -
        {me_login_lower}
    )

    print(f"[INFO] Found {len(to_unfollow_set)} users to unfollow")

    if not to_unfollow_set:
        print("[INFO] No users to unfollow")
        return

    # — Batch unfollow with error tracking —
    unfollowed = 0
    error_stats = defaultdict(int)

    # Convert to list for processing
    to_unfollow_list = list(to_unfollow_set)

    # Process in batches to avoid overwhelming the API
    batch_size = 20
    for i in range(0, len(to_unfollow_list), batch_size):
        batch = to_unfollow_list[i:i+batch_size]
        print(f"[BATCH] Unfollowing users {i+1}-{min(i+batch_size, len(to_unfollow_list))} of {len(to_unfollow_list)}")

        for login in batch:
            user = following_users[login]
            try:
                me.remove_from_following(user)
                unfollowed += 1
                print(f"[UNFOLLOWED] {login} ({unfollowed}/{len(to_unfollow_set)})")
            except GithubException as e:
                status = getattr(e, "status", None)
                if status == 429:  # Rate limit
                    print("[RATE_LIMIT] Hit rate limit, stopping unfollow process")
                    break
                else:
                    error_stats[f"error_{status}"] += 1
                    print(f"[ERROR] could not unfollow {login}: {e}")

        # Small delay between batches to be nice to the API
        if i + batch_size < len(to_unfollow_list):
            import time
            time.sleep(0.5)

    # — Summary —
    print(f"\n=== UNFOLLOW SUMMARY ===")
    print(f"Successfully unfollowed: {unfollowed}/{len(to_unfollow_set)} users")
    if error_stats:
        print(f"Errors encountered: {dict(error_stats)}")
    print(f"Remaining following: {len(following_users) - unfollowed}")

if __name__ == "__main__":
    main()
