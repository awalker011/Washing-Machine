from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None

CONFIG_SUFFIXES = {".json", ".yaml", ".yml"}


def load_config(path: str | Path) -> dict:
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()

    if suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("YAML config support requires PyYAML to be installed.")
        data = yaml.safe_load(text) or {}
    else:
        raise ValueError(f"Unsupported config format: {config_path}")

    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain an object at the top level: {config_path}")

    data.setdefault("_meta", {})
    data["_meta"]["path"] = str(config_path)
    return data


def find_config_files(path: str | Path) -> list[Path]:
    base = Path(path)
    if not base.exists():
        raise FileNotFoundError(f"Config path does not exist: {base}")

    if base.is_file():
        if base.suffix.lower() not in CONFIG_SUFFIXES:
            raise ValueError(f"Unsupported config format: {base}")
        return [base]

    files = sorted(
        file_path
        for file_path in base.rglob("*")
        if file_path.is_file() and file_path.suffix.lower() in CONFIG_SUFFIXES
    )
    return files


def load_named_configs(path: str | Path, key_name: str = "entity_name") -> dict[str, dict]:
    configs: dict[str, dict] = {}
    for config_file in find_config_files(path):
        config = load_config(config_file)
        name = str(config.get(key_name) or config_file.stem)

        if name in configs:
            existing_path = configs[name].get("_meta", {}).get("path", "<unknown>")
            raise ValueError(
                f"Duplicate config name '{name}' found in '{existing_path}' and '{config_file}'."
            )

        configs[name] = config
    return configs
