#!/usr/bin/env python3
"""Validate the question bank data files.

Checks:
- JSON parses and matches schema/question.schema.json
- IDs are unique across all categories
- correctIndex is within the choices range (schema can't express this)
- category field matches the file it lives in
- no duplicate question text within a category
"""

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "questions"
SCHEMA_PATH = ROOT / "schema" / "question.schema.json"
CATEGORIES_PATH = ROOT / "data" / "categories.json"

REQUIRED_CATEGORY_KEYS = {"id", "key", "name"}


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    errors: list[str] = []

    if not CATEGORIES_PATH.exists():
        print(f"missing {CATEGORIES_PATH}")
        return 1

    categories = load(CATEGORIES_PATH)
    cats_by_id = {}
    for cat in categories:
        missing = REQUIRED_CATEGORY_KEYS - set(cat)
        if missing:
            errors.append(f"categories.json id={cat.get('id')}: missing keys {sorted(missing)}")
        else:
            cats_by_id[cat["id"]] = cat
    if not cats_by_id:
        errors.append("categories.json has no valid entries")

    schema = load(SCHEMA_PATH) if SCHEMA_PATH.exists() else None
    if schema is None:
        errors.append(f"missing {SCHEMA_PATH}")
    validator = jsonschema.Draft202012Validator(schema) if jsonschema and schema else None

    seen_ids: dict[str, str] = {}
    total = 0

    for path in sorted(DATA.glob("*.json")):
        payload = load(path)
        questions = payload.get("questions", [])
        declared_cat = payload.get("categoryId")
        cat_key = payload.get("categoryKey")

        if declared_cat not in cats_by_id:
            errors.append(f"{path.name}: unknown categoryId {declared_cat!r}")
        elif cats_by_id[declared_cat]["key"] != cat_key:
            errors.append(f"{path.name}: categoryKey {cat_key!r} does not match categoryId {declared_cat}")

        texts: list[str] = []
        for i, q in enumerate(questions):
            label = f"{path.name}[{i}] id={q.get('id', '?')}"

            if validator is not None:
                for err in validator.iter_errors(q):
                    errors.append(f"{label}: {err.message} (path: {'/'.join(map(str, err.absolute_path))})")

            choices = q.get("choices", [])
            idx = q.get("correctIndex")
            if isinstance(idx, int) and not 0 <= idx < len(choices):
                errors.append(f"{label}: correctIndex {idx} out of range for {len(choices)} choices")

            qid = q.get("id")
            if isinstance(qid, str):
                if qid in seen_ids:
                    errors.append(f"{label}: duplicate id, already in {seen_ids[qid]}")
                seen_ids[qid] = path.name

            if isinstance(q.get("category"), int) and q["category"] != declared_cat:
                errors.append(f"{label}: question category {q['category']} != file categoryId {declared_cat}")

            text = q.get("text")
            if isinstance(text, str):
                key = (text, q.get("ageBand"))
                if key in texts:
                    errors.append(f"{label}: duplicate question text+ageBand in this category")
                texts.append(key)

        total += len(questions)

    # every category must have a data file
    for cid, cat in cats_by_id.items():
        if not (DATA / f"{cat['key']}.json").exists():
            errors.append(f"category '{cat['key']}' (id={cid}) has no data file")

    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK — {total} questions across {len(categories)} categories validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
