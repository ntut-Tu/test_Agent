"""Keep responsibility boundaries enforceable as the package grows."""

import ast
import sys
import unittest
from pathlib import Path


class ArchitectureTests(unittest.TestCase):
    def test_component_dependency_boundaries(self):
        root = Path(__file__).parents[1] / "src" / "codebase_analysis"
        rules = {
            "models": ({"models"}, set()),
            "interfaces.py": ({"models"}, set()),
            "lib/rules": ({"models", "lib.rules", "lib.errors"}, set()),
            "lib/parsers": ({"models", "schemas", "lib.errors"}, {"pydantic", "tree_sitter", "tree_sitter_java"}),
            "lib/clients": ({"lib.clients", "lib.errors"}, {"pydantic", "langchain_core"}),
            "tools": ({"models", "lib.clients", "lib.parsers", "lib.rules"}, set()),
            "prompts": ({"prompts"}, set()),
            "nodes": ({"models", "nodes", "prompts", "schemas.llm", "lib.clients.langchain", "lib.errors"}, set()),
            "schemas": ({"models"}, {"pydantic"}),
            "collection.py": ({"interfaces", "models", "lib.rules"}, set()),
            "workflow.py": ({"collection", "interfaces", "models", "lib.rules"}, set()),
            "repositories": ({"models", "repositories"}, set()),
            "tasks.py": ({"models", "repositories.base"}, set()),
            "controller.py": ({"tasks", "models", "schemas.http"}, {"fastapi"}),
            "worker.py": ({"tasks", "repositories.sqlite"}, set()),
            "smoke.py": ({"collection", "lib.rules"}, set()),
        }
        for component, (allowed, third_party) in rules.items():
            location = root / component
            files = [location] if location.is_file() else list(location.rglob("*.py"))
            self.assertTrue(files, f"Missing component: {component}")
            self.assertTrue(any(p.name != "__init__.py" for p in files))
            for path in files:
                for node in ast.walk(ast.parse(path.read_text())):
                    if isinstance(node, ast.Import):
                        modules = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        self.assertEqual(node.level, 0, f"Use absolute imports: {path}")
                        modules = [node.module or ""]
                    else:
                        continue
                    for module in modules:
                        with self.subTest(path=str(path.relative_to(root)), dependency=module):
                            if module.startswith("codebase_analysis."):
                                dependency = module.removeprefix("codebase_analysis.")
                                self.assertTrue(any(dependency == prefix or dependency.startswith(prefix + ".") for prefix in allowed))
                            else:
                                self.assertIn(module.split(".")[0], sys.stdlib_module_names | third_party)
