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
Permission checks for the agent's tools.

The agent may do exactly what the acting user could do in SQL Lab and in
Superset's own UI, nothing more:

- databases must be visible to the user and exposed in SQL Lab;
- SQL runs only after the same ``raise_for_access`` check SQL Lab applies;
- table metadata and samples need table access;
- writes to charts, datasets and dashboards need editorship.

Every check raises ``AccessDenied``; tools turn it into an error result the
model can read. Each tool call is logged with the acting user.
"""

from __future__ import annotations

import logging
from typing import Any

from superset_core.common import daos

from superset.extensions import db, security_manager
from superset.sql.parse import SQLScript, Table
from superset.utils.core import get_username

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("ai_assistant.audit")


class AccessDenied(Exception):
    """The acting user may not perform this operation."""


def current_username() -> str:
    return get_username() or "<anonymous>"


def audit(tool: str, **details: Any) -> None:
    """Log a tool call with the acting user, for the audit trail."""
    rendered = " ".join(f"{k}={v!r}" for k, v in details.items() if v is not None)
    audit_logger.info("user=%s tool=%s %s", current_username(), tool, rendered)


def find_visible(dao: Any, model: Any, object_id: int) -> Any:
    """Fetch one object by id through the DAO's access filter, or None.

    ``dao.find_one_or_none(id=...)`` is not used on purpose: it applies
    ``filter_by`` after the base filter, and when that filter joins another
    table (as the dataset filter does for non-admin users) ``filter_by``
    targets the joined table's ``id`` and finds nothing.
    """
    rows = dao.query(db.session.query(model).filter(model.id == object_id))
    return rows[0] if rows else None


def get_database(database_id: int) -> Any:
    """Load a database the user can see and use in SQL Lab.

    The DAO applies Superset's database filter, so a database the user has no
    access to is reported as not found rather than revealed.
    """
    from superset.models.core import Database

    database = find_visible(daos.DatabaseDAO, Database, database_id)
    if database is None:
        raise AccessDenied(f"Database with id={database_id} not found")
    if not database.expose_in_sqllab:
        raise AccessDenied(f"Database '{database.database_name}' is not available in SQL Lab")
    return database


def _raise(check: Any, message: str) -> None:
    from superset.exceptions import SupersetSecurityException

    try:
        check()
    except SupersetSecurityException as ex:
        raise AccessDenied(message) from ex


def check_table_access(database: Any, table: Table) -> None:
    _raise(
        lambda: security_manager.raise_for_access(database=database, table=table),
        f"No access to table {table}",
    )


def check_sql_access(
    database: Any, sql: str, catalog: str | None, schema: str | None
) -> None:
    """Apply SQL Lab's own execute-time check to `sql`."""
    _raise(
        lambda: security_manager.raise_for_access(
            database=database,
            sql=sql,
            catalog=catalog,
            schema=schema,
            force_dataset_match=True,
        ),
        "You do not have access to every table this query reads",
    )


def ensure_read_only(database: Any, sql: str) -> SQLScript:
    """Parse `sql` and allow exactly one statement that does not write.

    A prefix check (``startswith("SELECT")``) lets ``SELECT 1; DELETE ...``
    through; the parsed script does not.
    """
    from superset.exceptions import SupersetParseError

    try:
        script = SQLScript(sql, database.db_engine_spec.engine)
    except SupersetParseError as ex:
        raise ValueError(f"SQL syntax error: {ex}") from ex
    if len(script.statements) != 1:
        raise AccessDenied("Only a single SQL statement is allowed")
    if script.has_mutation():
        raise AccessDenied("Only read-only queries (SELECT / WITH) are allowed")
    return script


def filter_schemas(database: Any, catalog: str | None, schemas: set[str]) -> set[str]:
    return security_manager.get_schemas_accessible_by_user(database, catalog, schemas)


def filter_tables(
    database: Any, catalog: str | None, schema: str, tables: set[Any]
) -> list[Any]:
    return security_manager.get_datasources_accessible_by_user(
        database, list(tables), catalog, schema
    )


def check_editor(resource: Any, label: str) -> None:
    """Writes need editorship, as in Superset's own UI."""
    _raise(
        lambda: security_manager.raise_for_editorship(resource),
        f"You are not an editor of {label}",
    )
    if getattr(resource, "is_managed_externally", False):
        raise AccessDenied(f"{label} is managed externally and cannot be edited here")
