#!/usr/bin/env python3
"""
Batch script to update signatures in existing JSONL data files.

Reads each language_functions.jsonl, re-extracts signature from focal_code,
and writes back updated function_component.signature.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from xrepotest.crawler.extractors.function_extractor import FunctionExtractor


def update_file(filepath: Path, extractor: FunctionExtractor) -> int:
    """Update signatures in a single JSONL file. Returns count of updated entries."""
    updated = 0
    errors = 0
    temp_path = filepath.with_suffix('.tmp')

    with open(filepath, 'r', encoding='utf-8') as f_in, \
         open(temp_path, 'w', encoding='utf-8') as f_out:
        for line_no, line in enumerate(f_in, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping malformed JSON at {filepath.name}:{line_no} - {e}")
                f_out.write(line)
                errors += 1
                continue

            language = entry.get('language', '').lower()
            focal_code = entry.get('focal_code', '')

            if not focal_code or not language:
                f_out.write(line)
                continue

            # Re-extract signature
            new_signature = extractor._extract_signature(focal_code, language)

            # Update function_component
            if 'function_component' in entry:
                entry['function_component']['signature'] = new_signature

            f_out.write(json.dumps(entry, ensure_ascii=False) + '\n')
            updated += 1

    # Replace original with temp
    temp_path.replace(filepath)
    return updated, errors


def main():
    # environments/xrepotest is at src/xrepotest/environments/xrepotest
    data_dir = Path(__file__).parent.parent.parent / 'environments' / 'xrepotest'
    config_path = Path(__file__).parent.parent / 'config.json'

    # Languages to update
    languages = ['go', 'rust', 'ruby', 'php', 'julia']

    extractor = FunctionExtractor(None, str(config_path))

    total_updated = 0
    total_errors = 0
    for lang in languages:
        filepath = data_dir / f'{lang}_functions.jsonl'
        if not filepath.exists():
            print(f"Skipping {filepath} (not found)")
            continue

        print(f"Updating {filepath.name}...")
        updated, errors = update_file(filepath, extractor)
        print(f"  Updated {updated} entries, {errors} errors")
        total_updated += updated
        total_errors += errors

    print(f"\nTotal: {total_updated} entries updated, {total_errors} errors")


if __name__ == '__main__':
    main()