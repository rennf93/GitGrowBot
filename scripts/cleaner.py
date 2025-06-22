# cleaner.py
#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

def main():
    base_dir      = Path(__file__).parent.parent
    username_path = base_dir / "config" / "usernames.txt"
    log_dir       = base_dir / "logs" / "cleaner"
    log_dir.mkdir(parents=True, exist_ok=True)

    if not username_path.exists():
        sys.exit(f"Error: usernames file not found at {username_path}")

    # Use OrderedDict for efficient duplicate detection while preserving order
    seen = OrderedDict()
    duplicates = []

    # Stream processing to handle large files efficiently
    with username_path.open('r') as f:
        for line_num, line in enumerate(f, 1):
            name = line.strip()
            if not name:  # Skip empty lines
                continue

            lower_name = name.lower()
            if lower_name in seen:
                duplicates.append((line_num, name))
            else:
                seen[lower_name] = name

    if duplicates:
        # Log duplicates with line numbers for better debugging
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        dup_file = log_dir / f"duplicates-{ts}.txt"
        with dup_file.open("w") as f:
            f.write(f"Total duplicates found: {len(duplicates)}\n")
            f.write("Line | Username\n")
            f.write("-" * 20 + "\n")
            for line_num, name in duplicates:
                f.write(f"{line_num:4d} | {name}\n")

        print(f"[INFO] Logged {len(duplicates)} duplicates to {dup_file}")

        # Write unique usernames back - preserve original case from first occurrence
        unique_usernames = list(seen.values())
        username_path.write_text("\n".join(unique_usernames) + "\n")
        print(f"[INFO] Removed {len(duplicates)} duplicates; {len(unique_usernames)} remain.")
    else:
        print("[INFO] No duplicates found.")

if __name__ == "__main__":
    main()
