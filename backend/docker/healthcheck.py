#!/usr/bin/env python3
"""Container healthcheck without curl: exits 0 when the URL answers 2xx."""

import sys
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/readyz"
try:
    with urllib.request.urlopen(url, timeout=4) as r:
        sys.exit(0 if 200 <= r.status < 300 else 1)
except Exception:
    sys.exit(1)
