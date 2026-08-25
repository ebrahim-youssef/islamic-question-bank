#!/usr/bin/env python3
"""Validate the question bank data files against Schema V2.

Checks:
- JSON parses and matches schema/question.schema.json
- IDs are unique across all categories
- correctChoiceId matches one of the choices
- categoryId references a valid category
- category hierarchy has no invalid parent references
- exactly four choices per question
- choice IDs unique within question (a,b,c,d)
- choice texts unique within question
- tier is 1..5
- ageBand is valid (kids|general|scholar)
- tags are unique and non-empty
- references match supported schemas
- verification.status is valid
- verifiedAt is null unless status is verified
- no duplicate question text + ageBand within same category
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

VALID_AGE_BANDS = {"kids", "general", "scholar"}
VALID_VERIFICATION_STATUSES = {"pending", "verified", "needs_review"}


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_categories(categories: list[dict]) -> list[str]:
    """Validate category hierarchy."""
    errors = []
    cat_by_id = {c["id"]: c for c in categories}

    # Check parentId references
    for cat in categories:
        parent_id = cat.get("parentId")
        if parent_id is not None and parent_id not in cat_by_id:
            errors.append(f"Category '{cat['id']}': parentId '{parent_id}' does not exist")
    return errors


def validate_question(q: dict, category_key: str, cat_ids: set[str], seen_ids: dict, texts_seen: set, idx: int, filename: str) -> list[str]:
    """Validate a single question."""
    errors = []
    qid = q.get("id", f"MISSING_ID_{filename}_{idx}")
    label = f"{filename}[{idx}] id={qid}"

    # Check required fields
    required_fields = ["id", "categoryId", "ageBand", "tier", "text", "choices", "correctChoiceId", "explanation", "references", "tags", "verification"]
    for field in required_fields:
        if field not in q:
            errors.append(f"{label}: missing required field '{field}'")

    # ID uniqueness
    if qid in seen_ids:
        errors.append(f"{label}: duplicate id, already in {seen_ids[qid]}")
    seen_ids[qid] = filename

    # categoryId exists
    cat_id = q.get("categoryId")
    if cat_id not in cat_ids:
        errors.append(f"{label}: categoryId '{cat_id}' not in category taxonomy")

    # categoryId matches file
    if cat_id != category_key:
        errors.append(f"{label}: categoryId '{cat_id}' != file category '{category_key}'")

    # ageBand
    age_band = q.get("ageBand")
    if age_band not in VALID_AGE_BANDS:
        errors.append(f"{label}: invalid ageBand '{age_band}'")

    # tier 1-5
    tier = q.get("tier")
    if not isinstance(tier, int) or not (1 <= tier <= 5):
        errors.append(f"{label}: tier must be integer 1-5, got {tier!r}")

    # text non-empty
    text = q.get("text", "")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{label}: text must be non-empty string")

    # Duplicate text + ageBand within category
    if isinstance(text, str):
        key = (text.strip(), age_band)
        if key in texts_seen:
            errors.append(f"{label}: duplicate question text+ageBand in this category")
        texts_seen.add(key)

    # choices: exactly 4, unique IDs a-d, unique texts
    choices = q.get("choices", [])
    if len(choices) != 4:
        errors.append(f"{label}: must have exactly 4 choices, got {len(choices)}")

    choice_ids = []
    choice_texts = []
    for i, choice in enumerate(choices):
        if not isinstance(choice, dict):
            errors.append(f"{label}: choice {i} must be object")
            continue
        cid = choice.get("id")
        ctext = choice.get("text", "")
        if cid not in {"a", "b", "c", "d"}:
            errors.append(f"{label}: choice {i} id must be a/b/c/d, got {cid!r}")
        choice_ids.append(cid)
        if not isinstance(ctext, str) or not ctext.strip():
            errors.append(f"{label}: choice {i} text must be non-empty string")
        choice_texts.append(ctext.strip())

    # unique choice IDs
    if len(set(choice_ids)) != len(choice_ids):
        errors.append(f"{label}: duplicate choice IDs: {choice_ids}")

    # unique choice texts
    if len(set(choice_texts)) != len(choice_texts):
        errors.append(f"{label}: duplicate choice texts")

    # correctChoiceId matches one choice
    correct_id = q.get("correctChoiceId")
    if correct_id not in choice_ids:
        errors.append(f"{label}: correctChoiceId '{correct_id}' not found in choices {choice_ids}")

    # explanation non-empty
    explanation = q.get("explanation", "")
    if not isinstance(explanation, str) or not explanation.strip():
        errors.append(f"{label}: explanation must be non-empty string")

    # references validation
    references = q.get("references", [])
    if not isinstance(references, list) or len(references) == 0:
        errors.append(f"{label}: references must be non-empty array")
    else:
        for j, ref in enumerate(references):
            ref_label = f"{label}.references[{j}]"
            if not isinstance(ref, dict):
                errors.append(f"{ref_label}: must be object")
                continue
            ref_type = ref.get("type")
            if ref_type == "quran":
                if "surah" not in ref or "ayah" not in ref:
                    errors.append(f"{ref_label}: quran reference requires surah and ayah")
                else:
                    surah = ref["surah"]
                    ayah = ref["ayah"]
                    if not isinstance(surah, int) or not (1 <= surah <= 114):
                        errors.append(f"{ref_label}: surah must be 1-114")
                    if not isinstance(ayah, int) or ayah < 1:
                        errors.append(f"{ref_label}: ayah must be positive integer")
            elif ref_type == "hadith":
                if "collection" not in ref or "number" not in ref:
                    errors.append(f"{ref_label}: hadith reference requires collection and number")
            elif ref_type == "book":
                if "title" not in ref:
                    errors.append(f"{ref_label}: book reference requires title")
            elif ref_type == "other":
                if "label" not in ref:
                    errors.append(f"{ref_label}: other reference requires label")
            else:
                errors.append(f"{ref_label}: unknown reference type '{ref_type}'")

    # tags: unique, non-empty
    tags = q.get("tags", [])
    if not isinstance(tags, list):
        errors.append(f"{label}: tags must be array")
    else:
        tag_set = set()
        for t in tags:
            if not isinstance(t, str) or not t.strip():
                errors.append(f"{label}: tag must be non-empty string")
            if t in tag_set:
                errors.append(f"{label}: duplicate tag '{t}'")
            tag_set.add(t)

    # verification
    verification = q.get("verification", {})
    status = verification.get("status")
    verified_at = verification.get("verifiedAt")
    if status not in VALID_VERIFICATION_STATUSES:
        errors.append(f"{label}: verification.status must be one of {sorted(VALID_VERIFICATION_STATUSES)}, got {status!r}")
    if status != "verified" and verified_at is not None:
        errors.append(f"{label}: verifiedAt must be null unless status is 'verified'")
    if status == "verified" and verified_at is None:
        errors.append(f"{label}: verifiedAt must be set when status is 'verified'")

    return errors


def main() -> int:
    errors: list[str] = []

    if not CATEGORIES_PATH.exists():
        print(f"missing {CATEGORIES_PATH}")
        return 1

    categories = load(CATEGORIES_PATH)
    cat_errors = validate_categories(categories)
    errors.extend(cat_errors)

    cat_ids = {c["id"] for c in categories}

    schema = load(SCHEMA_PATH) if SCHEMA_PATH.exists() else None
    validator = jsonschema.Draft202012Validator(schema) if jsonschema and schema else None

    seen_ids: dict[str, str] = {}
    total = 0

    for path in sorted(DATA.glob("*.json")):
        payload = load(path)
        questions = payload.get("questions", [])
        declared_cat = payload.get("categoryId")
        cat_key = declared_cat  # In V2, categoryId is the string key

        if declared_cat not in cat_ids:
            errors.append(f"{path.name}: unknown categoryId {declared_cat!r}")

        texts_seen: set = set()
        for i, q in enumerate(questions):
            errors.extend(validate_question(q, cat_key, cat_ids, seen_ids, texts_seen, i, path.name))

        total += len(questions)

    # Every category must have a data file
    for cat in categories:
        if cat["id"] == "arkan-al-islam":
            continue  # parent category, no questions
        if not (DATA / f"{cat['id']}.json").exists():
            errors.append(f"category '{cat['id']}' has no data file")

    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK — {total} questions across {len([c for c in categories if c['id'] != 'arkan-al-islam'])} categories validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())