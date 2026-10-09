import unittest

from codebase_analysis.lib.parsers.coverage import parse_coverage
from codebase_analysis.lib.rules.coverage import added_lines, match_coverage
from codebase_analysis.models.pull_request import ChangedFile


class CoverageTests(unittest.TestCase):
    def test_jacoco_aggregate_preserves_module_identity(self):
        xml = (
            b'<report><group name="a"><package name="demo"><sourcefile name="Mod.java">'
            b'<line nr="1" mi="1" ci="0"/></sourcefile></package></group>'
            b'<group name="b"><package name="demo"><sourcefile name="Mod.java">'
            b'<line nr="1" mi="0" ci="1"/></sourcefile></package></group></report>'
        )
        patch = "@@ -0,0 +1 @@\n+new"
        report = parse_coverage(xml)
        result = match_coverage(report, (ChangedFile("a/src/main/java/demo/Mod.java", "added", patch),))
        self.assertEqual([line.number for line in result.uncovered_lines], [1])
        self.assertEqual(result.covered_changed_count, 0)
        ambiguous = match_coverage(report, (ChangedFile("src/main/java/demo/Mod.java", "added", patch),))
        self.assertEqual(ambiguous.unmatched_paths, ("src/main/java/demo/Mod.java",))

    def test_patch_coverage_excludes_old_uncovered_lines_and_counts_executable_changes(self):
        xml = (
            b'<coverage><class filename="src/mod.py"><lines>'
            b'<line number="1" hits="0"/><line number="5" hits="0"/>'
            b'<line number="6" hits="2"/></lines></class></coverage>'
        )
        patch = "@@ -4,1 +4,4 @@\n same\n+uncovered\n+covered\n+# comment"
        result = match_coverage(parse_coverage(xml), (ChangedFile("src/mod.py", "modified", patch),))
        self.assertEqual([line.number for line in result.uncovered_lines], [5])
        self.assertEqual(result.changed_executable_count, 2)
        self.assertEqual(result.covered_changed_count, 1)

    def test_missing_patch_is_reported_instead_of_using_whole_file_coverage(self):
        xml = b'<coverage><class filename="src/mod.py"><lines><line number="5" hits="0"/></lines></class></coverage>'
        result = match_coverage(parse_coverage(xml), (ChangedFile("src/mod.py", "modified", None),))
        self.assertEqual(result.uncovered_lines, ())
        self.assertEqual(result.missing_patch_paths, ("src/mod.py",))

    def test_added_source_line_starting_with_plus_is_not_a_file_header(self):
        self.assertEqual(added_lines("@@ -1 +1,2 @@\n old\n+++counter"), {2})

    def test_repeated_cobertura_class_entries_merge_line_hits(self):
        xml = (
            b'<coverage><class filename="src/mod.py"><lines><line number="1" hits="0"/></lines></class>'
            b'<class filename="src/mod.py"><lines><line number="1" hits="2"/></lines></class></coverage>'
        )
        report = parse_coverage(xml)
        self.assertEqual(report.files[0].uncovered_numbers, frozenset())
        self.assertEqual(report.files[0].executable_numbers, frozenset({1}))

    def test_normalization_preserves_fully_covered_files(self):
        xml = b'<coverage><class filename="src/mod.py"><lines><line number="1" hits="2"/></lines></class></coverage>'
        report = parse_coverage(xml)
        result = match_coverage(report, (ChangedFile("src/mod.py", "modified", None),))
        self.assertEqual(len(report.files), 1)
        self.assertEqual(result.uncovered_lines, ())
        self.assertEqual(result.unmatched_paths, ())

    def test_added_lines_and_jacoco_match(self):
        patch = "@@ -4,2 +4,3 @@\n old\n+new\n-stale\n+more\n next"
        self.assertEqual(added_lines(patch), {5, 6})
        xml = b'<report><package name="pkg"><sourcefile name="mod.py"><line nr="5" mi="2" ci="0"/><line nr="6" mi="0" ci="1"/></sourcefile></package></report>'
        result = match_coverage(parse_coverage(xml), (ChangedFile("src/pkg/mod.py", "modified", patch),))
        self.assertEqual([(line.number, line.on_added_line) for line in result.uncovered_lines], [(5, True)])
        self.assertEqual(result.unmatched_paths, ())

    def test_cobertura_ambiguous_suffix_does_not_guess(self):
        xml = b'<coverage><packages><package><classes><class filename="a/mod.py"><lines><line number="3" hits="0"/></lines></class><class filename="b/mod.py"><lines><line number="7" hits="0"/></lines></class></classes></package></packages></coverage>'
        result = match_coverage(parse_coverage(xml), (ChangedFile("mod.py", "modified", None),))
        self.assertEqual(result.uncovered_lines, ())
        self.assertEqual(result.unmatched_paths, ("mod.py",))
