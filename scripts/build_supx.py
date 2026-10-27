#!/usr/bin/env python3
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
Build an extension into a .supx package, on any platform.

    python scripts/build_supx.py ai_assistant [--skip-npm] [--out DIR]

Steps, each of which stops the build before anything is overwritten:
1. every version string agrees (extension.json, package.json, pyproject.toml,
   the package __init__.py);
2. the frontend builds (``npm ci`` + ``npm run build``) unless --skip-npm;
3. ``<ext>/dist`` is rebuilt from scratch: manifest.json (the full
   extension.json plus the generated fields), frontend bundle, backend sources;
4. ``<publisher>.<name>-<version>.supx`` and its ``-requirements.txt`` (LF line
   endings) are written to --out (default: the repository root).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def read_versions(ext_dir: Path, ext: dict) -> dict[str, str]:
    versions = {"extension.json": ext["version"]}
    package_json = ext_dir / "frontend" / "package.json"
    if package_json.exists():
        versions["frontend/package.json"] = json.loads(package_json.read_text("utf-8"))[
            "version"
        ]
    pyproject = ext_dir / "backend" / "pyproject.toml"
    if pyproject.exists():
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text("utf-8"), re.M)
        if match:
            versions["backend/pyproject.toml"] = match.group(1)
    for init in sorted((ext_dir / "backend" / "src").glob("*/__init__.py")):
        match = re.search(r'^__version__\s*=\s*"([^"]+)"', init.read_text("utf-8"), re.M)
        if match:
            versions[str(init.relative_to(ext_dir)).replace("\\", "/")] = match.group(1)
    return versions


def build_frontend(frontend: Path) -> None:
    npm = shutil.which("npm")
    if not npm:
        fail("npm not found; install Node.js or pass --skip-npm to reuse frontend/dist")
    for args in (["ci", "--no-audit", "--no-fund"], ["run", "build"]):
        print(f"  npm {' '.join(args)}")
        subprocess.run([npm, *args], cwd=frontend, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("extension", help="extension directory, e.g. ai_assistant")
    parser.add_argument("--skip-npm", action="store_true", help="reuse frontend/dist")
    parser.add_argument("--out", type=Path, default=ROOT, help="output directory")
    args = parser.parse_args()

    ext_dir = (ROOT / args.extension).resolve()
    ext = json.loads((ext_dir / "extension.json").read_text("utf-8"))
    ext_id = f"{ext['publisher']}.{ext['name']}"
    version = ext["version"]

    # Superset's manifest schema accepts only plain X.Y.Z (no "-rc1"); stage a
    # release candidate as a GitHub prerelease of the final number instead.
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"version {version!r} must be X.Y.Z; Superset rejects anything else")

    versions = read_versions(ext_dir, ext)
    if len(set(versions.values())) != 1:
        listing = "\n".join(f"  {k}: {v}" for k, v in versions.items())
        fail(f"version strings disagree:\n{listing}")
    print(f"Building {ext_id} {version}")

    frontend = ext_dir / "frontend"
    if ext.get("frontend"):
        if not args.skip_npm:
            build_frontend(frontend)
        bundle = frontend / "dist"
        entries = sorted(bundle.glob("remoteEntry*.js")) if bundle.exists() else []
        if len(entries) != 1:
            fail(f"expected exactly one remoteEntry*.js in {bundle}, found {len(entries)}")
        remote_entry = entries[0].name

    manifest = {"id": ext_id, **ext}
    if ext.get("frontend"):
        manifest["frontend"] = {
            **ext["frontend"],
            "remoteEntry": remote_entry,
            "moduleFederationName": ext["frontend"]["moduleFederation"]["name"],
        }
    if ext.get("backend"):
        manifest["backend"] = {
            key: value for key, value in ext["backend"].items() if key != "files"
        }
        manifest["backend"]["entrypoint"] = ext["backend"]["entryPoints"][0]

    # Assemble in a temporary directory; dist/ is replaced only once it is complete.
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "dist"
        staging.mkdir()
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", "utf-8"
        )
        if ext.get("frontend"):
            shutil.copytree(frontend / "dist", staging / "frontend" / "dist")
        if ext.get("backend"):
            shutil.copytree(
                ext_dir / "backend" / "src",
                staging / "backend" / "src",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

        dist = ext_dir / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        shutil.copytree(staging, dist)

    args.out.mkdir(parents=True, exist_ok=True)
    supx = args.out / f"{ext_id}-{version}.supx"
    with zipfile.ZipFile(supx, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(dist.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(dist).as_posix())
    requirements = ext.get("backend", {}).get("dependencies", {}).get("python", [])
    req_file = args.out / f"{ext_id}-{version}-requirements.txt"
    with open(req_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(f"{line}\n" for line in requirements))
    print(f"  {supx}\n  {req_file}")


if __name__ == "__main__":
    main()
