import ast
import sys
import unittest
from importlib.util import resolve_name
from pathlib import Path


class ArchitectureTests(unittest.TestCase):
    def test_core_layers_do_not_import_frameworks_or_outer_layers(self):
        root = Path(__file__).parents[1] / "src" / "codebase_analysis"
        for layer, allowed in [
            ("domain", {"domain"}),
            ("application", {"domain", "application"}),
        ]:
            for path in (root / layer).rglob("*.py"):
                package = ".".join(("codebase_analysis", *path.relative_to(root).parts[:-1]))
                for node in ast.walk(ast.parse(path.read_text())):
                    if isinstance(node, ast.Import):
                        modules = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        name = "." * node.level + (node.module or "")
                        modules = [resolve_name(name, package) if node.level else name]
                    else:
                        continue
                    for module in modules:
                        with self.subTest(path=str(path), dependency=module):
                            parts = module.split(".")
                            if parts[0] == "codebase_analysis":
                                self.assertGreater(len(parts), 1)
                                self.assertIn(parts[1], allowed)
                            else:
                                self.assertIn(parts[0], sys.stdlib_module_names)
