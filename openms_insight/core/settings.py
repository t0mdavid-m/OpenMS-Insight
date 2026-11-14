"""Settings of a plot in its toolbar: ``toolbar_settings``.

A plot given ``toolbar_settings=[...]`` gets a gear button in its toolbar whose menu
holds the settings. A setting writes its value to a selection identifier of
the plot's ``StateManager``, so the caller reads it back with
``state_manager.get_selection(identifier)`` (``setting_value`` falls back to
the default) and builds the plot's data from it on the next run. Render-time
only, never part of the cache configuration.

Each setting is a dict:

- ``{"identifier", "label", "kind": "choice", "options": [values or
  {"value", "label"}], "default"}``: one value out of a few;
- ``{"identifier", "label", "kind": "range", "min", "max", "step"?,
  "default"}``: a number picked with a slider;
- ``{"identifier", "label", "kind": "toggle", "default"}``: on or off.
"""

from typing import Any

KINDS = ("choice", "range", "toggle")


def validate_settings(settings: Any) -> list[dict[str, Any]] | None:
    """Check ``settings`` and return them in the form the browser reads."""
    if settings is None:
        return None
    if not isinstance(settings, (list, tuple)):
        raise ValueError(f"settings must be a list of dicts, got {settings!r}")
    out = []
    seen = set()
    for setting in settings:
        if not isinstance(setting, dict):
            raise ValueError(f"a setting must be a dict, got {setting!r}")
        identifier = setting.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"a setting needs an identifier, got {setting!r}")
        if identifier in seen:
            raise ValueError(f"setting identifier {identifier!r} given twice")
        seen.add(identifier)
        kind = setting.get("kind", "choice")
        if kind not in KINDS:
            raise ValueError(f"setting kind must be one of {KINDS}, got {kind!r}")
        entry = {
            "identifier": identifier,
            "label": str(setting.get("label") or identifier),
            "kind": kind,
            "default": setting.get("default"),
        }
        if kind == "choice":
            options = []
            for option in setting.get("options") or []:
                if isinstance(option, dict):
                    options.append(
                        {
                            "value": option["value"],
                            "label": str(option.get("label", option["value"])),
                        }
                    )
                else:
                    options.append({"value": option, "label": str(option)})
            if not options:
                raise ValueError(f"choice setting {identifier!r} has no options")
            entry["options"] = options
            if entry["default"] is None:
                entry["default"] = options[0]["value"]
        elif kind == "range":
            for bound in ("min", "max"):
                if not isinstance(setting.get(bound), (int, float)):
                    raise ValueError(
                        f"range setting {identifier!r} needs a number {bound}"
                    )
            entry.update(
                min=setting["min"], max=setting["max"], step=setting.get("step") or 1
            )
            if entry["default"] is None:
                entry["default"] = setting["min"]
        else:
            entry["default"] = bool(entry["default"])
        out.append(entry)
    return out or None


def setting_value(state_manager: Any, setting: dict[str, Any]) -> Any:
    """The value of ``setting`` in ``state_manager``, else its default."""
    value = (
        state_manager.get_selection(setting["identifier"])
        if state_manager is not None
        else None
    )
    return setting.get("default") if value is None else value
