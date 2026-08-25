#!/usr/bin/env python3
"""Validate canonical question-bank data under data/ against Schema V2."""

import json
import sys
from pathlib import Path

import jsonschema
from jsonschema import FormatChecker

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "questions"
QUESTION_SCHEMA_PATH = ROOT / "schema" / "question.schema.json"
CATEGORY_SCHEMA_PATH = ROOT / "schema" / "category.schema.json"
CATEGORIES_PATH = ROOT / "data" / "categories.json"


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def schema_errors(instance, validator, label: str) -> list[str]:
    errors = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        path = "/".join(map(str, err.absolute_path)) or "<root>"
        errors.append(f"{label}: {err.message} (path: {path})")
    return errors


def validate_categories(categories: list[dict], validator) -> tuple[list[str], dict[str, dict], set[str]]:
    errors: list[str] = []
    by_id: dict[str, dict] = {}

    for i, category in enumerate(categories):
        errors.extend(schema_errors(category, validator, f"categories.json[{i}]"))
        cid = category.get("id")
        if isinstance(cid, str):
            if cid in by_id:
                errors.append(f"categories.json[{i}]: duplicate category id '{cid}'")
            else:
                by_id[cid] = category

    for cid, category in by_id.items():
        parent = category.get("parentId")
        if parent == cid:
            errors.append(f"category '{cid}': cannot be its own parent")
        elif parent is not None and parent not in by_id:
            errors.append(f"category '{cid}': parentId '{parent}' does not exist")

    # Detect cycles by walking each ancestry chain.
    for cid in by_id:
        seen: set[str] = set()
        current = cid
        while current is not None and current in by_id:
            if current in seen:
                errors.append(f"category '{cid}': category hierarchy contains a cycle")
                break
            seen.add(current)
            current = by_id[current].get("parentId")

    parent_ids = {
        category.get("parentId")
        for category in by_id.values()
        if category.get("parentId") is not None
    }
    leaf_ids = set(by_id) - parent_ids
    return errors, by_id, leaf_ids


def main() -> int:
    errors: list[str] = []

    for path in (QUESTION_SCHEMA_PATH, CATEGORY_SCHEMA_PATH, CATEGORIES_PATH):
        if not path.exists():
            print(f"missing {path}")
            return 1

    question_schema = load(QUESTION_SCHEMA_PATH)
    category_schema = load(CATEGORY_SCHEMA_PATH)

    # Fail CI if either schema itself is malformed.
    try:
        jsonschema.Draft202012Validator.check_schema(question_schema)
        jsonschema.Draft202012Validator.check_schema(category_schema)
    except jsonschema.SchemaError as exc:
        print(f"FAILED — invalid JSON Schema: {exc.message}")
        return 1

    format_checker = FormatChecker()
    question_validator = jsonschema.Draft202012Validator(
        question_schema, format_checker=format_checker
    )
    category_validator = jsonschema.Draft202012Validator(category_schema)

    categories = load(CATEGORIES_PATH)
    if not isinstance(categories, list) or not categories:
        print("FAILED — data/categories.json must be a non-empty array")
        return 1

    cat_errors, categories_by_id, leaf_ids = validate_categories(categories, category_validator)
    errors.extend(cat_errors)

    seen_ids: dict[str, str] = {}
    seen_texts: set[tuple[str, str, str]] = set()
    total = 0

    files = sorted(DATA.glob("*.json"))
    if not files:
        errors.append("data/questions contains no JSON files")

    file_category_ids: set[str] = set()

    for path in files:
        payload = load(path)
        if not isinstance(payload, dict):
            errors.append(f"{path.name}: payload must be an object")
            continue

        declared_category = payload.get("categoryId")
        questions = payload.get("questions")
        file_category_ids.add(declared_category)

        if declared_category not in categories_by_id:
            errors.append(f"{path.name}: unknown categoryId {declared_category!r}")
        elif declared_category not in leaf_ids:
            errors.append(f"{path.name}: categoryId '{declared_category}' is not a leaf category")

        expected_filename = f"{declared_category}.json"
        if isinstance(declared_category, str) and path.name != expected_filename:
            errors.append(f"{path.name}: filename must be '{expected_filename}'")

        if not isinstance(questions, list):
            errors.append(f"{path.name}: questions must be an array")
            continue

        for i, question in enumerate(questions):
            label = f"{path.name}[{i}]"
            errors.extend(schema_errors(question, question_validator, label))

            if not isinstance(question, dict):
                continue

            qid = question.get("id")
            if isinstance(qid, str):
                if qid in seen_ids:
                    errors.append(f"{label}: duplicate id '{qid}', already in {seen_ids[qid]}")
                else:
                    seen_ids[qid] = path.name

            category_id = question.get("categoryId")
            if category_id != declared_category:
                errors.append(
                    f"{label}: categoryId '{category_id}' != file category '{declared_category}'"
                )
            if category_id not in leaf_ids:
                errors.append(f"{label}: categoryId '{category_id}' must reference a leaf category")

            text = question.get("text")
            age_band = question.get("ageBand")
            if isinstance(text, str) and isinstance(age_band, str) and isinstance(category_id, str):
                key = (category_id, text.strip(), age_band)
                if key in seen_texts:
                    errors.append(f"{label}: duplicate question text+ageBand in category")
                seen_texts.add(key)

            choices = question.get("choices")
            if isinstance(choices, list):
                choice_ids = [c.get("id") for c in choices if isinstance(c, dict)]
                choice_texts = [c.get("text", "").strip() for c in choices if isinstance(c, dict)]
                if len(choice_ids) != len(set(choice_ids)):
                    errors.append(f"{label}: choice ids must be unique")
                if len(choice_texts) != len(set(choice_texts)):
                    errors.append(f"{label}: choice texts must be unique")
                correct_choice_id = question.get("correctChoiceId")
                if choice_ids.count(correct_choice_id) != 1:
                    errors.append(
                        f"{label}: correctChoiceId must match exactly one choice id"
                    )

        total += len(questions)

    # Canonical data currently stores one file per leaf category.
    for leaf_id in sorted(leaf_ids):
        if leaf_id not in file_category_ids:
            errors.append(f"leaf category '{leaf_id}' has no data/questions/{leaf_id}.json file")

    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"OK — {total} questions across {len(files)} leaf categories validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
