#!/usr/bin/env bash
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
#
# Build all extensions into the dist/ bundle format expected by Superset.
#
# Usage (from repo root or inside container):
#   bash build-extensions.sh
#
# Requires: node/npm (or run via: docker run --rm -v $PWD:/app -w /app node:20-slim bash build-extensions.sh)
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

build_extension() {
    local ext_dir="$1"
    local ext_name
    ext_name="$(basename "$ext_dir")"

    echo "=== Building extension: ${ext_name} ==="

    # Check for extension.json
    if [ ! -f "${ext_dir}/extension.json" ]; then
        echo "  SKIP: no extension.json found"
        return
    fi

    # Clean previous dist
    rm -rf "${ext_dir}/dist"
    mkdir -p "${ext_dir}/dist/frontend/dist"

    # Build frontend if present
    if [ -f "${ext_dir}/frontend/package.json" ]; then
        echo "  Installing frontend dependencies..."
        (cd "${ext_dir}/frontend" && npm install --legacy-peer-deps --no-audit --no-fund)
        echo "  Building frontend..."
        (cd "${ext_dir}/frontend" && npm run build)
        cp "${ext_dir}/frontend/dist/"* "${ext_dir}/dist/frontend/dist/"
        echo "  Frontend built OK"
    fi

    # Copy backend sources if present
    if [ -d "${ext_dir}/backend/src" ]; then
        mkdir -p "${ext_dir}/dist/backend/src"
        cp -r "${ext_dir}/backend/src/"* "${ext_dir}/dist/backend/src/"
        echo "  Backend sources copied"
    fi

    # Generate manifest.json from extension.json
    local remote_entry
    remote_entry=$(ls "${ext_dir}/dist/frontend/dist/" 2>/dev/null | grep "^remoteEntry" | head -1)

    python3 -c "
import json, sys

with open('${ext_dir}/extension.json') as f:
    ext = json.load(f)

manifest = {
    'id': ext['id'],
    'name': ext['name'],
    'version': ext['version'],
    'license': ext.get('license', 'Apache-2.0'),
}

if ext.get('frontend'):
    manifest['frontend'] = {
        'contributions': ext['frontend'].get('contributions', {}),
        'moduleFederation': ext['frontend'].get('moduleFederation', {}),
        'remoteEntry': '${remote_entry}',
    }

if ext.get('backend'):
    manifest['backend'] = {
        'entryPoints': ext['backend'].get('entryPoints', []),
    }

if 'permissions' in ext:
    manifest['permissions'] = ext['permissions']

with open('${ext_dir}/dist/manifest.json', 'w') as f:
    json.dump(manifest, f, indent=2)
print('  manifest.json generated')
"

    echo "=== ${ext_name} build complete ==="
}

# Build each extension that has an extension.json
for ext_dir in "${SCRIPT_DIR}"/*/; do
    if [ -f "${ext_dir}/extension.json" ]; then
        build_extension "${ext_dir}"
    fi
done

echo "All extensions built."
