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
Vambery AI Agent Extension Entrypoint.

This module is loaded during Superset initialization when the extension is enabled.
It auto-installs missing Python dependencies and registers the Flask Blueprint
that exposes the Vambery AI Agent API endpoints.
"""

import importlib
import logging
import shutil
import subprocess
import sys

from flask import current_app

logger = logging.getLogger(__name__)

REQUIRED_PACKAGES = {
    "openai": "openai>=1.0.0",
}


def _pip_install(pip_spec: str) -> bool:
    """Try to install a package using uv (preferred) or pip (fallback).

    Returns True if installation succeeded.
    """
    # Try uv first (faster, used by Superset Docker images)
    uv_path = shutil.which("uv")
    if uv_path:
        result = subprocess.run(
            [uv_path, "pip", "install", pip_spec],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info("Vambery AI Agent: installed '%s' via uv", pip_spec)
            return True
        logger.warning(
            "Vambery AI Agent: uv install failed (rc=%d): %s",
            result.returncode, result.stderr.strip(),
        )

    # Fallback to pip
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", pip_spec],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        logger.info("Vambery AI Agent: installed '%s' via pip", pip_spec)
        return True

    logger.error(
        "Vambery AI Agent: pip install failed (rc=%d): %s",
        result.returncode, result.stderr.strip(),
    )
    return False


def _ensure_dependencies() -> list[str]:
    """Check and auto-install missing Python dependencies.

    Returns list of packages that were installed.
    """
    installed = []
    missing = []
    for import_name, pip_spec in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            logger.warning(
                "Vambery AI Agent: package '%s' not found, attempting install...",
                import_name,
            )
            if _pip_install(pip_spec):
                importlib.invalidate_caches()
                # Verify it actually works now
                try:
                    importlib.import_module(import_name)
                    installed.append(pip_spec)
                except ImportError:
                    logger.error(
                        "Vambery AI Agent: '%s' installed but still not importable. "
                        "This may be a virtualenv/path issue.",
                        import_name,
                    )
                    missing.append(import_name)
            else:
                missing.append(import_name)

    if missing:
        logger.error(
            "Vambery AI Agent: MISSING DEPENDENCIES: %s. "
            "The extension will load but chat will NOT work. "
            "Fix: add 'openai>=1.0.0' to docker/requirements-local.txt "
            "or run: pip install %s",
            ", ".join(missing),
            " ".join(REQUIRED_PACKAGES[m] for m in missing if m in REQUIRED_PACKAGES),
        )
    return installed


auto_installed = _ensure_dependencies()
if auto_installed:
    logger.info(
        "Vambery AI Agent: auto-installed dependencies: %s",
        ", ".join(auto_installed),
    )

from ai_assistant.api import ai_assistant_bp  # noqa: E402

# Register the Vambery AI Agent Blueprint
current_app.register_blueprint(ai_assistant_bp)

logger.info("Vambery AI Agent extension registered successfully (v%s)",
            __import__("ai_assistant").__version__)
print("Vambery AI Agent extension registered")
