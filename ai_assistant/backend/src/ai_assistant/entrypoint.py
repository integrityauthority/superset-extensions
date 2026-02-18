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
It registers the Flask Blueprint that exposes the Vambery AI Agent API endpoints.
"""

import logging

from flask import current_app

from ai_assistant.api import ai_assistant_bp

logger = logging.getLogger(__name__)

# Register the Vambery AI Agent Blueprint
current_app.register_blueprint(ai_assistant_bp)

logger.info("Vambery AI Agent extension registered successfully")
print("Vambery AI Agent extension registered")
