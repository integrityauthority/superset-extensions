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
Vambery AI Agent REST API.

Provides the /api/v1/ai_assistant/ endpoints for the chat interface.
Supports both regular JSON responses and SSE streaming.
"""

from __future__ import annotations

import json
import logging
from typing import Generator

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ai_assistant.agent import run_agent, run_agent_stream
from ai_assistant.config import get_ai_config, get_provider_config

logger = logging.getLogger(__name__)

ai_assistant_bp = Blueprint(
    "ai_assistant",
    __name__,
    url_prefix="/api/v1/ai_assistant",
)


@ai_assistant_bp.route("/chat", methods=["POST"])
def chat() -> tuple[Response, int] | Response:
    """
    Vambery AI Agent chat endpoint.

    Request body:
    {
        "messages": [
            {"role": "user", "content": "Create a query that shows..."}
        ],
        "context": {
            "database_id": 1,
            "database_name": "My Database",
            "schema": "dbo",
            "catalog": null,
            "current_sql": "SELECT ..."
        }
    }

    Response:
    {
        "response": "Here's the query...",
        "actions": [{"type": "set_editor_sql", "sql": "SELECT ..."}],
        "steps": [...],
        "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
    }
    """
    # Check authentication - require logged-in user
    try:
        from superset.extensions import security_manager

        if not security_manager.current_user or security_manager.current_user.is_anonymous:
            return jsonify({"error": "Authentication required"}), 401
    except Exception as ex:
        logger.warning("Could not check authentication: %s", ex)

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "At least one message is required"}), 400

    context = data.get("context", {})
    database_id = context.get("database_id")
    if not database_id:
        return jsonify({"error": "database_id is required in context"}), 400

    model_override = context.get("model_override")

    try:
        result = run_agent(
            messages=messages,
            database_id=database_id,
            database_name=context.get("database_name"),
            schema_name=context.get("schema"),
            catalog=context.get("catalog"),
            current_sql=context.get("current_sql"),
            model_override=model_override,
        )
        return jsonify(result)
    except Exception as ex:
        logger.exception("Error in Vambery AI Agent chat endpoint")
        return jsonify({"error": str(ex)}), 500


@ai_assistant_bp.route("/chat/stream", methods=["POST"])
def chat_stream() -> tuple[Response, int] | Response:
    """
    Streaming version of the chat endpoint using Server-Sent Events (SSE).

    Returns a stream of events:
        event: step\ndata: {"type":"tool_call","tool":"...","args":{...},"result_summary":"..."}\n\n
        event: action\ndata: {"type":"set_editor_sql","sql":"..."}\n\n
        event: response\ndata: {"response":"...","usage":{...}}\n\n
        event: error\ndata: {"error":"..."}\n\n
    """
    # Check authentication
    try:
        from superset.extensions import security_manager

        if not security_manager.current_user or security_manager.current_user.is_anonymous:
            return jsonify({"error": "Authentication required"}), 401
    except Exception as ex:
        logger.warning("Could not check authentication: %s", ex)

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "At least one message is required"}), 400

    context = data.get("context", {})
    database_id = context.get("database_id")
    if not database_id:
        return jsonify({"error": "database_id is required in context"}), 400

    model_override = context.get("model_override")

    def generate() -> Generator[str, None, None]:
        try:
            for event in run_agent_stream(
                messages=messages,
                database_id=database_id,
                database_name=context.get("database_name"),
                schema_name=context.get("schema"),
                catalog=context.get("catalog"),
                current_sql=context.get("current_sql"),
                model_override=model_override,
            ):
                event_type = event["event"]
                event_data = json.dumps(event["data"], default=str)
                yield f"event: {event_type}\ndata: {event_data}\n\n"
        except Exception as ex:
            logger.exception("Error in streaming chat endpoint")
            error_data = json.dumps({"error": str(ex)})
            yield f"event: error\ndata: {error_data}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@ai_assistant_bp.route("/models", methods=["GET"])
def list_models() -> tuple[Response, int] | Response:
    """
    List available LLM models for the configured provider.

    For Ollama, queries the Ollama server's /api/tags endpoint
    to discover installed models. For other providers, returns
    the configured model/deployment name.

    Response:
    {
        "provider": "ollama",
        "models": [
            {"name": "qwen3.5:122b", "size_gb": 70.2, ...},
            ...
        ],
        "default_model": "llama3.1"
    }
    """
    try:
        config = get_ai_config()
        provider = config.get("provider", "unknown")
        p_config = get_provider_config(provider)

        if provider == "ollama":
            from ai_assistant.llm import list_ollama_models

            base_url = p_config.get(
                "base_url", "http://localhost:11434"
            )
            models = list_ollama_models(base_url)
            default_model = p_config.get("model", "llama3.1")
            return jsonify({
                "provider": provider,
                "models": models,
                "default_model": default_model,
            })

        # Non-Ollama providers: return the configured model
        model_name = p_config.get(
            "model",
            p_config.get("deployment_name", "unknown"),
        )
        return jsonify({
            "provider": provider,
            "models": [{"name": model_name}],
            "default_model": model_name,
        })
    except Exception as ex:
        logger.exception("Error listing models")
        return jsonify({"error": str(ex)}), 500


@ai_assistant_bp.route("/health", methods=["GET"])
def health() -> tuple[Response, int] | Response:
    """Health check endpoint for the Vambery AI Agent extension."""
    try:
        config = get_ai_config()
        provider = config.get("provider", "unknown")
        provider_config = config.get(provider, {})
        if provider == "ollama":
            configured = bool(provider_config.get("base_url"))
        else:
            has_key = bool(provider_config.get("api_key"))
            has_ep = bool(
                provider_config.get("azure_endpoint")
                or provider_config.get("base_url")
            )
            configured = has_key and has_ep

        return jsonify(
            {
                "status": "ok",
                "provider": provider,
                "configured": configured,
            }
        )
    except Exception as ex:
        return jsonify({"status": "error", "error": str(ex)}), 500
