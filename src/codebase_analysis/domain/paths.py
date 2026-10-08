"""Maven Java source-role conventions used by collection."""


def is_java_test_path(path: str) -> bool:
    """Identify Java test candidates under Maven test roots or test filenames.

    Main-source roots take precedence so production classes named *Test are
    not treated as tests. Custom source layouts require adapting this policy.
    """
    if not path.endswith(".java") or "/src/main/java/" in "/" + path:
        return False
    name = path.rsplit("/", 1)[-1]
    return (
        "/src/test/" in "/" + path or "/src/it/" in "/" + path
        or name.startswith("Test") or name.endswith(("Test.java", "Tests.java", "IT.java", "ITCase.java"))
    )
