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

Supported providers: azure_openai, openai, ollama

Example superset_config.py entry:
    AI_ASSISTANT = {
        "provider": "azure_openai",  # or "openai" or "ollama"
        "azure_openai": {
            "api_key": "your-api-key",
            "api_version": "2025-03-01-preview",
            "azure_endpoint": "https://your-resource.openai.azure.com/",
            "deployment_name": "gpt-52",
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "llama3.1",
        },
        "system_prompt_extra": "",
        "max_tool_rounds": 10,
        "max_sample_rows": 20,
    }
"""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import current_app

logger = logging.getLogger(__name__)

# Environment variable mapping for Docker / .env based deployments.
# These are used as fallback when AI_ASSISTANT is not set in superset_config.py.
ENV_MAPPING: dict[str, str] = {
    "provider": "AI_PROVIDER",
    "system_prompt_extra": "AI_SYSTEM_PROMPT_EXTRA",
    "max_tool_rounds": "AI_MAX_TOOL_ROUNDS",
    "max_sample_rows": "AI_MAX_SAMPLE_ROWS",
}

AZURE_ENV_MAPPING: dict[str, str] = {
    "api_key": "AZURE_OPENAI_API_KEY",
    "api_version": "AZURE_OPENAI_API_VERSION",
    "azure_endpoint": "AZURE_OPENAI_ENDPOINT",
    "deployment_name": "AZURE_OPENAI_DEPLOYMENT",
}

OLLAMA_ENV_MAPPING: dict[str, str] = {
    "base_url": "OLLAMA_BASE_URL",
    "model": "OLLAMA_MODEL",
}

# Default configuration values
DEFAULTS: dict[str, Any] = {
    "provider": "azure_openai",
    "azure_openai": {
        "api_key": "",
        "api_version": "2025-03-01-preview",
        "azure_endpoint": "",
        "deployment_name": "gpt-52",
    },
    "ollama": {
        "base_url": "http://localhost:11434",
        "model": "llama3.1",
    },
    "system_prompt_extra": "",
    "max_tool_rounds": 50,
    "max_sample_rows": 20,
}


def _read_provider_env(
    mapping: dict[str, str],
) -> dict[str, str]:
    """Read provider-specific env vars into a config dict."""
    config: dict[str, str] = {}
    for config_key, env_var in mapping.items():
        val = os.environ.get(env_var)
        if val is not None:
            config[config_key] = val
    return config


def _read_env_config() -> dict[str, Any]:
    """Build config from environment variables (Docker fallback)."""
    env_config: dict[str, Any] = {}

    for config_key, env_var in ENV_MAPPING.items():
        val = os.environ.get(env_var)
        if val is not None:
            if config_key in ("max_tool_rounds", "max_sample_rows"):
                try:
                    env_config[config_key] = int(val)
                except ValueError:
                    logger.warning(
                        "Invalid integer for %s: %s", env_var, val
                    )
            else:
                env_config[config_key] = val

    azure = _read_provider_env(AZURE_ENV_MAPPING)
    if azure:
        env_config["azure_openai"] = azure

    ollama = _read_provider_env(OLLAMA_ENV_MAPPING)
    if ollama:
        env_config["ollama"] = ollama

    return env_config


def get_ai_config() -> dict[str, Any]:
    """Get the merged Vambery AI Agent configuration.

    Priority (highest to lowest):
    1. AI_ASSISTANT dict in superset_config.py
    2. Environment variables (AZURE_OPENAI_API_KEY, etc.)
    3. Built-in defaults
    """
    user_config = current_app.config.get("AI_ASSISTANT", {})

    # If no superset_config.py entry, fall back to environment variables
    if not user_config:
        user_config = _read_env_config()
        if user_config:
            logger.info("AI_ASSISTANT config loaded from environment variables")

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
