# -*- coding: utf-8 -*-
"""
Stem registry - manages all available code stems.

Each stem is a dict with:
  - id: unique identifier (e.g. "query.elements_by_category")
  - name: human-readable name
  - category: grouping category ("query", "modify", "view", "transaction")
  - description: what the stem does
  - parameters: list of parameter definitions
  - code_template: IronPython code with {param} placeholders
  - requires_transaction: whether the stem modifies the model
"""

from typing import Dict, List, Optional, Any
import re

# Singleton registry
_registry = None


class StemParameter:
    """Definition of a parameter that a stem accepts."""

    def __init__(
        self,
        name: str,
        param_type: str,
        description: str,
        required: bool = True,
        default: Any = None,
        choices: List[str] = None,
    ):
        self.name = name
        self.param_type = param_type  # "str", "int", "float", "bool", "list"
        self.description = description
        self.required = required
        self.default = default
        self.choices = choices

    def to_dict(self) -> Dict:
        d = {
            "name": self.name,
            "type": self.param_type,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            d["default"] = self.default
        if self.choices:
            d["choices"] = self.choices
        return d

    def validate(self, value: Any) -> Any:
        """Validate and coerce a parameter value."""
        if value is None:
            if self.required and self.default is None:
                raise ValueError(f"Parameter '{self.name}' is required")
            return self.default

        if self.choices and str(value) not in [str(c) for c in self.choices]:
            raise ValueError(
                f"Parameter '{self.name}' must be one of {self.choices}, got '{value}'"
            )

        # Type coercion
        try:
            if self.param_type == "int":
                return int(value)
            elif self.param_type == "float":
                return float(value)
            elif self.param_type == "bool":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
            elif self.param_type == "list":
                if isinstance(value, str):
                    return [v.strip() for v in value.split(",")]
                return list(value)
            else:
                return str(value)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Parameter '{self.name}' expected type '{self.param_type}': {e}"
            )


class Stem:
    """A single code building block."""

    def __init__(
        self,
        stem_id: str,
        name: str,
        category: str,
        description: str,
        code_template: str,
        parameters: List[StemParameter] = None,
        requires_transaction: bool = False,
        output_description: str = "",
    ):
        self.id = stem_id
        self.name = name
        self.category = category
        self.description = description
        self.code_template = code_template
        self.parameters = parameters or []
        self.requires_transaction = requires_transaction
        self.output_description = output_description

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "requires_transaction": self.requires_transaction,
            "output_description": self.output_description,
        }

    def render(self, params: Dict[str, Any] = None) -> str:
        """Render the code template with validated parameters.

        Uses safe string formatting — only declared parameter names are
        substituted.  Placeholders use the ``{param_name}`` syntax inside
        the code template.  Doubled braces ``{{`` / ``}}`` are used to
        represent literal braces in IronPython code (e.g. for ``.format()``
        calls) and are unescaped after parameter substitution.
        """
        params = params or {}
        validated: Dict[str, Any] = {}

        for p in self.parameters:
            raw_value = params.get(p.name)
            validated[p.name] = p.validate(raw_value)

        # Only substitute known parameter names — ignore unknown braces
        code = self.code_template
        for key, val in validated.items():
            # Replace {key} with the value, using simple string replacement
            # to avoid issues with IronPython curly-brace code
            code = code.replace("{" + key + "}", str(val))

        # Unescape doubled braces: {{ -> { and }} -> }
        # These are used in templates to represent literal braces for
        # IronPython .format() calls
        code = code.replace("{{", "{").replace("}}", "}")

        return code


