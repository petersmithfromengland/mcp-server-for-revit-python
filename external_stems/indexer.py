# -*- coding: utf-8 -*-
"""
Indexes a Python library by parsing AST to extract:
- Module paths
- Function signatures
- Class definitions
- Docstrings
- Parameter types

This avoids copying code — the index points to the original source.
"""

import ast
import os
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict


@dataclass
class FunctionInfo:
    name: str
    module_path: str  # e.g. "duHast.Revit.Walls.walls"
    file_path: str  # absolute path to .py file
    line_number: int
    docstring: Optional[str] = None
    parameters: List[Dict] = field(default_factory=list)  # [{name, type_hint, default}]
    returns: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    is_method: bool = False
    class_name: Optional[str] = None
    requires_doc: bool = False  # True if 'doc' is a parameter
    requires_transaction: bool = False  # heuristic: contains Transaction usage
    category: str = ""  # derived from module path


@dataclass
class ClassInfo:
    name: str
    module_path: str
    file_path: str
    line_number: int
    docstring: Optional[str] = None
    methods: List[FunctionInfo] = field(default_factory=list)
    base_classes: List[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    module_path: str
    file_path: str
    docstring: Optional[str] = None
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)


@dataclass
class LibraryIndex:
    name: str
    root_path: str
    modules: List[ModuleInfo] = field(default_factory=list)
    _function_lookup: Dict[str, FunctionInfo] = field(default_factory=dict, repr=False)

    def build_lookup(self):
        """Build fast lookup tables after indexing."""
        self._function_lookup.clear()
        for mod in self.modules:
            for func in mod.functions:
                key = f"{mod.module_path}.{func.name}"
                self._function_lookup[key] = func
            for cls in mod.classes:
                for method in cls.methods:
                    key = f"{mod.module_path}.{cls.name}.{method.name}"
                    self._function_lookup[key] = method

    def search(self, query: str, max_results: int = 20) -> List[FunctionInfo]:
        """Search functions by name, docstring, or module path."""
        query_lower = query.lower()
        results = []
        for key, func in self._function_lookup.items():
            score = 0
            if query_lower in func.name.lower():
                score += 10
            if query_lower in key.lower():
                score += 5
            if func.docstring and query_lower in func.docstring.lower():
                score += 3
            if func.category and query_lower in func.category.lower():
                score += 2
            if score > 0:
                results.append((score, func))
        results.sort(key=lambda x: -x[0])
        return [f for _, f in results[:max_results]]

    def get_by_category(self, category: str) -> List[FunctionInfo]:
        """Get all functions in a category (e.g. 'Walls', 'Views')."""
        cat_lower = category.lower()
        return [
            f for f in self._function_lookup.values() if cat_lower in f.category.lower()
        ]

    def get_requires_doc(self) -> List[FunctionInfo]:
        """Get all functions that take a Revit document parameter."""
        return [f for f in self._function_lookup.values() if f.requires_doc]

    @property
    def total_functions(self) -> int:
        return len(self._function_lookup)


def _extract_param_info(arg: ast.arg) -> Dict:
    """Extract parameter name and type hint from AST arg node."""
    info = {"name": arg.arg}
    if arg.annotation:
        try:
            info["type_hint"] = ast.dump(arg.annotation)
        except Exception:
            pass
    return info


def _check_requires_transaction(node: ast.FunctionDef, source_lines: List[str]) -> bool:
    """Heuristic: check if function body references Transaction."""
    start = node.lineno - 1
    end = (
        node.end_lineno
        if hasattr(node, "end_lineno") and node.end_lineno
        else start + 50
    )
    body_text = "\n".join(source_lines[start:end])
    return "Transaction(" in body_text or "in_transaction" in body_text


def _derive_category(module_path: str) -> str:
    """Derive a category from the module path.

    duHast.Revit.Walls.walls -> Walls
    """
    parts = module_path.split(".")
    for i, part in enumerate(parts):
        if part == "Revit" and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1] if parts else "Unknown"


