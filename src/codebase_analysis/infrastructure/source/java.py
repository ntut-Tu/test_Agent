"""Parse Java declarations using a syntax tree without executing repository code."""

import tree_sitter_java
from tree_sitter import Language, Node, Parser

from codebase_analysis.domain.context import SourceMethod
from codebase_analysis.infrastructure.errors import RemoteError

_CLASS_NODES = {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}
_METHOD_NODES = {"method_declaration", "constructor_declaration", "compact_constructor_declaration"}
_TEST_ANNOTATIONS = {"Test", "ParameterizedTest", "RepeatedTest", "TestFactory", "TestTemplate", "Theory"}


class JavaSourceAnalyzer:
    """Extract methods, overload identities and existing-test file context."""

    def __init__(self) -> None:
        """Initialize the Java grammar parser."""
        self.parser = Parser(Language(tree_sitter_java.language()))

    def parse(self, path: str, content: str) -> tuple[SourceMethod, ...]:
        """Extract declarations from one Java file.

        Args:
            path: Repository-relative .java path.
            content: Source decoded from the pinned commit.

        Returns:
            Methods with their full declaring file for imports, fixtures,
            Spring annotations and helper definitions.

        Raises:
            RemoteError: Java syntax cannot be parsed without error recovery.
        """
        data = content.encode("utf-8")
        root = self.parser.parse(data).root_node
        if root.has_error:
            raise RemoteError(f"Cannot parse Java source: {path}")

        def text(node: Node | None) -> str:
            return data[node.start_byte:node.end_byte].decode("utf-8") if node else ""

        package = ""
        for child in root.named_children:
            if child.type == "package_declaration":
                names = [n for n in child.named_children if n.type in {"identifier", "scoped_identifier"}]
                package = text(names[-1]) if names else ""

        methods = []

        def visit(node: Node, owners: tuple[str, ...], junit3: bool = False) -> None:
            if node.type in _CLASS_NODES:
                owners = (*owners, text(node.child_by_field_name("name")))
                superclass = text(node.child_by_field_name("superclass"))
                junit3 = superclass.endswith("TestCase")
            elif node.type == "class_body" and node.parent and node.parent.type == "object_creation_expression":
                owners = (*owners, f"anonymous@{node.start_point.row + 1}")
            if node.type in _METHOD_NODES and node.child_by_field_name("body") is not None:
                name = text(node.child_by_field_name("name"))
                annotations = set()
                for modifiers in node.named_children:
                    if modifiers.type == "modifiers":
                        for annotation in modifiers.named_children:
                            if annotation.type in {"annotation", "marker_annotation"}:
                                annotations.add(text(annotation.child_by_field_name("name")).rsplit(".", 1)[-1])
                methods.append(SourceMethod(
                    path, ".".join(part for part in (package, *owners) if part), name,
                    text(node.child_by_field_name("parameters")) or "()",
                    node.start_point.row + 1, node.end_point.row + 1,
                    text(node), bool(annotations & _TEST_ANNOTATIONS) or (junit3 and name.startswith("test")),
                    content,
                ))
            for child in node.named_children:
                visit(child, owners, junit3)

        visit(root, ())
        return tuple(methods)
