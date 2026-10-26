/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

/**
 * Fallback for the shared `@apache-superset/core` module.
 *
 * Superset 7.0+ hands each extension its own instance of `@apache-superset/core`
 * through the Module Federation share scope, with `extensions.getContext()`
 * bound to that extension — the only way to reach the Storage API. The global
 * `window.superset.extensions.getContext()` always throws.
 *
 * Superset 6.1 puts no such module in the share scope; its API lives on
 * `window.superset`. Webpack falls back to this module there. It is shared at
 * version 0.0.0 so any host-provided instance (0.2.0 on 7.0) always wins.
 */
module.exports = window.superset;
