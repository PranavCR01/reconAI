"""One-shot script — truncates rca_cache so all rows get re-analyzed with the current agent code."""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
if not url or not key:
    print("ERROR: SUPABASE_URL or SUPABASE_SERVICE_KEY not set", file=sys.stderr)
    sys.exit(1)

from supabase import create_client

client = create_client(url, key)
result = client.table("rca_cache").delete().neq("cache_key", "").execute()
deleted = len(result.data) if result.data else "?"
print(f"rca_cache cleared — {deleted} row(s) deleted")
