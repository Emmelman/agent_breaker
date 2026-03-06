"""
Config loader for agent-breaker-hybrid.
Reads config.yaml and provides access to project settings.
"""
from pathlib import Path
import yaml


def load_config(config_path: str = "config.yaml") -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file (relative to working directory)

    Returns:
        Configuration dict

    Raises:
        FileNotFoundError: If config file does not exist
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
