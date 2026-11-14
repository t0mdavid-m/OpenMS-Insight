"""Copy the Universal Spectrum Identifier (USI) of the shown spectrum: ``usi``.

A plot given ``usi`` gets a **USI** button in its toolbar that copies the
identifier of the spectrum it shows, for example to look it up in a
repository or to cite it. ``usi`` is a USI as defined by the HUPO-PSI
(``mzspec:<collection>:<run>:<index type>:<index>[:<interpretation>]``) in
which any part may be a placeholder ``{identifier}``, filled with the value the
shared state holds under that identifier when the button is clicked:

    LinePlot(..., filters={"spectrum": "scan_id"},
             usi="mzspec:PXD000561:Adult_Frontalcortex_bRP_Elite_85_f09:scan:{spectrum}")

While a placeholder has no value (nothing selected yet) the button is shown
disabled. ``usi`` is a render-time argument, never part of the cache
configuration.
"""

import re
from typing import Any

#: A placeholder: ``{identifier}``, the identifier without braces.
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")

#: Index types a USI may use (case as in the specification).
_INDEX_TYPES = {"scan", "index", "nativeid", "trace"}


def usi_placeholders(template: str) -> list[str]:
    """The state identifiers named by the placeholders of ``template``, in order."""
    return [m.group(1) for m in _PLACEHOLDER.finditer(template)]


def validate_usi(usi: Any) -> str | None:
    """Check ``usi`` is a USI, placeholders allowed, and return it stripped, or None."""
    if usi is None:
        return None
    if not isinstance(usi, str):
        raise ValueError(f"usi must be a string or None, got {type(usi).__name__}")
    usi = usi.strip()
    names = usi_placeholders(usi)
    if any(not name.strip() or name != name.strip() for name in names):
        raise ValueError(
            f"usi placeholders must name a state identifier, e.g. '{{spectrum}}', got {usi!r}"
        )
    rest = _PLACEHOLDER.sub("x", usi)
    if "{" in rest or "}" in rest:
        raise ValueError(f"usi has an unmatched brace: {usi!r}")
    parts = rest.split(":")
    if len(parts) < 5 or parts[0].lower() != "mzspec" or not all(parts[1:5]):
        raise ValueError(
            "usi must look like 'mzspec:<collection>:<run>:<index type>:<index>"
            f"[:<interpretation>]', got {usi!r}"
        )
    index_type = usi.split(":")[3]
    if (
        not _PLACEHOLDER.fullmatch(index_type)
        and index_type.lower() not in _INDEX_TYPES
    ):
        raise ValueError(
            "the index type of a usi must be scan, index, nativeId or trace, "
            f"got {index_type!r}"
        )
    return usi


def usi_args(usi: str | None) -> dict[str, Any]:
    """The Vue argument: the USI template, if one is set."""
    return {"usi": usi} if usi else {}
