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
LLM Provider Abstraction.

Supports multiple LLM providers with a unified interface.
Providers: Azure OpenAI, OpenAI (+ OpenRouter), Ollama.
"""

from __future__ import annotations

import logging
import time
from typing import Any
import requests

logger = logging.getLogger(__name__)


def list_ollama_models(base_url: str) -> list[dict[str, Any]]:
    """
    Query Ollama's /api/tags endpoint to list installed models.
    Returns a list of model dicts with name, size, parameter_size, etc.
    """
    url = base_url.rstrip("/") + "/api/tags"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = data.get("models", [])
        result = []
        for m in models:
            entry: dict[str, Any] = {
                "name": m.get("name", ""),
                "size_gb": round(
                    m.get("size", 0) / (1024**3), 1
                ),
                "modified_at": m.get("modified_at", ""),
            }
            details = m.get("details", {})
            if details.get("parameter_size"):
                entry["parameter_size"] = details["parameter_size"]
            if details.get("family"):
                entry["family"] = details["family"]
            if details.get("quantization_level"):
                entry["quantization"] = details[
                    "quantization_level"
                ]
            result.append(entry)
        return result
    except Exception as ex:
        logger.error(
            "Failed to list Ollama models from %s: %s",
            url, ex,
        )
        return []


# Deployments that cannot chat: embeddings, speech, images.
_NON_CHAT_MODELS = ("embedding", "whisper", "tts", "dall-e", "gpt-image", "transcribe", "sora")
_AZURE_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_AZURE_CACHE_SECONDS = 600


def list_azure_deployments(config: dict[str, Any]) -> list[dict[str, str]]:
    """Chat-capable deployments of the Azure OpenAI resource.

    ``config["deployments"]`` (comma-separated, env AZURE_OPENAI_DEPLOYMENTS)
    is an allow-list; without it the resource is asked, and the answer is
    cached for ten minutes. Falls back to the configured deployment alone.
    """
    default = config.get("deployment_name", "")
    allowed = [d.strip() for d in str(config.get("deployments") or "").split(",") if d.strip()]
    if allowed:
        return [{"name": d, "model": d} for d in allowed]

    endpoint = str(config.get("azure_endpoint", "")).rstrip("/")
    cached = _AZURE_CACHE.get(endpoint)
    if cached and time.time() - cached[0] < _AZURE_CACHE_SECONDS:
        return cached[1]
    try:
        # The deployments listing exists only in this older data-plane version.
        resp = requests.get(
            f"{endpoint}/openai/deployments",
            params={"api-version": "2022-12-01"},
            headers={"api-key": config["api_key"]},
            timeout=10,
        )
        resp.raise_for_status()
        found = [
            {"name": d["id"], "model": d.get("model", d["id"])}
            for d in resp.json().get("data", [])
            if d.get("status", "succeeded") == "succeeded"
            and not any(k in d.get("model", d["id"]).lower() for k in _NON_CHAT_MODELS)
        ]
    except Exception as ex:  # noqa: BLE001
        logger.warning("Could not list Azure OpenAI deployments: %s", ex)
        found = []
    if default and default not in {d["name"] for d in found}:
        found.insert(0, {"name": default, "model": default})
    _AZURE_CACHE[endpoint] = (time.time(), found)
    return found


# Deployments that refused function tools while reasoning was on. Newer
# reasoning models (e.g. gpt-6-luna) reject tools on /chat/completions unless
# reasoning_effort is "none", while others (gpt-5.2-chat) reject "none", so the
# parameter is only sent where the model asked for it.
_NO_REASONING_WITH_TOOLS: set[str] = set()


def _create_completion(client: Any, kwargs: dict[str, Any], configured_effort: str | None) -> Any:
    """Call chat.completions.create, adapting reasoning_effort to the model."""
    model = kwargs["model"]
    if configured_effort:
        kwargs["reasoning_effort"] = configured_effort
    elif kwargs.get("tools") and model in _NO_REASONING_WITH_TOOLS:
        kwargs["reasoning_effort"] = "none"
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as ex:  # openai.BadRequestError; imported lazily
        message = str(ex)
        if (
            configured_effort
            or "reasoning_effort" in kwargs
            or not kwargs.get("tools")
            or "reasoning_effort" not in message
        ):
            raise
        logger.info(
            "Model %s refuses tools with reasoning on; retrying with reasoning_effort=none",
            model,
        )
        _NO_REASONING_WITH_TOOLS.add(model)
        return client.chat.completions.create(**{**kwargs, "reasoning_effort": "none"})


def create_chat_completion(
    provider_config: dict[str, Any],
    provider: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Create a chat completion using the configured LLM provider.

    Returns the raw response from the LLM in a normalized format:
    {
        "message": {
            "role": "assistant",
            "content": "...",
            "tool_calls": [...]  # optional
        },
        "finish_reason": "stop" | "tool_calls",
        "usage": {...}
    }
    """
    if provider == "azure_openai":
        return _azure_openai_completion(provider_config, messages, tools)
    elif provider == "openai":
        return _openai_completion(provider_config, messages, tools)
    elif provider == "ollama":
        return _ollama_completion(provider_config, messages, tools)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def _azure_openai_completion(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Azure OpenAI Chat Completions API."""
    try:
        from openai import AzureOpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required for Azure OpenAI. "
            "Install it with: pip install openai"
        )

    client = AzureOpenAI(
        api_key=config["api_key"],
        api_version=config.get("api_version", "2025-03-01-preview"),
        azure_endpoint=config["azure_endpoint"],
    )

    # A model picked in the chat panel arrives as "model" and names a deployment.
    deployment = config.get("model") or config["deployment_name"]
    kwargs: dict[str, Any] = {
        "model": deployment,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    logger.debug(
        "Azure OpenAI request: model=%s, messages=%d, tools=%s",
        deployment,
        len(messages),
        len(tools) if tools else 0,
    )

    response = _create_completion(client, kwargs, config.get("reasoning_effort"))
    choice = response.choices[0]

    result: dict[str, Any] = {
        "message": {
            "role": choice.message.role,
            "content": choice.message.content,
        },
        "finish_reason": choice.finish_reason,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": (
                response.usage.completion_tokens if response.usage else 0
            ),
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        },
    }

    # Include tool calls if present
    if choice.message.tool_calls:
        result["message"]["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.message.tool_calls
        ]

    logger.debug(
        "Azure OpenAI response: finish_reason=%s, tool_calls=%d",
        choice.finish_reason,
        len(choice.message.tool_calls) if choice.message.tool_calls else 0,
    )

    return result


def _openai_completion(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Standard OpenAI Chat Completions API (also works for OpenRouter etc.)."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required. Install it with: pip install openai"
        )

    client_kwargs: dict[str, Any] = {"api_key": config["api_key"]}
    if "base_url" in config:
        client_kwargs["base_url"] = config["base_url"]

    client = OpenAI(**client_kwargs)

    kwargs: dict[str, Any] = {
        "model": config.get("model", config.get("deployment_name", "gpt-4")),
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = _create_completion(client, kwargs, config.get("reasoning_effort"))
    choice = response.choices[0]

    result: dict[str, Any] = {
        "message": {
            "role": choice.message.role,
            "content": choice.message.content,
        },
        "finish_reason": choice.finish_reason,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": (
                response.usage.completion_tokens if response.usage else 0
            ),
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        },
    }

    if choice.message.tool_calls:
        result["message"]["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.message.tool_calls
        ]

    return result


def _ollama_completion(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Ollama Chat Completions via the OpenAI-compatible API.

    Ollama exposes /v1/chat/completions which is compatible with the
    OpenAI Python SDK. No API key is required for local/self-hosted
    instances, but we send a dummy key since the SDK requires one.

    The model can be overridden at runtime via config["model"] which
    the agent sets from the frontend's model selector.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required for Ollama. "
            "Install it with: pip install openai"
        )

    raw_base = config.get("base_url", "http://localhost:11434")
    # Ensure /v1/ suffix for OpenAI SDK compatibility
    api_url = raw_base.rstrip("/")
    if not api_url.endswith("/v1"):
        api_url += "/v1/"

    client = OpenAI(
        api_key=config.get("api_key", "ollama"),
        base_url=api_url,
    )

    model = config.get("model", "llama3.1")

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    logger.debug(
        "Ollama request: base_url=%s, model=%s, messages=%d, tools=%s",
        api_url,
        model,
        len(messages),
        len(tools) if tools else 0,
    )

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]

    result: dict[str, Any] = {
        "message": {
            "role": choice.message.role,
            "content": choice.message.content or "",
        },
        "finish_reason": choice.finish_reason,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": (
                response.usage.completion_tokens if response.usage else 0
            ),
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        },
    }

    if choice.message.tool_calls:
        result["message"]["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.message.tool_calls
        ]

    logger.debug(
        "Ollama response: model=%s, finish_reason=%s, tool_calls=%d",
        model,
        choice.finish_reason,
        len(choice.message.tool_calls) if choice.message.tool_calls else 0,
    )

    return result