class StemRegistry:
    """Central registry of all available stems."""

    def __init__(self):
        self._stems: Dict[str, Stem] = {}

    def register(self, stem: Stem) -> None:
        """Register a stem. Overwrites if ID already exists."""
        self._stems[stem.id] = stem

    def get(self, stem_id: str) -> Optional[Stem]:
        """Look up a stem by ID."""
        return self._stems.get(stem_id)

    def list_all(self) -> List[Dict]:
        """Return all stems as dicts, sorted by category then name."""
        return [
            s.to_dict()
            for s in sorted(self._stems.values(), key=lambda s: (s.category, s.name))
        ]

    def list_by_category(self, category: str) -> List[Dict]:
        """Return stems in a given category."""
        return [
            s.to_dict()
            for s in sorted(self._stems.values(), key=lambda s: s.name)
            if s.category == category
        ]

    def categories(self) -> List[str]:
        """Return sorted list of unique categories."""
        return sorted({s.category for s in self._stems.values()})

    def search(self, query: str) -> List[Dict]:
        """Search stems by name or description (case-insensitive)."""
        q = query.lower()
        return [
            s.to_dict()
            for s in sorted(self._stems.values(), key=lambda s: (s.category, s.name))
            if q in s.name.lower() or q in s.description.lower()
        ]

    def render_stem(self, stem_id: str, params: Dict[str, Any] = None) -> str:
        """Render a single stem's code with parameters.

        If the stem requires a transaction, the code is automatically
        wrapped in one.
        """
        stem = self.get(stem_id)
        if not stem:
            raise ValueError(f"Unknown stem: '{stem_id}'")
        code = stem.render(params)

        if stem.requires_transaction:
            code = self._wrap_transaction(code, stem.name)

        return code

    def render_chain(self, steps: List[Dict]) -> str:
        """Render a chain of stems into a single code block.

        Each step is a dict: {"stem_id": "...", "params": {...}}
        Steps are concatenated in order. If any step requires a
        transaction, the whole chain is wrapped in a single transaction.
        """
        if not steps:
            raise ValueError("No steps provided")

        code_blocks = []
        needs_transaction = False

        for i, step in enumerate(steps):
            stem_id = step.get("stem_id")
            params = step.get("params", {})
            stem = self.get(stem_id)
            if not stem:
                raise ValueError(f"Unknown stem in step {i + 1}: '{stem_id}'")
            if stem.requires_transaction:
                needs_transaction = True
            code_blocks.append(
                f"# Step {i + 1}: {stem.name} (Stem ID: {stem.id})\n"
                + stem.render(params)
            )

        combined = "\n\n".join(code_blocks)

        if needs_transaction:
            combined = self._wrap_transaction(combined, "Stem chain")

        return combined

    @staticmethod
    def _wrap_transaction(code: str, description: str) -> str:
        """Wrap code in a Revit transaction with rollback on error."""
        indented = "\n".join("    " + line for line in code.splitlines())
        return (
            f't = DB.Transaction(doc, "{description}")\n'
            "t.Start()\n"
            "try:\n"
            f"{indented}\n"
            "    t.Commit()\n"
            "except:\n"
            "    t.RollBack()\n"
            "    raise"
        )


def get_registry() -> StemRegistry:
    """Get or create the singleton stem registry, loading all built-in stems."""
    global _registry
    if _registry is None:
        _registry = StemRegistry()
        _load_builtin_stems(_registry)
    return _registry


def _load_builtin_stems(registry: StemRegistry) -> None:
    """Import and register all built-in stem modules."""
    from .query_stems import register_query_stems
    from .modify_stems import register_modify_stems
    from .view_stems import register_view_stems
    from .wall_stems import register_wall_stems
    from .floor_ceiling_stems import register_floor_ceiling_stems
    from .room_stems import register_room_stems
    from .door_window_stems import register_door_window_stems
    from .family_stems import register_family_stems
    from .level_grid_stems import register_level_grid_stems
    from .parameter_stems import register_parameter_stems
    from .workset_phase_group_stems import register_workset_phase_group_stems
    from .material_link_stems import register_material_link_stems
    from .sheet_schedule_filter_stems import register_sheet_schedule_filter_stems
    from .color_stems import register_color_stems

    register_query_stems(registry)
    register_modify_stems(registry)
    register_view_stems(registry)
    register_wall_stems(registry)
    register_floor_ceiling_stems(registry)
    register_room_stems(registry)
    register_door_window_stems(registry)
    register_family_stems(registry)
    register_level_grid_stems(registry)
    register_parameter_stems(registry)
    register_workset_phase_group_stems(registry)
    register_material_link_stems(registry)
    register_sheet_schedule_filter_stems(registry)
    register_color_stems(registry)
