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
import subprocess
import sys

from flask import current_app

logger = logging.getLogger(__name__)

REQUIRED_PACKAGES = {
    "openai": "openai>=1.0.0",
}


def _ensure_dependencies() -> list[str]:
    """Check and auto-install missing Python dependencies.

    Returns list of packages that were installed.
    """
    installed = []
    for import_name, pip_spec in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            logger.warning(
                "Vambery AI Agent: package '%s' not found, installing '%s'...",
                import_name,
                pip_spec,
            )
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--quiet", pip_spec],
                    stdout=subprocess.DEVNULL,
                )
                importlib.invalidate_caches()
                installed.append(pip_spec)
                logger.info("Vambery AI Agent: installed '%s' successfully", pip_spec)
            except Exception:
                logger.exception(
                    "Vambery AI Agent: failed to install '%s' — "
                    "install it manually: pip install %s",
                    pip_spec,
                    pip_spec,
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
