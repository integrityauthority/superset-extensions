#!/usr/bin/env python3
"""Check chart and dashboard details. Run inside Superset container."""
import json
import sys
import urllib.request

BASE = "http://localhost:8088"

def login():
    payload = json.dumps({"username":"admin","password":"admin","provider":"db","refresh":True}).encode()
    req = urllib.request.Request(f"{BASE}/api/v1/security/login", data=payload, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["access_token"]

def api_get(token, path):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

token = login()

# Check chart 106
print("=== Chart 106 ===")
try:
    data = api_get(token, "/api/v1/chart/106")
    r = data.get("result", {})
    print(f"  Name: {r.get('slice_name')}")
    print(f"  Viz type: {r.get('viz_type')}")
    print(f"  Datasource: {r.get('datasource_id')} ({r.get('datasource_type')})")
    params = r.get("params")
    if params:
        p = json.loads(params) if isinstance(params, str) else params
        print(f"  x_axis: {p.get('x_axis')}")
        print(f"  metrics: {p.get('metrics')}")
        print(f"  groupby: {p.get('groupby')}")
except Exception as e:
    print(f"  Error: {e}")

# Check dataset for chart 106
print("\n=== Dataset for chart 106 ===")
try:
    data = api_get(token, "/api/v1/chart/106")
    ds_id = data["result"]["datasource_id"]
    ds = api_get(token, f"/api/v1/dataset/{ds_id}")
    r = ds.get("result", {})
    print(f"  Name: {r.get('table_name')}")
    print(f"  SQL: {(r.get('sql') or '')[:300]}")
    cols = r.get("columns", [])
    print(f"  Columns: {[c.get('column_name') for c in cols[:10]]}")
except Exception as e:
    print(f"  Error: {e}")

# Check dashboard 12
print("\n=== Dashboard 12 ===")
try:
    data = api_get(token, "/api/v1/dashboard/12")
    r = data.get("result", {})
    print(f"  Title: {r.get('dashboard_title')}")
    pos = r.get("position_json")
    if pos:
        p = json.loads(pos) if isinstance(pos, str) else pos
        charts = [k for k in p if k.startswith("CHART")]
        print(f"  Chart components: {charts}")
        for ck in charts:
            meta = p[ck].get("meta", {})
            print(f"    {ck}: chartId={meta.get('chartId')}, sliceName={meta.get('sliceName')}, width={meta.get('width')}, height={meta.get('height')}")
        rows = [k for k in p if k.startswith("ROW")]
        print(f"  Row components: {rows}")
except Exception as e:
    print(f"  Error: {e}")

print("\nDone.")
