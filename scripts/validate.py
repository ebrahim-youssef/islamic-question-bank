#!/usr/bin/env python3
"""Validate the question bank data files against Schema V2.

Checks:
- schema/question.schema.json and schema/category.schema.json are valid
  Draft 2020-12 schemas (Draft202012Validator.check_schema)
- every category and every question validates against its schema with a
  FormatChecker whose date-time checker combines strict RFC 3339 shape with
  real calendar/time validation (timezone required), so format enforcement
  does not depend on optional extras like rfc3339-validator; the same
  predicate backs the semantic verifiedAt check
- category IDs are unique; parentId references exist and are not self-references
- category hierarchy contains no cycles
- parent/leaf categories are computed from the actual hierarchy in
  data/categories.json (no hardcoded category names)
- questions live only in leaf categories
- each question file's declared categoryId equals every contained question's
  categoryId, and each leaf category has exactly one file
- question IDs are globally unique
- exactly four choices per question; choice IDs drawn from a|b|c|d and unique;
  choice texts unique and non-empty
- correctChoiceId is one of a|b|c|d and corresponds to exactly one choice
- tier is an integer 1..5; ageBand is kids|general|scholar
- tags are unique after whitespace trimming and non-empty
- references are structured: quran/hadith/book/other with required fields
- verification.status is pending|verified|needs_review; verifiedAt is set
  (date-time) iff status is verified, otherwise null
- no duplicate question text + ageBand within the same category
- data/manifest.json validates against schema/manifest.schema.json
- manifest file hashes and byte counts are recomputed directly from raw bytes
- every achievement set validates, references questions on this branch, and has no duplicate IDs
- manifest question and achievement-set metadata, totals, paths, and bankHash match data/

Exit code 0 on success, 1 on any error.
"""

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from build_manifest import derive_bank_hash

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ImportError:
    print(
        "FAILED: the 'jsonschema' package is required "
        "(pip install jsonschema); cannot run validation."
    )
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CATEGORIES_PATH = DATA_DIR / "categories.json"
QUESTIONS_DIR = DATA_DIR / "questions"
ACHIEVEMENT_SETS_DIR = DATA_DIR / "achievement-sets"
QUESTION_SCHEMA_PATH = ROOT / "schema" / "question.schema.json"
CATEGORY_SCHEMA_PATH = ROOT / "schema" / "category.schema.json"
ACHIEVEMENT_SET_SCHEMA_PATH = ROOT / "schema" / "achievement-set.schema.json"
MANIFEST_PATH = DATA_DIR / "manifest.json"
MANIFEST_SCHEMA_PATH = ROOT / "schema" / "manifest.schema.json"

VALID_AGE_BANDS = ("kids", "general", "scholar")
VALID_CHOICE_IDS = ("a", "b", "c", "d")
VALID_REF_TYPES = ("quran", "hadith", "book", "other")
VALID_VERIFICATION_STATUSES = ("pending", "verified", "needs_review")

RFC3339_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def _is_valid_rfc3339_datetime(value: str) -> bool:
    """Strict RFC 3339 date-time string: exact shape plus real calendar values,
    timezone mandatory."""
    if not RFC3339_DATETIME_RE.match(value):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00" if value[-1] in "Zz" else value)
    except ValueError:
        return False
    return True


def _format_is_rfc3339_datetime(instance) -> bool:
    """FormatChecker hook: non-string instances are the 'type' keywords' job,
    so they pass here; strings get full RFC 3339 validation."""
    return not isinstance(instance, str) or _is_valid_rfc3339_datetime(instance)


FORMAT_CHECKER = FormatChecker()
FORMAT_CHECKER.checks("date-time")(_format_is_rfc3339_datetime)


def load_json(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc


def make_validator(schema_path: Path) -> Draft202012Validator:
    """check_schema the document, then return a validator with format checking."""
    schema = load_json(schema_path)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"{schema_path}: not a valid Draft 2020-12 schema: {exc.message}") from exc
    return Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


def schema_errors(validator: Draft202012Validator, instance, label: str) -> list[str]:
    errors = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in err.absolute_path
        )
        errors.append(f"{label}: schema violation at {path}: {err.message}")
    return errors


