from __future__ import annotations

from collections import defaultdict
from typing import Any

from .validators import comparable

IndexedIssues = dict[tuple[str, str, int], list[tuple[str, str]]]
StagedEntities = dict[str, dict[str, Any]]
StagedRows = list[dict[str, Any]]


def evaluate_entity_rules(staged_entities: StagedEntities) -> IndexedIssues:
    indexed_issues: IndexedIssues = defaultdict(list)
    handlers = {
        "no_parent_cycles": _evaluate_no_parent_cycles,
        "child_count_lte_reference": _evaluate_child_count_lte_reference,
    }

    for entity_name, entity_state in staged_entities.items():
        rows = entity_state.get("rows", [])
        schema = entity_state.get("schema", {})

        for rule in schema.get("entity_rules", []):
            rule_type = str(rule.get("type", "")).strip()
            handler = handlers.get(rule_type)
            if handler is not None:
                handler(indexed_issues, entity_name, rows, rule, staged_entities)

    return dict(indexed_issues)


def _evaluate_no_parent_cycles(
    indexed_issues: IndexedIssues,
    entity_name: str,
    rows: StagedRows,
    rule: dict[str, Any],
    staged_entities: StagedEntities,
):
    del staged_entities

    id_field = str(rule.get("id_field", "")).strip()
    parent_field = str(rule.get("parent_field", "")).strip()
    message = str(rule.get("message", "Parent relationship contains a cycle."))
    if not id_field or not parent_field:
        return

    row_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = comparable(row["data"].get(id_field))
        if row_id and row_id not in row_by_id:
            row_by_id[row_id] = row

    for row in rows:
        row_id = comparable(row["data"].get(id_field))
        parent_id = comparable(row["data"].get(parent_field))
        if row_id is None or parent_id is None:
            continue

        if row_id == parent_id:
            _add_indexed_issue(indexed_issues, entity_name, row, parent_field, message)
            continue

        seen = {row_id}
        current_parent = parent_id
        while current_parent:
            if current_parent in seen:
                _add_indexed_issue(indexed_issues, entity_name, row, parent_field, message)
                break
            seen.add(current_parent)
            parent_row = row_by_id.get(current_parent)
            if parent_row is None:
                break
            current_parent = comparable(parent_row["data"].get(parent_field))


def _evaluate_child_count_lte_reference(
    indexed_issues: IndexedIssues,
    entity_name: str,
    rows: StagedRows,
    rule: dict[str, Any],
    staged_entities: StagedEntities,
):
    child_entity = str(rule.get("child_entity", "")).strip()
    parent_lookup_field = str(rule.get("parent_lookup_field", "")).strip()
    child_lookup_field = str(rule.get("child_lookup_field", "")).strip()
    limit_field = str(rule.get("limit_field", "")).strip()
    if not child_entity or not parent_lookup_field or not child_lookup_field or not limit_field:
        return

    child_rows = staged_entities.get(child_entity, {}).get("rows", [])
    child_counts: dict[str, int] = defaultdict(int)
    for child_row in child_rows:
        child_key = comparable(child_row["data"].get(child_lookup_field))
        if child_key is not None:
            child_counts[child_key] += 1

    for row in rows:
        parent_key = comparable(row["data"].get(parent_lookup_field))
        raw_limit = comparable(row["data"].get(limit_field))
        if parent_key is None or raw_limit is None:
            continue

        try:
            limit_value = int(float(raw_limit))
        except ValueError:
            continue

        child_count = child_counts.get(parent_key, 0)
        if child_count > limit_value:
            message = str(
                rule.get(
                    "message",
                    f"Related {child_entity} count ({child_count}) exceeds {limit_field} ({limit_value}).",
                )
            )
            _add_indexed_issue(indexed_issues, entity_name, row, limit_field, message)


def _add_indexed_issue(
    indexed_issues: IndexedIssues,
    entity_name: str,
    row: dict[str, Any],
    field_name: str,
    reason: str,
):
    key = (entity_name, row["source_file"], row["row_number"])
    indexed_issues.setdefault(key, []).append((field_name, reason))
