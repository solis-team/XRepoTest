"""Agentic (headless Claude Code) evaluation mode.

Runs Claude Code directly against a scratch copy of the affected repo, using
the existing, unmodified per-language Docker images purely as an invoked
compile/test tool. Output is packaged into the same prompts_responses.jsonl
shape every other mode produces, so preprocess/eval need no changes.
"""
