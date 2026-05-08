#!/usr/bin/env python3
import json, urllib.request
payload = json.dumps({"username": "admin", "password": "admin", "provider": "db", "refresh": True}).encode()
req = urllib.request.Request("http://localhost:8088/api/v1/security/login", data=payload, headers={"Content-Type": "application/json"})
token = json.loads(urllib.request.urlopen(req, timeout=10).read())["access_token"]
req2 = urllib.request.Request("http://localhost:8088/api/v1/database/", headers={"Authorization": "Bearer " + token})
dbs = json.loads(urllib.request.urlopen(req2, timeout=10).read())["result"]
for d in dbs:
    print(f"id={d['id']}, name={d.get('database_name', '?')}, backend={d.get('backend', '?')}")
