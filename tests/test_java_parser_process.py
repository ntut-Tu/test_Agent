"""Exercise native parser lifetime and line numbers beyond cached small integers."""

import subprocess
import sys
import unittest


class JavaParserProcessTests(unittest.TestCase):
    def test_large_java_files_keep_line_numbers_and_exit_cleanly(self):
        # A child process lets the test report native crashes, including at exit.
        script = '''
from codebase_analysis.infrastructure.source.java import JavaSourceAnalyzer
analyzer = JavaSourceAnalyzer()
source = "package demo;\\nclass Large {\\n" + "".join(
    f"    int method{i}() {{\\n        return {i}; // 中文\\n    }}\\n"
    for i in range(400)
) + "}\\n"
for _ in range(8):
    methods = analyzer.parse("src/main/java/demo/Large.java", source)
    assert len(methods) == 400
    for i, method in enumerate(methods):
        assert method.name == f"method{i}"
        assert method.start_line == 3 + 3 * i
        assert method.end_line == 5 + 3 * i
'''
        result = subprocess.run(
            [sys.executable, '-X', 'faulthandler', '-c', script],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
