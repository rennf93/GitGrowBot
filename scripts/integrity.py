#!/usr/bin/env python3
# integrity.py
# Optimized batch integrity check with concurrent processing
# This script verifies the integrity of GitHub usernames listed in config/usernames.txt for the bot's operation.
# It checks that each username exists on GitHub using concurrent processing for better performance.

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from github import Github, GithubException
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import time

def check_user_exists(gh, username):
    """Check if a single user exists on GitHub"""
    try:
        gh.get_user(username)
        return username, "OK"
    except GithubException as e:
        if e.status == 404:
            return username, "MISSING"
        else:
            return username, f"ERROR({e.status})"

def batch_check_users(gh, usernames, max_workers=5):
    """
    Check users in parallel using ThreadPoolExecutor
    Returns dict of {username: status}
    """
    results = {}

    # Process in smaller batches to respect rate limits
    batch_size = 50
    for i in range(0, len(usernames), batch_size):
        batch = usernames[i:i+batch_size]
        print(f"[BATCH] Checking users {i+1}-{min(i+batch_size, len(usernames))} of {len(usernames)}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_user = {
                executor.submit(check_user_exists, gh, username): username
                for username in batch
            }

            # Collect results
            for future in as_completed(future_to_user):
                username, status = future.result()
                results[username] = status

        # Small delay between batches to be nice to the API
        if i + batch_size < len(usernames):
            time.sleep(1)

    return results

def main():
    load_dotenv()
    token = os.getenv("PAT_TOKEN")
    if not token:
        sys.exit("Error: PAT_TOKEN environment variable is required")
    gh = Github(token)

    base_dir      = Path(__file__).parent.parent
    username_path = base_dir / "config" / "usernames.txt"
    log_dir       = base_dir / "logs" / "integrity"
    log_dir.mkdir(parents=True, exist_ok=True)

    if not username_path.exists():
        sys.exit(f"Error: usernames file not found at {username_path}")

    # Stream read usernames to handle large files efficiently
    usernames = []
    with username_path.open('r') as f:
        for line in f:
            name = line.strip()
            if name:
                usernames.append(name)

    total = len(usernames)
    if total == 0:
        sys.exit("Error: usernames.txt is empty")

    # Prompt user for batch range, showing valid bounds
    try:
        start = int(input(f"Enter START line number (1–{total}): ").strip())
        end   = int(input(f"Enter   END   line number ({start}–{total}): ").strip())
    except ValueError:
        sys.exit("Invalid input. Please enter integer values for start and end.")

    if not (1 <= start <= end <= total):
        sys.exit(f"Range out of bounds: file has {total} lines, but you requested {start}-{end}.")

    batch = usernames[start-1:end]
    print(f"[INFO] Processing {len(batch)} usernames with optimized concurrent checking...")

    # Check existence with concurrent processing
    start_time = time.time()
    results = batch_check_users(gh, batch)
    end_time = time.time()

    print(f"[INFO] Completed checks in {end_time - start_time:.2f} seconds")

    # Organize results
    status_counts = defaultdict(int)
    missing_users = []

    batch_results = []  # (line_no, username, status)
    for idx, name in enumerate(batch, start=start):
        status = results[name]
        batch_results.append((idx, name, status))
        status_counts[status] += 1

        if status == "MISSING":
            missing_users.append(name)

    # Write run log with performance metrics
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run_file = log_dir / f"run-{ts}-{start}-{end}.txt"
    with run_file.open("w") as f:
        f.write(f"Run timestamp: {ts} (UTC)\n")
        f.write(f"Lines processed: {start} to {end} (of {total})\n")
        f.write(f"Processing time: {end_time - start_time:.2f} seconds\n")
        f.write(f"Rate: {len(batch) / (end_time - start_time):.2f} users/second\n\n")
        f.write("Status Summary:\n")
        for status, count in status_counts.items():
            f.write(f"  {status}: {count}\n")
        f.write("\nDetailed Results:\n")
        for idx, name, status in batch_results:
            f.write(f"{idx}: {name} – {status}\n")
        if batch_results:
            last_idx, last_name, _ = batch_results[-1]
            f.write(f"\nLast processed: {last_idx}: {last_name}\n")

    print(f"[INFO] Run log → {run_file}")
    print(f"[STATS] OK: {status_counts['OK']}, Missing: {status_counts['MISSING']}, Errors: {sum(v for k, v in status_counts.items() if k.startswith('ERROR'))}")

    # If any missing, log and remove them
    if missing_users:
        miss_file = log_dir / f"missing-{ts}-{start}-{end}.txt"
        with miss_file.open("w") as f:
            f.write("\n".join(missing_users) + "\n")
        print(f"[INFO] Logged {len(missing_users)} missing → {miss_file}")

        # Use set for O(1) lookup when removing missing users
        missing_set = set(missing_users)
        remaining = [u for u in usernames if u not in missing_set]
        username_path.write_text("\n".join(remaining) + "\n")
        print(f"[INFO] Removed {len(missing_users)} missing entries; {len(remaining)} remain.")
    else:
        print("[INFO] No missing usernames in this batch.")

if __name__ == "__main__":
    main()
