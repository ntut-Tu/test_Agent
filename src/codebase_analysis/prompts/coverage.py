"""Instructions for the coverage analysis operation."""

from codebase_analysis.prompts.common import SYSTEM_PREFIX

INSTRUCTIONS = SYSTEM_PREFIX + 'Explain the behavior and test needs of the supplied uncovered patch lines. Return only path/number pairs present in those candidates. Prioritize lines added by the PR/MR. An empty list is valid. Unmatched changed paths have no coverage data.'
