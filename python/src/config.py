"""Configuration loading and validation."""

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${ENV_VAR} placeholders in config values."""
    if isinstance(value, str):
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, value)
        for var_name in matches:
            env_val = os.getenv(var_name, "")
            value = value.replace(f"${{{var_name}}}", env_val)
        return value
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def merge_configs(base: dict, overlay: dict) -> dict:
    """Deep merge overlay into base. Overlay values win."""
    merged = base.copy()
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str = None, overlay_path: str = None, env_file: str = ".env") -> Dict[str, Any]:
    """Load configuration from YAML file with environment variable resolution.

    Args:
        config_path: Path to YAML config file. Defaults to src/config/default.yaml.
        overlay_path: Optional path to overlay YAML that merges on top of base config.
        env_file: Path to .env file for environment variables.

    Returns:
        Resolved configuration dictionary.
    """
    load_dotenv(env_file)

    if config_path is None:
        config_path = str(Path(__file__).parent / "config" / "default.yaml")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if overlay_path and os.path.exists(overlay_path):
        with open(overlay_path) as f:
            overlay = yaml.safe_load(f)
        if overlay:
            config = merge_configs(config, overlay)

    config = _resolve_env_vars(config)
    return config


def get_config(config: Dict, *keys: str, default: Any = None) -> Any:
    """Safely get a nested config value.

    Usage: get_config(config, "risk", "max_position_pct", default=3.0)
    """
    current = config
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current
