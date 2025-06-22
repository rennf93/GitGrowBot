#!/usr/bin/env python3
import os
import sys
import random
import time
from pathlib import Path
from github import Github, GithubException
from datetime import datetime, timedelta, timezone
from collections import defaultdict

def check_user_activity_fast(user, activity_days=3):
    """
    Optimized activity checker - checks repos first (faster API call)
    Returns (is_active, last_activity_type, last_activity_date)
    """
    try:
        # Check public repositories first - most efficient
        repos = user.get_repos(type='public', sort='updated')
        try:
            recent_repo = next(iter(repos))
            if recent_repo.updated_at and recent_repo.updated_at > datetime.now(timezone.utc) - timedelta(days=activity_days):
                return True, "repository_update", recent_repo.updated_at
        except StopIteration:
            pass

        # Only check events if repo check fails - more expensive
        events = user.get_events()
        try:
            last_event = next(iter(events))
            if last_event.created_at > datetime.now(timezone.utc) - timedelta(days=activity_days):
                return True, "event", last_event.created_at
        except StopIteration:
            pass

        return False, "none", None

    except GithubException as e:
        # If we can't check activity, assume inactive to be conservative
        return False, "error", None

def batch_process_users_optimized(gh, usernames, batch_size=20):
    """
    Optimized batch processing with better error handling and fewer API calls
    Returns dict of {username: user_object or None}
    """
    results = {}
    failed_users = set()

    for i in range(0, len(usernames), batch_size):
        batch = usernames[i:i+batch_size]
        print(f"[BATCH] Processing users {i+1}-{min(i+batch_size, len(usernames))} of {len(usernames)}")

        for username in batch:
            if username in failed_users:
                results[username] = None
                continue

            try:
                user = gh.get_user(username)
                results[username] = user
            except GithubException as e:
                status = getattr(e, "status", None)
                if status == 404:
                    failed_users.add(username)
                    results[username] = None
                elif status == 403:
                    print(f"[RATE_LIMIT] Hit rate limit, waiting 60 seconds...")
                    time.sleep(60)
                    # Single retry after rate limit
                    try:
                        user = gh.get_user(username)
                        results[username] = user
                    except GithubException:
                        failed_users.add(username)
                        results[username] = None
                else:
                    failed_users.add(username)
                    results[username] = None

        # Minimal delay between batches
        if i + batch_size < len(usernames):
            time.sleep(0.5)

    return results

