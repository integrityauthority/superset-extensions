#!/usr/bin/env python3
"""Check chart data quality after E2E test."""
import json
import urllib.request

BASE = "http://localhost:8088"

# Login
payload = json.dumps({"username": "admin", "password": "admin", "provider": "db", "refresh": True}).encode()
req = urllib.request.Request(f"{BASE}/api/v1/security/login", data=payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=10) as resp:
    token = json.loads(resp.read())["access_token"]

# Get CSRF
req = urllib.request.Request(f"{BASE}/api/v1/security/csrf_token/", headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(req, timeout=10) as resp:
    csrf = json.loads(resp.read()).get("result")
    cookies = resp.headers.get_all("Set-Cookie") or []
    session = ""
    for c in cookies:
        if "session=" in c:
            session = c.split(";")[0]

# Check charts 111, 112, 113
for chart_id in [111, 112, 113]:
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/chart/{chart_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            result = data.get("result", {})
            params = json.loads(result.get("params", "{}"))
            ds_id = result.get("datasource_id")
            print(f"\nChart {chart_id}: {result.get('slice_name')}")
            print(f"  viz_type: {result.get('viz_type')}")
            print(f"  datasource_id: {ds_id}")

        # Get dataset SQL
        if ds_id:
            req2 = urllib.request.Request(
                f"{BASE}/api/v1/dataset/{ds_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                ds_data = json.loads(resp2.read())
                ds_result = ds_data.get("result", {})
                sql = ds_result.get("sql", "(none)")
                print(f"  Dataset: {ds_result.get('table_name', '?')}")
                print(f"  SQL:\n    {sql[:500]}")

        # Try to get chart data
        chart_data_payload = json.dumps({
            "datasource": {"id": ds_id, "type": "table"},
            "force": True,
            "queries": [{
                "columns": [],
                "metrics": [],
                "row_limit": 5,
            }],
            "result_format": "json",
            "result_type": "results",
        }).encode()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if csrf:
            headers["X-CSRFToken"] = csrf
        if session:
            headers["Cookie"] = session

        req3 = urllib.request.Request(
            f"{BASE}/api/v1/chart/data",
            data=chart_data_payload,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req3, timeout=30) as resp3:
                chart_data = json.loads(resp3.read())
                for qr in chart_data.get("result", []):
                    row_count = qr.get("rowcount", 0)
                    data_rows = qr.get("data", [])
                    print(f"  Data rows: {row_count}")
                    for row in data_rows[:3]:
                        print(f"    {row}")
        except Exception as e:
            print(f"  Data fetch error: {e}")

    except Exception as e:
        print(f"\nChart {chart_id}: ERROR - {e}")
