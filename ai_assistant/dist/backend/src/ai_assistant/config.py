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
Vambery AI Agent Configuration.

Reads Vambery AI Agent configuration from Superset's config (superset_config.py).
Configuration is stored under the AI_ASSISTANT key.

Example superset_config.py entry:
    AI_ASSISTANT = {
        "provider": "azure_openai",
        "azure_openai": {
            "api_key": "your-api-key",
            "api_version": "2025-03-01-preview",
            "azure_endpoint": "https://your-resource.openai.azure.com/",
            "deployment_name": "gpt-52",
        },
        "system_prompt_extra": "",  # Additional instructions appended to system prompt
        "max_tool_rounds": 10,      # Max number of tool-use round trips
        "max_sample_rows": 20,      # Max rows returned by sample queries
    }
"""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULTS: dict[str, Any] = {
    "provider": "azure_openai",
    "azure_openai": {
        "api_key": "",
        "api_version": "2025-03-01-preview",
        "azure_endpoint": "",
        "deployment_name": "gpt-52",
    },
    "system_prompt_extra": "",
    "max_tool_rounds": 10,
    "max_sample_rows": 20,
}


def get_ai_config() -> dict[str, Any]:
    """Get the Vambery AI Agent configuration from Superset config, merged with defaults."""
    user_config = current_app.config.get("AI_ASSISTANT", {})
    merged = {**DEFAULTS, **user_config}

    # Deep merge nested dicts (e.g. azure_openai)
    for key in DEFAULTS:
        if isinstance(DEFAULTS[key], dict) and key in user_config:
            merged[key] = {**DEFAULTS[key], **user_config[key]}

    return merged


def get_provider_config(provider: str | None = None) -> dict[str, Any]:
    """Get the configuration for the active LLM provider."""
    config = get_ai_config()
    provider = provider or config["provider"]
    provider_config = config.get(provider, {})

    if not provider_config:
        logger.warning("No configuration found for AI provider: %s", provider)

    return provider_config
