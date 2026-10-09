"""Instructions for the pr analysis operation."""

from codebase_analysis.prompts.common import SYSTEM_PREFIX

INSTRUCTIONS = SYSTEM_PREFIX + 'Summarize the PR/MR from its title, description, and changed-file patches. Mention if the supplied input was truncated.'
