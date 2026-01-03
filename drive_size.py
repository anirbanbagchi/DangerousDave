#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Drive‑size explorer for Windows.

Author :  <your name>
Date   :  2025‑10‑27
"""

import os
import sys
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# --------------------------------------------------------------------------- #
# Helper – human readable size
def fmt_size(bytes_: int) -> str:
    """Return a string with the size in MB or GB (rounded to 2 decimals)."""
    if bytes_ < 1024 ** 2:          # less than 1 MiB → show KiB
        return f"{bytes_/1024:.2f} KiB"
    elif bytes_ < 1024 ** 3:         # 1–999 MiB → show MiB
        return f"{bytes_/(1024**2):.2f} MiB"
    else:                            # ≥ 1 GiB → show GiB
        return f"{bytes_/(1024**3):.2f} GiB"

# --------------------------------------------------------------------------- #
# Core – gather sizes in a single walk
def collect_sizes(root: Path) -> dict:
    """
    Walk the directory tree rooted at *root* and return a dictionary
    mapping each path (file or folder) to its cumulative size in bytes.
    """
    # We keep a separate map for folder totals, because os.walk gives us only file sizes.
    folder_sizes = defaultdict(int)

    # To avoid recursing into the same directory twice (symlinks), remember visited dirs
    seen_dirs = set()

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(dirpath)
        if current_path.is_symlink():
            continue

        # Mark this directory as visited
        real_dir = current_path.resolve()
        if real_dir in seen_dirs:
            dirnames[:] = []          # don't descend further
            continue
        seen_dirs.add(real_dir)

        total_size = 0
        for f in filenames:
            try:
                fp = current_path / f
                size = fp.stat().st_size
                total_size += size
            except (OSError, FileNotFoundError):
                # The file vanished or is inaccessible – skip it
                continue

        folder_sizes[current_path] = total_size

    # After the walk we have only file‑sizes per folder.  Now propagate up.
    # We sort paths by depth descending so that child folders are processed before parents.
    for path in sorted(folder_sizes.keys(), key=lambda p: -len(p.parts)):
        size = folder_sizes[path]
        parent = path.parent
        if parent != path:                # root has no parent inside the tree
            folder_sizes[parent] += size

    return dict(folder_sizes)

# --------------------------------------------------------------------------- #
# Pretty printing – sorted by size (descending)
def print_report(items, limit=None):
    """
    items : iterable of (Path, bytes) tuples.
    limit : optional int – how many top items to display.
    """
    for idx, (path, sz) in enumerate(sorted(items, key=lambda x: -x[1]), 1):
        if limit and idx > limit:
            break
        print(f"{fmt_size(sz):>10}   {str(path)}")

# --------------------------------------------------------------------------- #
def main():
    # --------------------------------------------------------------- #
    # Which drive / root to analyse? – first arg or default C:\
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        root = Path("/")          # change this if you want another drive

    if not root.is_dir():
        print(f"❌ {root} is not a directory.")
        sys.exit(1)

    print(f"[+] Scanning {root} …")
    sizes_dict = collect_sizes(root)
    print("[✓] Scan finished.\n")

    # Show the top 50 items (you can change this number or remove the limit)
    print_report(sizes_dict.items(), limit=50)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    main()