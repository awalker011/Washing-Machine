# Code Review Notes

## Refactors completed

### 1. Shared normalization logic
- Consolidated loose-text normalization into `transformers.normalize_loose_text()`.
- Removed duplicate alias-normalization behavior from multiple modules.

### 2. Safer logging serialization
- Added a shared row serializer for log output.
- Log generation now safely handles non-JSON-native Excel values such as dates/timestamps.

### 3. Less repetition in the pipeline
- Centralized repeated row-issue-to-error-log conversion in `_append_row_issues()`.
- Replaced repeated CSV column lists with named constants.
- Moved dataset-level business rules into `entity_rules.py` so the pipeline is easier to test.

### 4. Better config safety
- `load_named_configs()` now raises an error if two config files declare the same `entity_name`.

### 5. CLI cleanup
- Errors now print to stderr.
- JSON result output preserves Unicode characters.

## Test scaffold added
- `tests/test_transformers.py`
- `tests/test_validators.py`
- `tests/test_entity_rules.py`
- `tests/conftest.py`

These focus on the highest-risk normalization, relationship, and entity-rule behaviors.

## Remaining future refactors (optional)
- Continue splitting `pipeline.py` if import/export responsibilities keep growing.
- Add integration tests around full workbook runs once Python is available in the environment.
- Introduce typed data models / dataclasses if config complexity increases.