def main():
    # — Auth & client setup —
    token = os.getenv("PAT_TOKEN")
    if not token:
        sys.exit("PAT_TOKEN environment variable is required")

    gh = Github(token, per_page=100)
    me = gh.get_user()

    # — Determine repo root & config paths —
    base_dir = Path(__file__).parent.parent.resolve()
    user_path = base_dir / "config" / "usernames.txt"
    white_path = base_dir / "config" / "whitelist.txt"
    per_run = int(os.getenv("FOLLOWERS_PER_RUN", 50))
    activity_days = int(os.getenv("ACTIVITY_DAYS", 3))

    print(f"[INFO] Starting GitGrowBot optimized run - target: {per_run} new follows")
    print(f"[INFO] Activity filter: {activity_days} days")

    # — Load whitelist as set for O(1) lookups —
    whitelist = set()
    if white_path.exists():
        with white_path.open() as f:
            whitelist = {ln.strip().lower() for ln in f if ln.strip()}
        print(f"[INFO] Loaded {len(whitelist)} whitelisted users")
    else:
        print("[WARN] config/whitelist.txt not found, proceeding with empty whitelist")

    # — Load candidate usernames —
    if not user_path.exists():
        sys.exit(f"Username file not found: {user_path}")

    with user_path.open() as f:
        all_candidates = [ln.strip() for ln in f if ln.strip()]

    print(f"[INFO] Loaded {len(all_candidates)} candidate usernames")

    # — Fetch current following list once - convert to set for O(1) lookups —
    try:
        following_set = {u.login.lower() for u in me.get_following()}
        print(f"[INFO] Currently following {len(following_set)} users")
    except GithubException as e:
        sys.exit(f"[ERROR] fetching following list: {e}")

    # — Optimized candidate selection —
    # Use set operations for faster filtering
    me_login_lower = me.login.lower()

    # Pre-filter candidates using set operations
    candidate_set = set(all_candidates)
    # Remove already filtered users
    candidate_set.discard(me.login)  # Remove self
    candidate_set -= {c for c in candidate_set if c.lower() in whitelist}  # Remove whitelisted
    candidate_set -= {c for c in candidate_set if c.lower() in following_set}  # Remove already following

    # Convert back to list for sampling
    filtered_candidates = list(candidate_set)

    # Smart sampling - prioritize recent additions
    sample_size = min(per_run * 2, len(filtered_candidates))
    if len(filtered_candidates) > 1000:
        recent_candidates = filtered_candidates[-800:]  # Recent 800
        older_candidates = filtered_candidates[:-800]   # Older ones

        recent_sample = random.sample(recent_candidates, min(int(sample_size * 0.7), len(recent_candidates)))
        older_sample = random.sample(older_candidates, min(sample_size - len(recent_sample), len(older_candidates)))
        candidates = recent_sample + older_sample
    else:
        candidates = random.sample(filtered_candidates, sample_size)

    random.shuffle(candidates)
    print(f"[INFO] Selected {len(candidates)} candidates for processing")

    # — Batch process users for existence and activity check —
    candidate_users = batch_process_users_optimized(gh, candidates)

    # — Follow users with optimized activity filtering —
    new_followed = 0
    activity_stats = defaultdict(int)

    for login, user in candidate_users.items():
        if new_followed >= per_run:
            break

        if user is None:
            continue

        # Fast activity check
        is_active, activity_type, last_activity = check_user_activity_fast(user, activity_days)

        if not is_active:
            activity_stats[f"inactive_{activity_type}"] += 1
            continue

        activity_stats["active"] += 1

        # Attempt follow
        try:
            me.add_to_following(user)
            new_followed += 1
            print(f"[FOLLOWED] {login} ({new_followed}/{per_run}) - active: {activity_type}")
        except GithubException as e:
            status = getattr(e, "status", None)
            if status == 403:
                print(f"[PRIVATE] cannot follow {login}")
            elif status == 429:
                print("[RATE_LIMIT] Hit rate limit during follow, stopping")
                break
            else:
                print(f"[ERROR] follow {login}: {e}")

    print(f"\n[SUMMARY] Follow phase: {new_followed}/{per_run} followed")
    print(f"Activity stats: {dict(activity_stats)}")

    # — Optimized follow-back phase —
    try:
        followers_set = {u.login.lower() for u in me.get_followers()}
        print(f"[INFO] Found {len(followers_set)} followers")
    except GithubException as e:
        print(f"[ERROR] fetching followers list: {e}")
        return

    # Find follow-back candidates using set operations
    follow_back_candidates = followers_set - following_set - whitelist - {me_login_lower}

    print(f"[INFO] Found {len(follow_back_candidates)} follow-back candidates")

    # Process follow-backs
    back_count = 0
    for login in list(follow_back_candidates)[:20]:  # Limit follow-backs to avoid rate limiting
        try:
            user = gh.get_user(login)
            me.add_to_following(user)
            back_count += 1
            print(f"[FOLLOW-BACKED] {login}")
        except GithubException as e:
            status = getattr(e, "status", None)
            if status == 403:
                print(f"[PRIVATE] cannot follow-back {login}")
            elif status == 429:
                print("[RATE_LIMIT] Hit rate limit during follow-back, stopping")
                break
            else:
                print(f"[ERROR] follow-back {login}: {e}")

    print(f"\n=== OPTIMIZED FINAL SUMMARY ===")
    print(f"New follows: {new_followed}/{per_run}")
    print(f"Follow-backs: {back_count}")
    print(f"Total actions: {new_followed + back_count}")

if __name__ == "__main__":
    main()