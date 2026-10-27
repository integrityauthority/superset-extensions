# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Compare two run_parity.py outputs.

    python compare_parity.py old.json new.json [--expect expected_changes.json]

A case counts as a regression when the old run succeeded (no "error" key) and
the new one did not, or when it returned different data. Cases listed in the
expectations file are intentional changes and are reported, not failed.
Exit status 1 if any unexpected difference remains.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Values that legitimately differ between runs on the same instance.
VOLATILE = {"datasource", "datasource_id", "datasource_name", "version", "count", "datasets"}


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--expect", help="JSON: {case: reason} for intended changes")
    args = parser.parse_args()

    old = json.load(open(args.old, encoding="utf-8"))
    new = json.load(open(args.new, encoding="utf-8"))
    expected = json.load(open(args.expect, encoding="utf-8")) if args.expect else {}
    print(f"{old['version']} -> {new['version']} as {new['user']}")

    unexpected = 0
    for case in sorted((set(old) | set(new)) - {"version", "user"}):
        a, b = _strip(old.get(case)), _strip(new.get(case))
        if a == b:
            print(f"  same      {case}")
            continue
        if case in expected:
            print(f"  expected  {case}: {expected[case]}")
            continue
        unexpected += 1
        print(f"  CHANGED   {case}")
        print(f"      old: {json.dumps(a)[:400]}")
        print(f"      new: {json.dumps(b)[:400]}")
    print(f"{unexpected} unexpected difference(s)")
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
