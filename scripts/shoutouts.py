#!/usr/bin/env python3

import os
import json
from pathlib import Path
import requests
from collections import defaultdict
import time

STATE_FILE = Path(".github/state/stars.json")
OUTPUT_DIR = Path(".github/state")
WELCOME_FILE = OUTPUT_DIR / "welcome_comments.md"
FAREWELL_FILE = OUTPUT_DIR / "farewell_comments.md"
REPO = os.environ["GITHUB_REPOSITORY"]
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"GitGrowBot-{REPO}"
}

def get_stargazers_optimized():
    """
    Optimized stargazer fetching with better pagination and error handling
    Returns set of stargazer logins
    """
    stargazers = set()
    page = 1
    empty_responses = 0
    max_empty_responses = 3

    print("[INFO] Fetching stargazers...")
    start_time = time.time()

    while empty_responses < max_empty_responses:
        url = f"https://api.github.com/repos/{REPO}/stargazers"
        params = {"per_page": 100, "page": page}

        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[ERROR] API request failed on page {page}: {e}")
            break
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to decode JSON on page {page}: {e}")
            break

        if not isinstance(data, list) or not data:
            empty_responses += 1
            if not data and page == 1:
                print("[WARN] No stargazers found in repository")
            break

        # Extract usernames efficiently
        page_stargazers = {user["login"] for user in data if "login" in user}
        stargazers.update(page_stargazers)

        print(f"[PAGE {page}] Found {len(page_stargazers)} stargazers (total: {len(stargazers)})")

        # Check if we got fewer results than requested (last page)
        if len(data) < 100:
            break

        page += 1

        # Rate limiting - be nice to the API
        time.sleep(0.1)

    end_time = time.time()
    print(f"[INFO] Stargazer fetch completed in {end_time - start_time:.2f} seconds")
    print(f"[INFO] Found {len(stargazers)} total stargazers")

    return stargazers

def load_previous_state():
    """Load previous stargazer state efficiently"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                previous_list = json.load(f)
                return set(previous_list) if isinstance(previous_list, list) else set()
        except (json.JSONDecodeError, IOError) as e:
            print(f"[WARN] Could not load previous state: {e}")
            return set()
    return set()

def save_state(stargazers_set):
    """Save current state efficiently"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(sorted(stargazers_set), f, indent=2, separators=(',', ': '))
        print(f"[INFO] State saved with {len(stargazers_set)} stargazers")
    except IOError as e:
        print(f"[ERROR] Could not save state: {e}")

def generate_messages(new_stars, lost_stars):
    """Generate welcome and farewell messages efficiently"""
    stats = {"new": len(new_stars), "lost": len(lost_stars)}

    # Generate welcome message
    if new_stars:
        # Sort for consistent output
        sorted_new = sorted(new_stars)
        welcome_msg = (
            "# 🌟 **New stargazers detected!**\n"
            f"**{len(sorted_new)} new star{'s' if len(sorted_new) != 1 else ''}!**\n\n"
            "Welcome aboard and thank you for your interest: "
            + ", ".join(f"@{u}" for u in sorted_new)
            + "\n\n"
            "You've been added to the active users follow list `(usernames.txt)`. Glad to have you here! 😸\n\n"
            "> _L'amitié naît d'une mutuelle estime et s'entretient moins par les bienfaits que par l'honnêteté._\n"
            "> — **Étienne de La Boétie**"
        )
    else:
        welcome_msg = "No new stargazers detected this run.\n"

    # Generate farewell message
    if lost_stars:
        sorted_lost = sorted(lost_stars)
        farewell_msg = (
            "# 💔 **Oh no, stars fading away...**\n"
            f"**{len(sorted_lost)} star{'s' if len(sorted_lost) != 1 else ''} lost.**\n\n"
            + ", ".join(f"@{u}" for u in sorted_lost)
            + " unstarred GitGrowBot.\n\n"
            "Your support was appreciated. We've removed you from the users follow list, but you're welcome back anytime.\n\n"
            "> _Rien ne se perd, rien ne se crée, tout se transforme._\n"
            "> — **Antoine Lavoisier**"
        )
    else:
        farewell_msg = "No stargazers lost this run.\n"

    return welcome_msg, farewell_msg, stats

def write_output_files(welcome_msg, farewell_msg):
    """Write output files efficiently"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(WELCOME_FILE, "w") as f:
            f.write(welcome_msg)
        with open(FAREWELL_FILE, "w") as f:
            f.write(farewell_msg)
        print(f"[INFO] Output files written to {OUTPUT_DIR}")
    except IOError as e:
        print(f"[ERROR] Could not write output files: {e}")

def main():
    """Main execution with optimized flow"""
    print(f"[INFO] Starting stargazer analysis for {REPO}")
    start_time = time.time()

    # Load previous state
    previous_stars = load_previous_state()
    print(f"[INFO] Previous state: {len(previous_stars)} stargazers")

    # Fetch current stargazers
    current_stars = get_stargazers_optimized()

    # Detect changes using set operations
    new_stars = current_stars - previous_stars
    lost_stars = previous_stars - current_stars

    print(f"[ANALYSIS] New: {len(new_stars)}, Lost: {len(lost_stars)}, Total: {len(current_stars)}")

    # Generate messages
    welcome_msg, farewell_msg, stats = generate_messages(new_stars, lost_stars)

    # Write output files
    write_output_files(welcome_msg, farewell_msg)

    # Save new state
    save_state(current_stars)

    # Summary
    end_time = time.time()
    print(f"\n=== SHOUTOUTS SUMMARY ===")
    print(f"Execution time: {end_time - start_time:.2f} seconds")
    print(f"New stars: {stats['new']}")
    print(f"Lost stars: {stats['lost']}")
    print(f"Current total: {len(current_stars)}")

    if new_stars:
        print(f"New stargazers: {', '.join(sorted(new_stars))}")
    if lost_stars:
        print(f"Lost stargazers: {', '.join(sorted(lost_stars))}")

if __name__ == "__main__":
    main()