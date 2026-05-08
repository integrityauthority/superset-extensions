#!/usr/bin/env python3
"""Execute chart SQL directly to verify data."""
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

queries = [
    ("Árbevétel", """
        SELECT TOP 5 YEAR(x.beszamolo_idoszakanak_vege) AS ev,
               SUM(x.beszamolo_tetelsoranak_osszege) AS arbevetel
        FROM dbo.x_ih_dwh_redflag_c_1 x
        WHERE x.adoszam = '23175415241'
          AND x.tetelsoranak_tipusa = 'BEVETEL'
        GROUP BY YEAR(x.beszamolo_idoszakanak_vege)
        ORDER BY ev
    """),
    ("Költségek", """
        SELECT TOP 5 r.beszamolo_idoszakanak_vege_ev AS ev,
               SUM(r.beszamolo_tetelsoranak_osszege) AS koltsegek
        FROM dbo.x_ih_dwh_redflag_c_1 r
        WHERE r.adoszam = '23175415241'
          AND r.tetelsoranak_tipusa = 'KOLTSEG'
        GROUP BY r.beszamolo_idoszakanak_vege_ev
        ORDER BY ev
    """),
    ("Profit", """
        SELECT TOP 5 beszamolo_idoszakanak_kezdete_ev AS ev,
               SUM(beszamolo_tetelsoranak_osszege) AS profit
        FROM dbo.x_ih_dwh_redflag_c_1
        WHERE adoszam = '23175415241'
          AND tetelsoranak_tipusa = 'EREDMENY'
        GROUP BY beszamolo_idoszakanak_kezdete_ev
        ORDER BY ev
    """),
    ("Distinct tipusok", """
        SELECT DISTINCT TOP 20 tetelsoranak_tipusa
        FROM dbo.x_ih_dwh_redflag_c_1
        WHERE adoszam = '23175415241'
    """),
]

for name, sql in queries:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if csrf:
        headers["X-CSRFToken"] = csrf
    if session:
        headers["Cookie"] = session

    payload = json.dumps({
        "database_id": 2,
        "sql": sql.strip(),
        "schema": "dbo",
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/ai_assistant/tools/execute_sql",
        data=payload,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            rows = data.get("data", [])
            print(f"\n{name}: {len(rows)} rows")
            for r in rows[:5]:
                print(f"  {r}")
    except Exception as e:
        # Fallback: use the chat endpoint with execute_sql
        print(f"\n{name}: Error with tools API - {e}")
        # Try direct SQL via Superset SQL Lab API
        try:
            sql_payload = json.dumps({
                "client_id": "test",
                "database_id": 2,
                "sql": sql.strip(),
                "schema": "dbo",
                "runAsync": False,
                "json": True,
                "expand_data": True,
            }).encode()
            req2 = urllib.request.Request(
                f"{BASE}/api/v1/sqllab/execute/",
                data=sql_payload,
                headers=headers,
            )
            with urllib.request.urlopen(req2, timeout=30) as resp2:
                result = json.loads(resp2.read())
                data_rows = result.get("data", [])
                print(f"  Via sqllab: {len(data_rows)} rows")
                for r in data_rows[:5]:
                    print(f"    {r}")
        except Exception as e2:
            print(f"  Also failed via sqllab: {e2}")
