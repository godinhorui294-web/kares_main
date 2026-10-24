"""Download missing CVRPLIB E/F/M/P .vrp files, with retries."""
import os
import sys
import time
import urllib.request

BASE = "https://raw.githubusercontent.com/vidalt/CVRPLIB/main"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cvrplib_raw")

# Second round: the 5 remaining P files
MISSING = [
    ("P", "P-n40-k5.vrp"),
    ("P", "P-n45-k5.vrp"),
    ("P", "P-n50-k7.vrp"),
    ("P", "P-n50-k8.vrp"),
    ("P", "P-n50-k10.vrp"),
]


def download(url, dst, retries=4, timeout=45):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kares/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if len(data) < 50:
                raise IOError(f"too small: {len(data)}")
            with open(dst, "wb") as f:
                f.write(data)
            return len(data)
        except Exception as e:
            if i == retries - 1:
                return -1
            time.sleep(2 ** i)
    return -1


def main():
    ok = 0
    fail = 0
    for s, fn in MISSING:
        url = f"{BASE}/{s}/Instances/{fn}"
        dst = os.path.join(ROOT, s, fn)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst) and os.path.getsize(dst) > 50:
            print(f"SKIP {fn} (exists, {os.path.getsize(dst)} bytes)")
            ok += 1
            continue
        size = download(url, dst)
        if size > 0:
            print(f"OK   {fn} ({size} bytes)")
            ok += 1
        else:
            print(f"FAIL {fn}")
            fail += 1
    print(f"\n=== Done: ok={ok} fail={fail} ===")


if __name__ == "__main__":
    main()
