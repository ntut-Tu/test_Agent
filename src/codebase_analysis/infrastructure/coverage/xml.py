"""Normalize JaCoCo and Cobertura XML into domain coverage types."""

import xml.etree.ElementTree as ET
from collections import defaultdict

from codebase_analysis.domain.models import CoverageReport, FileCoverage
from codebase_analysis.infrastructure.errors import RemoteError


def _jacoco_packages(element: ET.Element, groups: tuple[str, ...] = ()):
    for child in element:
        if child.tag == "group":
            yield from _jacoco_packages(child, (*groups, child.get("name", "")))
        elif child.tag == "package":
            yield "/".join(part for part in (*groups, child.get("name", "")) if part), child


def parse_coverage(xml_data: bytes) -> CoverageReport:
    """Parse source paths and uncovered line numbers from a coverage artifact.

    JaCoCo lines are uncovered when mi > 0 and ci == 0; Cobertura lines are
    uncovered when hits == 0. Files with no uncovered lines are preserved.

    Args:
        xml_data: JaCoCo report or Cobertura coverage XML bytes.

    Returns:
        Normalized entries using source paths recorded in the XML.

    Raises:
        RemoteError: XML is malformed or its root element is unsupported.
        ValueError: A numeric line attribute cannot be converted to an integer.
        KeyError: A required uncovered-line number is missing.
    """
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        raise RemoteError("Coverage artifact is not valid XML") from exc
    result: dict[str, set[int]] = defaultdict(set)
    executable: dict[str, set[int]] = defaultdict(set)
    covered: dict[str, set[int]] = defaultdict(set)
    if root.tag == "report":  # JaCoCo XML
        for prefix, package in _jacoco_packages(root):
            for source in package.findall("sourcefile"):
                name = source.get("name")
                if not name:
                    continue
                path = f"{prefix}/{name}".lstrip("/")
                uncovered = result[path]  # Preserve files whose lines are all covered.
                for line in source.findall("line"):
                    number = int(line.attrib["nr"])
                    if int(line.get("mi", "0")) + int(line.get("ci", "0")) > 0:
                        executable[path].add(number)
                    if int(line.get("mi", "0")) > 0 and int(line.get("ci", "0")) == 0:
                        uncovered.add(number)
                    elif int(line.get("ci", "0")) > 0:
                        covered[path].add(number)
    elif root.tag == "coverage":  # Cobertura XML
        for klass in root.findall(".//class"):
            path = klass.get("filename")
            if not path:
                continue
            uncovered = result[path]
            for line in klass.findall("./lines/line"):
                number = int(line.attrib["number"])
                executable[path].add(number)
                if int(line.get("hits", "0")) == 0:
                    uncovered.add(number)
                else:
                    covered[path].add(number)
    else:
        raise RemoteError(f"Unsupported coverage XML root: {root.tag}")
    return CoverageReport(tuple(
        FileCoverage(path, frozenset(lines - covered[path]), frozenset(executable[path]))
        for path, lines in result.items()
    ))
