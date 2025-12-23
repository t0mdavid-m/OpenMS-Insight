"""Component type registry for serialization and deserialization."""

from typing import TYPE_CHECKING, Dict, Type

if TYPE_CHECKING:
    from .base import BaseComponent

# Global registry mapping component type names to their classes
_COMPONENT_REGISTRY: Dict[str, Type["BaseComponent"]] = {}


def register_component(name: str):
    """
    Decorator to register a component class in the registry.

    Args:
        name: Unique name for the component type (e.g., 'table', 'lineplot')

    Returns:
        Decorator function

    Example:
        @register_component("table")
        class Table(BaseComponent):
            ...
    """

    def decorator(cls: Type["BaseComponent"]) -> Type["BaseComponent"]:
        if name in _COMPONENT_REGISTRY:
            raise ValueError(
                f"Component type '{name}' is already registered to "
                f"{_COMPONENT_REGISTRY[name].__name__}"
            )
        _COMPONENT_REGISTRY[name] = cls
        cls._component_type = name
        return cls

    return decorator


def get_component_class(name: str) -> Type["BaseComponent"]:
    """
    Get a component class by its registered name.

    Args:
        name: The registered component type name

    Returns:
        The component class

    Raises:
        KeyError: If no component is registered with that name
    """
    if name not in _COMPONENT_REGISTRY:
        available = list(_COMPONENT_REGISTRY.keys())
        raise KeyError(
            f"No component registered with name '{name}'. "
            f"Available components: {available}"
        )
    return _COMPONENT_REGISTRY[name]


def list_registered_components() -> Dict[str, Type["BaseComponent"]]:
    """
    Get all registered component types.

    Returns:
        Dict mapping component names to their classes
    """
    return _COMPONENT_REGISTRY.copy()


def is_registered(name: str) -> bool:
    """
    Check if a component type is registered.

    Args:
        name: The component type name to check

    Returns:
        True if registered, False otherwise
    """
    return name in _COMPONENT_REGISTRY
