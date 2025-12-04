"""Serialization and deserialization of components to/from disk."""

import json
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

import polars as pl

if TYPE_CHECKING:
    from .base import BaseComponent

# File extension for saved components
COMPONENT_EXTENSION = ".svcomp"


def save_component(component: 'BaseComponent', filepath: str) -> None:
    """
    Save a component to disk as a .svcomp zip file.

    The archive contains:
        - metadata.json: Component type, interactivity mapping, and config
        - data/*.parquet: Preprocessed data as parquet files

    Args:
        component: The component instance to save
        filepath: Path to save the component file
    """
    filepath = Path(filepath)
    if not filepath.suffix:
        filepath = filepath.with_suffix(COMPONENT_EXTENSION)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        data_dir = tmpdir / 'data'
        data_dir.mkdir()

        # Build metadata
        metadata: Dict[str, Any] = {
            'component_type': component._component_type,
            'interactivity': component._interactivity,
            'config': _serialize_config(component._config),
            'data_files': {},
            'data_values': {},
        }

        # Save preprocessed data
        for key, value in component._preprocessed_data.items():
            if isinstance(value, pl.LazyFrame):
                # Collect and save as parquet
                parquet_path = data_dir / f'{key}.parquet'
                value.collect().write_parquet(parquet_path)
                metadata['data_files'][key] = f'data/{key}.parquet'
            elif isinstance(value, pl.DataFrame):
                # Save as parquet
                parquet_path = data_dir / f'{key}.parquet'
                value.write_parquet(parquet_path)
                metadata['data_files'][key] = f'data/{key}.parquet'
            elif _is_json_serializable(value):
                # Store simple values in metadata
                metadata['data_values'][key] = value
            else:
                # Skip non-serializable values with a warning
                import warnings
                warnings.warn(
                    f"Skipping non-serializable preprocessed data key '{key}' "
                    f"of type {type(value).__name__}"
                )

        # Write metadata
        metadata_path = tmpdir / 'metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Create zip archive
        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in tmpdir.rglob('*'):
                if file.is_file():
                    zf.write(file, file.relative_to(tmpdir))


def load_component(filepath: str) -> 'BaseComponent':
    """
    Load a component from a .svcomp file.

    Args:
        filepath: Path to the saved component file

    Returns:
        Reconstructed component instance with preprocessed data loaded
    """
    from .registry import get_component_class

    filepath = Path(filepath)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Extract archive
        with zipfile.ZipFile(filepath, 'r') as zf:
            zf.extractall(tmpdir)

        # Load metadata
        metadata_path = tmpdir / 'metadata.json'
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

        # Get the component class
        component_cls = get_component_class(metadata['component_type'])

        # Create component instance without running __init__
        component = object.__new__(component_cls)

        # Restore attributes
        component._interactivity = metadata['interactivity']
        component._config = _deserialize_config(metadata['config'])
        component._preprocessed_data = {}

        # Load data values from metadata
        for key, value in metadata.get('data_values', {}).items():
            component._preprocessed_data[key] = value

        # Load parquet files as LazyFrames
        for key, rel_path in metadata.get('data_files', {}).items():
            parquet_path = tmpdir / rel_path
            # Read into memory and convert to LazyFrame
            # (We read here because the tmpdir will be deleted)
            df = pl.read_parquet(parquet_path)
            component._preprocessed_data[key] = df.lazy()

        # Set raw_data to None since we loaded from preprocessed
        component._raw_data = None

        return component


def _serialize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialize config dict for JSON storage.

    Handles special types that aren't directly JSON serializable.
    """
    result = {}
    for key, value in config.items():
        if _is_json_serializable(value):
            result[key] = value
        elif isinstance(value, (list, tuple)):
            # Try to serialize list items
            serialized_list = []
            for item in value:
                if _is_json_serializable(item):
                    serialized_list.append(item)
                elif isinstance(item, dict):
                    serialized_list.append(_serialize_config(item))
                else:
                    serialized_list.append(str(item))
            result[key] = serialized_list
        elif isinstance(value, dict):
            result[key] = _serialize_config(value)
        else:
            # Convert to string as fallback
            result[key] = str(value)
    return result


def _deserialize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deserialize config dict from JSON storage.

    Currently just returns as-is since we serialize to JSON-compatible format.
    """
    return config


def _is_json_serializable(value: Any) -> bool:
    """Check if a value is directly JSON serializable."""
    if value is None:
        return True
    if isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_serializable(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(k, str) and _is_json_serializable(v)
            for k, v in value.items()
        )
    return False
