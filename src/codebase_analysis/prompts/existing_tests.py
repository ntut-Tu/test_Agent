"""Instructions for the existing_tests analysis operation."""

from codebase_analysis.prompts.common import SYSTEM_PREFIX

INSTRUCTIONS = SYSTEM_PREFIX + 'For each focal Java method without an observed test caller, select relevant existing test methods as examples for generating tests. Use only supplied focal_id and test_id values. Explain relevance; do not claim the recommended test executed the target. An empty selection is valid.'
