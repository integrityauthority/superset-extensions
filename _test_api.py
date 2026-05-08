#!/usr/bin/env python3
"""
End-to-end test for Vambery AI Agent via Superset REST API.
Run inside the Superset container:
  python3 /tmp/_test_api.py
"""

import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8088"


def login():
    """Get JWT access token."""
    payload = json.dumps({
        "username": "admin",
        "password": "admin",
        "provider": "db",
        "refresh": True,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/security/login",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    token = data.get("access_token")
    if not token:
        print(f"ERROR: No access token. Response: {data}")
        sys.exit(1)
    print(f"OK: Got JWT token ({len(token)} chars)")
    return token


def get_csrf(token):
    """Get CSRF token and session cookie."""
    req = urllib.request.Request(
        f"{BASE}/api/v1/security/csrf_token/",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            cookies = resp.headers.get_all("Set-Cookie") or []
            session_cookie = ""
            for c in cookies:
                if "session=" in c:
                    session_cookie = c.split(";")[0]
                    break
            csrf = data.get("result")
            print(f"OK: CSRF token ({len(csrf or '')} chars), session cookie: {'yes' if session_cookie else 'no'}")
            return csrf, session_cookie
    except Exception as ex:
        print(f"WARN: Could not get CSRF token: {ex}")
        return None, ""


def chat(token, csrf_token, session_cookie, database_id, database_name, question, plan_state=None):
    """Send a chat message to the AI agent (non-streaming)."""
    body = {
        "messages": [{"role": "user", "content": question}],
        "context": {
            "database_id": database_id,
            "database_name": database_name,
            "schema": "dbo",
        },
    }
    if plan_state:
        body["plan_state"] = plan_state

    payload = json.dumps(body).encode()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    if session_cookie:
        headers["Cookie"] = session_cookie

    req = urllib.request.Request(
        f"{BASE}/api/v1/ai_assistant/chat",
        data=payload,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: HTTP {e.code}: {body[:500]}")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None

    return data


def print_result(result):
    """Print detailed result info."""
    print(f"\n=== Agent Response ===")
    print(f"Response text ({len(result.get('response', ''))} chars):")
    print(result.get("response", "(empty)")[:500])

    steps = result.get("steps", [])
    print(f"\nSteps: {len(steps)}")
    for i, step in enumerate(steps):
        tool = step.get("tool", "?")
        summary = step.get("result_summary", "?")
        status = "OK" if "Error" not in summary else "FAIL"
        print(f"  [{status}] {i+1}. {tool}: {summary[:150]}")

    actions = result.get("actions", [])
    print(f"\nActions: {len(actions)}")
    for a in actions:
        atype = a.get("type", "?")
        if atype == "update_todo":
            items = a.get("items", [])
            done = sum(1 for x in items if x.get("status") == "done")
            print(f"  update_todo: {done}/{len(items)} done")
        elif atype == "open_chart":
            print(f"  open_chart: {a.get('chart_name', '?')} (saved={a.get('saved')}, id={a.get('chart_id', '?')})")
        elif atype == "open_dashboard":
            print(f"  open_dashboard: {a.get('dashboard_title', '?')} url={a.get('dashboard_url', '?')}")
        elif atype == "ask_user":
            print(f"  ask_user: {a.get('question', '?')}")
            for opt in a.get("options", []):
                print(f"    [{opt.get('id')}] {opt.get('label')}")
        else:
            print(f"  {atype}: {json.dumps(a, default=str)[:120]}")

    usage = result.get("usage", {})
    print(f"\nToken usage: {usage}")

    plan_state = result.get("plan_state")
    if plan_state:
        ctx = plan_state.get("context", {})
        print(f"\nPlan state: phase={plan_state.get('phase')}, "
              f"steps={len(plan_state.get('steps', []))}, "
              f"tables={len(ctx.get('tables', {}))}, "
              f"entity={ctx.get('entity_name')}, "
              f"filter={'yes' if ctx.get('entity_filter') else 'no'}, "
              f"chart_ids={ctx.get('chart_ids', [])}, "
              f"dashboard={ctx.get('dashboard_created')}, "
              f"candidates={len(ctx.get('entity_candidates', []))}")
    else:
        print("\nNo plan_state in response")


def check_dashboards(token, search="ai_"):
    """List recent dashboards."""
    req = urllib.request.Request(
        f"{BASE}/api/v1/dashboard/?q=(filters:!((col:dashboard_title,opr:ct,value:'{search}')),order_column:changed_on_delta_humanized,order_direction:desc,page:0,page_size:5)",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        dashboards = data.get("result", [])
        print(f"\n=== Recent dashboards matching '{search}' ===")
        for d in dashboards:
            print(f"  id={d['id']}, title={d.get('dashboard_title', '?')}, url=/superset/dashboard/{d['id']}/")
        return dashboards
    except Exception as ex:
        print(f"WARN: Could not list dashboards: {ex}")
        return []


def check_charts(token, search="ai_"):
    """List recent charts."""
    req = urllib.request.Request(
        f"{BASE}/api/v1/chart/?q=(filters:!((col:slice_name,opr:ct,value:'{search}')),order_column:changed_on_delta_humanized,order_direction:desc,page:0,page_size:10)",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        charts = data.get("result", [])
        print(f"\n=== Recent charts matching '{search}' ===")
        for c in charts:
            print(f"  id={c['id']}, name={c.get('slice_name', '?')}, viz={c.get('viz_type', '?')}")
        return charts
    except Exception as ex:
        print(f"WARN: Could not list charts: {ex}")
        return []


def main():
    print("=== Vambery AI Agent E2E Test ===\n")

    # 1. Login
    token = login()
    csrf, session_cookie = get_csrf(token)

    # 2. Database — PARTNER_CONTROL_RAW_P has the financial data
    db_id = 3
    db_name = "PARTNER_CONTROL_RAW_P"
    print(f"\nUsing database: id={db_id}, name={db_name}")

    # 3. Send initial question — testing "4iG" entity extraction
    question = "4iG pénzügyi adatairól csinálj egy dashboard-ot (bevétel, kiadás, létszám) az elmúlt 10 évben."
    print(f"\n=== Sending question ===")
    print(f"Q: {question}\n")
    print("Waiting for agent response (this may take 1-5 minutes)...")

    result = chat(token, csrf, session_cookie, db_id, db_name, question)

    if result is None:
        print("\nAgent returned no result.")
        sys.exit(1)

    print_result(result)

    # 4. Handle ask_user if triggered (entity selection)
    ask_actions = [a for a in result.get("actions", []) if a.get("type") == "ask_user"]
    if ask_actions and result.get("plan_state"):
        ask = ask_actions[0]
        options = ask.get("options", [])
        print(f"\n=== Agent is asking a question! ===")
        print(f"Q: {ask.get('question')}")

        # Auto-select: prefer Nyrt/Részvénytársaság/Informatikai, else first
        selected = None
        prefer_keywords = ["Nyrt", "Részvénytársaság", "Informatikai"]
        for opt in options:
            if opt.get("id") == "none":
                continue
            label = opt.get("label", "")
            if any(kw in label for kw in prefer_keywords):
                selected = label
                break
        if not selected:
            for opt in options:
                if opt.get("id") != "none":
                    selected = opt.get("label")
                    break

        if selected:
            print(f"Auto-selecting: '{selected}'")
            print(f"\n=== Sending answer with plan_state ===")
            print("Waiting for agent to continue...")

            result2 = chat(
                token, csrf, session_cookie, db_id, db_name,
                selected,
                plan_state=result["plan_state"],
            )

            if result2:
                print_result(result2)
                result = result2  # Use the final result for chart/dashboard check
            else:
                print("Agent returned no result for the follow-up.")
        else:
            print("No valid option to select.")

    # 5. Check created artifacts
    check_charts(token)
    check_dashboards(token)

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()
