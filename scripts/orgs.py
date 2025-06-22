#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from github import Github, GithubException
from collections import defaultdict
import time

def process_organization_batch(gh, me, org_logins, batch_size=5):
    """
    Process organizations in batches for better error handling and performance
    Returns processing statistics
    """
    stats = defaultdict(int)

    for i in range(0, len(org_logins), batch_size):
        batch = org_logins[i:i+batch_size]
        print(f"[BATCH] Processing organizations {i+1}-{min(i+batch_size, len(org_logins))} of {len(org_logins)}")

        for login in batch:
            print(f"[INFO] processing '{login}'")

            # Fetch organization/user
            try:
                target = gh.get_user(login)
            except GithubException as e:
                print(f"[ERROR] cannot fetch '{login}': {e}")
                stats["fetch_errors"] += 1
                continue

            # Unfollow if currently following
            try:
                me.remove_from_following(target)
                print(f"[UNFOLLOWED] '{login}'")
                stats["unfollowed"] += 1
            except GithubException as e:
                status = getattr(e, "status", None)
                if status == 404:
                    print(f"[INFO] not following '{login}', skipping unfollow")
                    stats["not_following"] += 1
                elif status == 429:
                    print(f"[RATE_LIMIT] Hit rate limit during unfollow, waiting...")
                    time.sleep(60)
                    # Retry once after rate limit
                    try:
                        me.remove_from_following(target)
                        print(f"[UNFOLLOWED] '{login}' (after retry)")
                        stats["unfollowed"] += 1
                    except GithubException as retry_e:
                        print(f"[WARN] error unfollowing '{login}' after retry: {retry_e}")
                        stats["unfollow_errors"] += 1
                else:
                    print(f"[WARN] error unfollowing '{login}': {e}")
                    stats["unfollow_errors"] += 1

            # Follow again
            try:
                me.add_to_following(target)
                print(f"[FOLLOWED] '{login}'")
                stats["followed"] += 1
            except GithubException as e:
                status = getattr(e, "status", None)
                if status == 429:
                    print(f"[RATE_LIMIT] Hit rate limit during follow, waiting...")
                    time.sleep(60)
                    # Retry once after rate limit
                    try:
                        me.add_to_following(target)
                        print(f"[FOLLOWED] '{login}' (after retry)")
                        stats["followed"] += 1
                    except GithubException as retry_e:
                        print(f"[ERROR] error following '{login}' after retry: {retry_e}")
                        stats["follow_errors"] += 1
                else:
                    print(f"[ERROR] error following '{login}': {e}")
                    stats["follow_errors"] += 1

        # Small delay between batches to be nice to the API
        if i + batch_size < len(org_logins):
            time.sleep(1)

    return stats

def main():
    # — Auth & client setup —
    token = os.getenv("PAT_TOKEN")
    if not token:
        sys.exit("[FATAL] PAT_TOKEN environment variable is required")

    gh = Github(token)
    try:
        me = gh.get_user()
        print(f"[INFO] Authenticated as {me.login}")
    except GithubException as e:
        sys.exit(f"[FATAL] could not get authenticated user: {e}")

    # — Load target organizations —
    base_dir  = Path(__file__).parent.parent.resolve()
    orgs_path = base_dir / "config" / "organizations.txt"
    if not orgs_path.is_file():
        sys.exit(f"[FATAL] organizations file not found: {orgs_path}")

    # Stream read organizations for memory efficiency
    org_logins = []
    with orgs_path.open() as f:
        for line in f:
            login = line.strip()
            if login:
                org_logins.append(login)

    if not org_logins:
        sys.exit("[FATAL] No organizations found in organizations.txt")

    print(f"[INFO] loaded {len(org_logins)} organization(s) to process")

    # — Process organizations in batches —
    start_time = time.time()
    stats = process_organization_batch(gh, me, org_logins)
    end_time = time.time()

    # — Summary —
    print(f"\n=== ORGANIZATION PROCESSING SUMMARY ===")
    print(f"Processing time: {end_time - start_time:.2f} seconds")
    print(f"Organizations processed: {len(org_logins)}")
    print(f"Successfully unfollowed: {stats['unfollowed']}")
    print(f"Successfully followed: {stats['followed']}")
    print(f"Not following (skipped): {stats['not_following']}")

    if stats["fetch_errors"]:
        print(f"Fetch errors: {stats['fetch_errors']}")
    if stats["unfollow_errors"]:
        print(f"Unfollow errors: {stats['unfollow_errors']}")
    if stats["follow_errors"]:
        print(f"Follow errors: {stats['follow_errors']}")

    success_rate = (stats['followed'] / len(org_logins)) * 100 if org_logins else 0
    print(f"Success rate: {success_rate:.1f}%")

if __name__ == "__main__":
    main()