def index_module(file_path: str, module_path: str) -> Optional[ModuleInfo]:
    """Parse a single Python file and extract its API surface."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
            source_lines = source.splitlines()
    except Exception:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    module = ModuleInfo(
        module_path=module_path,
        file_path=file_path,
        docstring=ast.get_docstring(tree),
    )

    category = _derive_category(module_path)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module.imports.append(node.module)

        elif isinstance(node, ast.FunctionDef):
            if node.name.startswith("_"):
                continue  # skip private functions

            params = [_extract_param_info(a) for a in node.args.args]

            # Apply defaults (right-aligned)
            defaults = node.args.defaults
            if defaults:
                offset = len(params) - len(defaults)
                for i, d in enumerate(defaults):
                    try:
                        params[offset + i]["default"] = ast.literal_eval(d)
                    except (ValueError, TypeError):
                        params[offset + i]["default"] = "..."

            func = FunctionInfo(
                name=node.name,
                module_path=module_path,
                file_path=file_path,
                line_number=node.lineno,
                docstring=ast.get_docstring(node),
                parameters=params,
                requires_doc=any(p["name"] == "doc" for p in params),
                requires_transaction=_check_requires_transaction(node, source_lines),
                decorators=[ast.dump(d) for d in node.decorator_list],
                category=category,
            )

            # Return type
            if node.returns:
                try:
                    func.returns = ast.dump(node.returns)
                except Exception:
                    pass

            module.functions.append(func)

        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue

            cls = ClassInfo(
                name=node.name,
                module_path=module_path,
                file_path=file_path,
                line_number=node.lineno,
                docstring=ast.get_docstring(node),
                base_classes=[ast.dump(b) for b in node.bases],
            )

            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    params = [
                        _extract_param_info(a)
                        for a in item.args.args
                        if a.arg != "self"
                    ]
                    method = FunctionInfo(
                        name=item.name,
                        module_path=module_path,
                        file_path=file_path,
                        line_number=item.lineno,
                        docstring=ast.get_docstring(item),
                        parameters=params,
                        is_method=True,
                        class_name=node.name,
                        requires_doc=any(p["name"] == "doc" for p in params),
                        requires_transaction=_check_requires_transaction(
                            item, source_lines
                        ),
                        category=category,
                    )
                    cls.methods.append(method)

            module.classes.append(cls)

    return module


def index_library(root_path: str, package_name: str = "duHast") -> LibraryIndex:
    """Recursively index all Python files under root_path.

    Args:
        root_path: Absolute path to the library root
                   (e.g. duHast/Revit or site-packages/duHast)
        package_name: Base package name for module path construction
    """
    index = LibraryIndex(name=package_name, root_path=root_path)

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Skip __pycache__, .git, etc.
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "__"))]

        for filename in filenames:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            file_path = os.path.join(dirpath, filename)

            # Build module path from the relative path
            rel_path = os.path.relpath(file_path, os.path.dirname(root_path))
            module_path = rel_path.replace(os.sep, ".").replace(".py", "")
            # Ensure it starts with the package name
            if not module_path.startswith(package_name):
                module_path = f"{package_name}.{module_path}"

            mod = index_module(file_path, module_path)
            if mod and (mod.functions or mod.classes):
                index.modules.append(mod)

    index.build_lookup()
    return index


def save_index(index: LibraryIndex, output_path: str) -> None:
    """Save index to JSON for fast loading."""
    data = {
        "name": index.name,
        "root_path": index.root_path,
        "module_count": len(index.modules),
        "function_count": len(index._function_lookup),
        "modules": [],
    }
    for mod in index.modules:
        mod_data = {
            "module_path": mod.module_path,
            "file_path": mod.file_path,
            "docstring": mod.docstring,
            "functions": [asdict(f) for f in mod.functions],
            "classes": [asdict(c) for c in mod.classes],
        }
        data["modules"].append(mod_data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def load_index(index_path: str) -> LibraryIndex:
    """Load a previously saved index from JSON."""
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    index = LibraryIndex(name=data["name"], root_path=data["root_path"])

    _valid_func_fields = set(FunctionInfo.__dataclass_fields__)
    _valid_cls_fields = set(ClassInfo.__dataclass_fields__)

    for mod_data in data["modules"]:
        mod = ModuleInfo(
            module_path=mod_data["module_path"],
            file_path=mod_data["file_path"],
            docstring=mod_data.get("docstring"),
        )
        for fd in mod_data.get("functions", []):
            mod.functions.append(
                FunctionInfo(**{k: v for k, v in fd.items() if k in _valid_func_fields})
            )
        for cd in mod_data.get("classes", []):
            methods = []
            for md in cd.get("methods", []):
                methods.append(
                    FunctionInfo(
                        **{k: v for k, v in md.items() if k in _valid_func_fields}
                    )
                )
            cls = ClassInfo(
                name=cd["name"],
                module_path=cd["module_path"],
                file_path=cd["file_path"],
                line_number=cd["line_number"],
                docstring=cd.get("docstring"),
                methods=methods,
                base_classes=cd.get("base_classes", []),
            )
            mod.classes.append(cls)
        index.modules.append(mod)

    index.build_lookup()
    return index