def _disk_metadata(path: Path) -> dict:
    """Compute integrity metadata directly from raw disk bytes."""
    raw = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def validate_manifest(
    manifest,
    validator: Draft202012Validator,
    leaf_ids: set[str],
    question_file_facts: dict[str, dict],
    achievement_set_facts: dict[str, dict],
) -> list[str]:
    """Validate manifest structure and independently recompute disk metadata."""
    errors = schema_errors(validator, manifest, MANIFEST_PATH.name)
    if not isinstance(manifest, dict):
        return errors

    categories_record = manifest.get("categories")
    categories_metadata = _disk_metadata(CATEGORIES_PATH)
    if isinstance(categories_record, dict):
        for field in ("path", "sha256", "bytes"):
            if categories_record.get(field) != categories_metadata[field]:
                errors.append(
                    f"{MANIFEST_PATH.name}.categories.{field}: "
                    f"got {categories_record.get(field)!r}, "
                    f"expected {categories_metadata[field]!r} from disk"
                )

    entries = manifest.get("questionFiles")
    if not isinstance(entries, list):
        return errors

    question_metadata_by_path = {
        path: _disk_metadata(facts["path"])
        for path, facts in question_file_facts.items()
    }

    manifest_paths: list[str] = []
    manifest_category_ids: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        label = f"{MANIFEST_PATH.name}.questionFiles[{index}]"
        manifest_path = entry.get("path")
        category_id = entry.get("categoryId")
        if isinstance(manifest_path, str):
            manifest_paths.append(manifest_path)
        if isinstance(category_id, str):
            manifest_category_ids.append(category_id)

        facts = question_file_facts.get(manifest_path)
        if facts is None:
            errors.append(f"{label}: path {manifest_path!r} is not a question file on disk")
            continue

        metadata = question_metadata_by_path[manifest_path]
        for field in ("sha256", "bytes"):
            if entry.get(field) != metadata[field]:
                errors.append(
                    f"{label}.{field}: got {entry.get(field)!r}, "
                    f"expected {metadata[field]!r} from disk"
                )
        if entry.get("questionCount") != facts["questionCount"]:
            errors.append(
                f"{label}.questionCount: got {entry.get('questionCount')!r}, "
                f"expected {facts['questionCount']!r} from disk"
            )
        if category_id != facts["categoryId"]:
            errors.append(
                f"{label}.categoryId: got {category_id!r}, "
                f"expected {facts['categoryId']!r} from {manifest_path}"
            )

    for path, count in sorted(Counter(manifest_paths).items()):
        if count > 1:
            errors.append(f"{MANIFEST_PATH.name}: path {path!r} appears {count} times")
    for category_id, count in sorted(Counter(manifest_category_ids).items()):
        if count > 1:
            errors.append(
                f"{MANIFEST_PATH.name}: categoryId {category_id!r} appears {count} times"
            )

    actual_paths = set(question_file_facts)
    for path in sorted(actual_paths - set(manifest_paths)):
        errors.append(f"{MANIFEST_PATH.name}: question file {path!r} has no entry")

    category_counts = Counter(manifest_category_ids)
    for category_id in sorted(leaf_ids):
        count = category_counts[category_id]
        if count != 1:
            errors.append(
                f"{MANIFEST_PATH.name}: leaf category {category_id!r} must have "
                f"exactly one entry, got {count}"
            )
    for category_id in sorted(set(manifest_category_ids) - leaf_ids):
        errors.append(
            f"{MANIFEST_PATH.name}: categoryId {category_id!r} is not a leaf category"
        )

    sorted_category_ids = sorted(manifest_category_ids)
    if manifest_category_ids != sorted_category_ids:
        errors.append(
            f"{MANIFEST_PATH.name}.questionFiles: entries must be sorted by categoryId"
        )

    expected_total_questions = sum(
        facts["questionCount"] for facts in question_file_facts.values()
    )
    expected_total_bytes = sum(
        metadata["bytes"] for metadata in question_metadata_by_path.values()
    )
    if manifest.get("totalQuestions") != expected_total_questions:
        errors.append(
            f"{MANIFEST_PATH.name}.totalQuestions: got "
            f"{manifest.get('totalQuestions')!r}, expected {expected_total_questions}"
        )
    if manifest.get("totalBytes") != expected_total_bytes:
        errors.append(
            f"{MANIFEST_PATH.name}.totalBytes: got {manifest.get('totalBytes')!r}, "
            f"expected {expected_total_bytes}"
        )

    achievement_entries = manifest.get("achievementSets")
    if not isinstance(achievement_entries, list):
        return errors

    achievement_metadata_by_path = {
        path: _disk_metadata(facts["path"])
        for path, facts in achievement_set_facts.items()
    }
    manifest_achievement_paths: list[str] = []
    for index, entry in enumerate(achievement_entries):
        if not isinstance(entry, dict):
            continue
        label = f"{MANIFEST_PATH.name}.achievementSets[{index}]"
        manifest_path = entry.get("path")
        if isinstance(manifest_path, str):
            manifest_achievement_paths.append(manifest_path)

        facts = achievement_set_facts.get(manifest_path)
        if facts is None:
            errors.append(f"{label}: path {manifest_path!r} is not an achievement set on disk")
            continue

        metadata = achievement_metadata_by_path[manifest_path]
        for field in ("sha256", "bytes"):
            if entry.get(field) != metadata[field]:
                errors.append(
                    f"{label}.{field}: got {entry.get(field)!r}, "
                    f"expected {metadata[field]!r} from disk"
                )
        if entry.get("questionCount") != facts["questionCount"]:
            errors.append(
                f"{label}.questionCount: got {entry.get('questionCount')!r}, "
                f"expected {facts['questionCount']!r} from disk"
            )

    for path, count in sorted(Counter(manifest_achievement_paths).items()):
        if count > 1:
            errors.append(f"{MANIFEST_PATH.name}: achievement set path {path!r} appears {count} times")
    actual_achievement_paths = set(achievement_set_facts)
    for path in sorted(actual_achievement_paths - set(manifest_achievement_paths)):
        errors.append(f"{MANIFEST_PATH.name}: achievement set {path!r} has no entry")
    for path in sorted(set(manifest_achievement_paths) - actual_achievement_paths):
        errors.append(f"{MANIFEST_PATH.name}: achievement set {path!r} is not on disk")
    if manifest_achievement_paths != sorted(manifest_achievement_paths):
        errors.append(
            f"{MANIFEST_PATH.name}.achievementSets: entries must be sorted by path"
        )

    expected_bank_hash = derive_bank_hash(
        [categories_metadata]
        + list(question_metadata_by_path.values())
        + list(achievement_metadata_by_path.values())
    )
    if manifest.get("bankHash") != expected_bank_hash:
        errors.append(
            f"{MANIFEST_PATH.name}.bankHash: got {manifest.get('bankHash')!r}, "
            f"expected {expected_bank_hash!r} from current file paths and hashes"
        )

    return errors


def validate_achievement_sets(
    validator: Draft202012Validator, question_ids: set[str]
) -> tuple[dict[str, dict], int, list[str]]:
    """Validate immutable set definitions against questions present on this branch."""
    errors: list[str] = []
    facts: dict[str, dict] = {}
    total_question_references = 0

    if not ACHIEVEMENT_SETS_DIR.is_dir():
        return facts, total_question_references, errors

    for path in sorted(ACHIEVEMENT_SETS_DIR.glob("*.json")):
        file_label = path.relative_to(ROOT).as_posix()
        try:
            achievement_set = load_json(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        errors.extend(schema_errors(validator, achievement_set, file_label))
        if not isinstance(achievement_set, dict):
            continue

        # The id is the stable handle a player's unlocked achievements are keyed
        # by, so it has to identify exactly one definition. Without this, a file
        # named advanced.json could declare the id of an already-published set,
        # or two files could claim the same id, and a consumer resolving an
        # unlocked achievement would have no way to tell which body of questions
        # it referred to.
        set_id = achievement_set.get("id")
        if isinstance(set_id, str) and set_id != path.stem:
            errors.append(
                f"{file_label}.id: {set_id!r} does not match its filename {path.stem!r}"
            )

        question_ids_in_set = achievement_set.get("questionIds")
        if not isinstance(question_ids_in_set, list):
            continue

        total_question_references += len(question_ids_in_set)
        string_question_ids = [
            question_id
            for question_id in question_ids_in_set
            if isinstance(question_id, str)
        ]
        for question_id, count in sorted(Counter(string_question_ids).items()):
            if count > 1:
                errors.append(
                    f"{file_label}: question id {question_id!r} appears {count} times"
                )
        for index, question_id in enumerate(question_ids_in_set):
            if not isinstance(question_id, str):
                continue
            if question_id not in question_ids:
                errors.append(
                    f"{file_label}.questionIds[{index}]: {question_id!r} "
                    "does not exist in data/questions on this branch"
                )

        facts[file_label] = {"path": path, "questionCount": len(question_ids_in_set)}

    return facts, total_question_references, errors


def validate_categories(
    categories, validator: Draft202012Validator
) -> tuple[dict, dict, dict, list[str]]:
    """Validate categories against schema + hierarchy rules.

    Returns (categories_by_id, parent_ids, leaf_ids, errors).
    """
    errors = []
    if not isinstance(categories, list) or not categories:
        return {}, set(), set(), [f"{CATEGORIES_PATH}: must be a non-empty array"]

    categories_by_id: dict[str, dict] = {}
    for i, cat in enumerate(categories):
        label = f"{CATEGORIES_PATH.name}[{i}]"
        if not isinstance(cat, dict):
            errors.append(f"{label}: must be an object")
            continue
        errors.extend(
            schema_errors(validator, cat, f"{label} id={cat.get('id')!r}")
        )
        cid = cat.get("id")
        if not isinstance(cid, str) or not cid:
            continue
        if cid in categories_by_id:
            errors.append(f"duplicate category id '{cid}'")
        else:
            categories_by_id[cid] = cat

    # Parent references must exist and must not be self-references.
    for cid, cat in categories_by_id.items():
        parent_id = cat.get("parentId")
        if parent_id is None:
            continue
        if parent_id == cid:
            errors.append(f"category '{cid}': parentId references itself")
        elif parent_id not in categories_by_id:
            errors.append(
                f"category '{cid}': parentId '{parent_id}' does not match any category id"
            )

    # Cycle detection over parentId chains.
    reported_cycles: set[frozenset] = set()
    for start in categories_by_id:
        seen: list[str] = []
        node = start
        while isinstance(node, str):
            if node in seen:
                cycle = seen[seen.index(node):]
                key = frozenset(cycle)
                if len(cycle) > 1 and key not in reported_cycles:
                    reported_cycles.add(key)
                    errors.append(
                        "category hierarchy cycle: " + " -> ".join([*cycle, cycle[0]])
                    )
                break
            seen.append(node)
            parent = categories_by_id.get(node, {}).get("parentId")
            if parent is not None and parent not in categories_by_id:
                break  # dangling reference already reported above
            node = parent

    children = {cid: 0 for cid in categories_by_id}
    for cat in categories_by_id.values():
        parent_id = cat.get("parentId")
        if parent_id in children:
            children[parent_id] += 1

    parent_ids = {cid for cid, n in children.items() if n > 0}
    leaf_ids = {cid for cid, n in children.items() if n == 0}
    return categories_by_id, parent_ids, leaf_ids, errors


def check_references(q_label: str, references, errors: list[str]) -> None:
    """Runtime mirror of the structured-reference union."""
    if not isinstance(references, list) or len(references) == 0:
        errors.append(f"{q_label}: references must be a non-empty array")
        return
    for j, ref in enumerate(references):
        ref_label = f"{q_label}.references[{j}]"
        if not isinstance(ref, dict):
            errors.append(f"{ref_label}: must be an object")
            continue
        allowed = {"type"}
        ref_type = ref.get("type")

        if ref_type == "quran":
            allowed |= {"surah", "ayah"}
            missing = {"surah", "ayah"} - ref.keys()
            if missing:
                errors.append(f"{ref_label}: quran reference missing {sorted(missing)}")
            else:
                surah, ayah = ref["surah"], ref["ayah"]
                if not isinstance(surah, int) or isinstance(surah, bool) or not (
                    1 <= surah <= 114
                ):
                    errors.append(f"{ref_label}: surah must be an integer 1-114, got {surah!r}")
                if not isinstance(ayah, int) or isinstance(ayah, bool) or ayah < 1:
                    errors.append(f"{ref_label}: ayah must be a positive integer, got {ayah!r}")
        elif ref_type == "hadith":
            allowed |= {"collection", "number"}
            missing = {"collection", "number"} - ref.keys()
            if missing:
                errors.append(f"{ref_label}: hadith reference missing {sorted(missing)}")
        elif ref_type == "book":
            allowed |= {"title", "locator"}
            if "title" not in ref:
                errors.append(f"{ref_label}: book reference requires 'title'")
        elif ref_type == "other":
            allowed |= {"label"}
            if "label" not in ref:
                errors.append(f"{ref_label}: other reference requires 'label'")
        else:
            errors.append(
                f"{ref_label}: unknown reference type {ref_type!r}; "
                f"expected one of {list(VALID_REF_TYPES)}"
            )
            continue

        extra = set(ref.keys()) - allowed
        if extra:
            errors.append(f"{ref_label}: unexpected field(s) {sorted(extra)}")


def check_verification(q_label: str, verification, errors: list[str]) -> None:
    if not isinstance(verification, dict):
        errors.append(f"{q_label}: verification must be an object")
        return
    extra = set(verification.keys()) - {"status", "verifiedAt"}
    if extra:
        errors.append(f"{q_label}: verification has unexpected field(s) {sorted(extra)}")
    status = verification.get("status")
    verified_at = verification.get("verifiedAt")
    if status not in VALID_VERIFICATION_STATUSES:
        errors.append(
            f"{q_label}: verification.status must be one of "
            f"{list(VALID_VERIFICATION_STATUSES)}, got {status!r}"
        )
    if status == "verified":
        if verified_at is None:
            errors.append(f"{q_label}: verifiedAt is required when status is 'verified'")
        elif (
            not isinstance(verified_at, str)
            or not _is_valid_rfc3339_datetime(verified_at)
        ):
            errors.append(
                f"{q_label}: verifiedAt must be a valid RFC 3339 date-time string "
                f"(timezone required), got {verified_at!r}"
            )
    elif verified_at is not None:
        errors.append(f"{q_label}: verifiedAt must be null unless status is 'verified'")


def check_question_semantics(
    q,
    q_label: str,
    file_category_id,
    cat_ids: set,
    leaf_ids: set,
    seen_question_ids: dict,
    texts_by_category: dict,
    errors: list[str],
) -> str | None:
    """All non-schema checks for one question. Returns the question id."""
    qid = q.get("id") if isinstance(q, dict) else None
    if isinstance(qid, str) and qid:
        if qid in seen_question_ids:
            errors.append(
                f"{q_label}: duplicate question id '{qid}' (already defined in "
                f"{seen_question_ids[qid]})"
            )
        else:
            seen_question_ids[qid] = q_label.rsplit("#", 1)[0]
    else:
        qid = None

    category_id = q.get("categoryId") if isinstance(q, dict) else None
    if category_id not in cat_ids:
        errors.append(f"{q_label}: categoryId {category_id!r} is not a known category")
    if category_id in cat_ids and category_id not in leaf_ids:
        errors.append(
            f"{q_label}: categoryId '{category_id}' is not a leaf category; "
            "questions may only live in leaf categories"
        )
    if category_id != file_category_id:
        errors.append(
            f"{q_label}: question categoryId {category_id!r} != file-declared "
            f"categoryId {file_category_id!r}"
        )

    age_band = q.get("ageBand")
    if age_band not in VALID_AGE_BANDS:
        errors.append(f"{q_label}: ageBand must be one of {list(VALID_AGE_BANDS)}, got {age_band!r}")

    tier = q.get("tier")
    if (
        not isinstance(tier, int)
        or isinstance(tier, bool)
        or not (1 <= tier <= 5)
    ):
        errors.append(f"{q_label}: tier must be an integer 1-5, got {tier!r}")

    text = q.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{q_label}: text must be a non-empty string")
    elif isinstance(category_id, str) and age_band is not None:
        key = (category_id, text.strip(), age_band)
        if key in texts_by_category:
            errors.append(
                f"{q_label}: duplicate question text+ageBand within category "
                f"'{category_id}' (first seen at {texts_by_category[key]})"
            )
        else:
            texts_by_category[key] = q_label

    choices = q.get("choices")
    if not isinstance(choices, list) or len(choices) != 4:
        errors.append(
            f"{q_label}: choices must contain exactly four items, got "
            f"{len(choices) if isinstance(choices, list) else type(choices).__name__}"
        )
        choices = None

    choice_ids: list = []
    choice_texts: list = []
    if choices:
        for i, choice in enumerate(choices):
            if not isinstance(choice, dict):
                errors.append(f"{q_label}.choices[{i}]: must be an object")
                continue
            cid = choice.get("id")
            ctext = choice.get("text")
            if cid not in VALID_CHOICE_IDS:
                errors.append(
                    f"{q_label}.choices[{i}]: id must be one of {list(VALID_CHOICE_IDS)}, got {cid!r}"
                )
            choice_ids.append(cid)
            if not isinstance(ctext, str) or not ctext.strip():
                errors.append(f"{q_label}.choices[{i}]: text must be a non-empty string")
            choice_texts.append(ctext.strip() if isinstance(ctext, str) else ctext)

    if len(set(choice_ids)) != len(choice_ids):
        errors.append(f"{q_label}: duplicate choice ids {choice_ids}")
    normalized_texts = [
        t for t in choice_texts if t is not None
    ]
    if len(set(normalized_texts)) != len(normalized_texts):
        errors.append(f"{q_label}: duplicate choice texts")

    correct_id = q.get("correctChoiceId")
    matches = [c for c in choice_ids if c == correct_id]
    if correct_id not in VALID_CHOICE_IDS:
        errors.append(
            f"{q_label}: correctChoiceId must be one of {list(VALID_CHOICE_IDS)}, got {correct_id!r}"
        )
    elif len(matches) != 1:
        errors.append(
            f"{q_label}: correctChoiceId '{correct_id}' must match exactly one choice, "
            f"matched {len(matches)} in {choice_ids}"
        )

    explanation = q.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        errors.append(f"{q_label}: explanation must be a non-empty string")

    tags = q.get("tags")
    if not isinstance(tags, list):
        errors.append(f"{q_label}: tags must be an array")
    else:
        seen_tags = set()
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                errors.append(f"{q_label}: tags must be non-empty strings, got {tag!r}")
                continue
            normalized = tag.strip()
            if normalized in seen_tags:
                errors.append(f"{q_label}: duplicate tag '{tag}'")
            else:
                seen_tags.add(normalized)

    check_references(q_label, q.get("references"), errors)
    check_verification(q_label, q.get("verification"), errors)
    return qid


def main() -> int:
    errors: list[str] = []

    for schema_path in (
        QUESTION_SCHEMA_PATH,
        CATEGORY_SCHEMA_PATH,
        ACHIEVEMENT_SET_SCHEMA_PATH,
        MANIFEST_SCHEMA_PATH,
    ):
        if not schema_path.exists():
            errors.append(f"missing schema file: {schema_path}")
    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    # All schema documents are check_schema'd and instantiated unconditionally,
    # before any data is loaded, so a broken schema is always reported.
    try:
        question_validator = make_validator(QUESTION_SCHEMA_PATH)
        category_validator = make_validator(CATEGORY_SCHEMA_PATH)
        achievement_set_validator = make_validator(ACHIEVEMENT_SET_SCHEMA_PATH)
        manifest_validator = make_validator(MANIFEST_SCHEMA_PATH)
    except ValueError as exc:
        print(f"FAILED — invalid schema: {exc}")
        return 1

    if not CATEGORIES_PATH.exists():
        print(f"FAILED — missing {CATEGORIES_PATH}")
        return 1
    if not QUESTIONS_DIR.is_dir():
        print(f"FAILED — missing questions directory {QUESTIONS_DIR}")
        return 1
    if not ACHIEVEMENT_SETS_DIR.is_dir():
        print(f"FAILED — missing achievement sets directory {ACHIEVEMENT_SETS_DIR}")
        return 1
    if not MANIFEST_PATH.exists():
        print(f"FAILED — missing {MANIFEST_PATH}")
        return 1

    try:
        categories = load_json(CATEGORIES_PATH)
        manifest = load_json(MANIFEST_PATH)
    except ValueError as exc:
        print(f"FAILED — {exc}")
        return 1

    categories_by_id, parent_ids, leaf_ids, cat_errors = validate_categories(
        categories, category_validator
    )
    errors.extend(cat_errors)
    cat_ids = set(categories_by_id)

    question_files = sorted(QUESTIONS_DIR.glob("*.json"))
    if not question_files:
        errors.append(f"{QUESTIONS_DIR}: no question files found")

    seen_question_ids: dict[str, str] = {}
    texts_by_category: dict[tuple, str] = {}
    files_by_category: dict[str, Path] = {}
    question_file_facts: dict[str, dict] = {}
    total_questions = 0
    age_band_counts = {band: 0 for band in VALID_AGE_BANDS}
    status_counts = {status: 0 for status in VALID_VERIFICATION_STATUSES}

    for path in question_files:
        file_label = path.relative_to(ROOT).as_posix()
        try:
            payload = load_json(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        if not isinstance(payload, dict) or "questions" not in payload:
            errors.append(f"{file_label}: expected an object with a 'questions' array")
            continue
        questions = payload["questions"]
        if not isinstance(questions, list):
            errors.append(f"{file_label}: 'questions' must be an array")
            continue

        declared_category = payload.get("categoryId")
        if not isinstance(declared_category, str) or not declared_category:
            errors.append(f"{file_label}: 'categoryId' must be a non-empty string")
            declared_category = None
        if declared_category is not None and declared_category not in cat_ids:
            errors.append(
                f"{file_label}: declared categoryId {declared_category!r} is not a known category"
            )
        if declared_category in cat_ids and declared_category not in leaf_ids:
            errors.append(
                f"{file_label}: declared categoryId '{declared_category}' is not a leaf "
                "category; questions may only live in leaf categories"
            )
        if isinstance(declared_category, str):
            if declared_category in files_by_category:
                errors.append(
                    f"{file_label}: second file declaring categoryId '{declared_category}' "
                    f"(first was {files_by_category[declared_category].relative_to(ROOT).as_posix()})"
                )
            else:
                files_by_category[declared_category] = path

        question_file_facts[file_label] = {
            "path": path,
            "categoryId": declared_category,
            "questionCount": len(questions),
        }

        for idx, q in enumerate(questions):
            q_label = f"{file_label}#{idx}"
            if not isinstance(q, dict):
                errors.append(f"{q_label}: question must be an object")
                continue
            qid_for_label = q.get("id") if isinstance(q.get("id"), str) else "?"
            q_label = f"{file_label}#{idx} id={qid_for_label}"

            errors.extend(schema_errors(question_validator, q, q_label))
            check_question_semantics(
                q,
                q_label,
                declared_category,
                cat_ids,
                leaf_ids,
                seen_question_ids,
                texts_by_category,
                errors,
            )
            total_questions += 1
            band = q.get("ageBand")
            if band in age_band_counts:
                age_band_counts[band] += 1
            verification = q.get("verification")
            status = verification.get("status") if isinstance(verification, dict) else None
            if status in status_counts:
                status_counts[status] += 1

    # Coverage: every leaf category needs a question file.
    for cid in sorted(leaf_ids - set(files_by_category)):
        errors.append(f"leaf category '{cid}' has no question file")
    orphan_files = sorted(
        p.relative_to(ROOT).as_posix()
        for cid, p in files_by_category.items()
        if cid not in cat_ids
    )

    achievement_set_facts, achievement_question_references, achievement_set_errors = (
        validate_achievement_sets(achievement_set_validator, set(seen_question_ids))
    )
    errors.extend(achievement_set_errors)

    errors.extend(
        validate_manifest(
            manifest,
            manifest_validator,
            leaf_ids,
            question_file_facts,
            achievement_set_facts,
        )
    )

    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"OK — validated {total_questions} questions in {len(question_files)} file(s); "
        f"{len(cat_ids)} categories ({len(parent_ids)} parent / {len(leaf_ids)} leaf); "
        f"{len(achievement_set_facts)} achievement set(s) "
        f"({achievement_question_references} question reference(s))"
    )
    print(
        f"    ageBands: "
        + ", ".join(f"{band}={n}" for band, n in age_band_counts.items())
    )
    print(
        "    verification: "
        + ", ".join(f"{status}={n}" for status, n in status_counts.items())
    )
    if orphan_files:
        print(f"    note: ignored undeclared files: {', '.join(orphan_files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
