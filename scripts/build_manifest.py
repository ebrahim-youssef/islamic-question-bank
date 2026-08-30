#!/usr/bin/env python3
"""إنشاء ``data/manifest.json`` من الملفات المرجعية داخل ``data/``.

تُحسب قيمة ``bankHash`` هكذا بالضبط: تُرتّب جميع ملفات المصدر حسب المسار،
ثم تُنشأ مصفوفة JSON من أزواج ``[path, sha256]`` وتُسلسل بترميز UTF-8، من
دون مسافات أو سطر أخير. شكل البايتات الداخلة إلى SHA-256 حرفيًا هو:

``[["data/categories.json","<64 lowercase hex>"],["data/questions/hajj.json","<64 lowercase hex>"],...]``

لا يتضمن البيان ``generatedAt`` عمدًا؛ لأن وقت الإنشاء لا يصف المحتوى،
ويجعل ملفًا صحيحًا يختلف بين تشغيلين ويعطّل فحص ``--check`` دون فائدة.
تُحسب تجزئات الملفات من بايتاتها الخام قبل فك JSON، بلا إعادة تسلسل أو تطبيع.
وتجمع ``totalBytes`` أحجام ملفات الأسئلة، أما حجم ملف الفئات ففي سجله المستقل.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
CATEGORIES_PATH = DATA_DIR / "categories.json"
QUESTIONS_DIR = DATA_DIR / "questions"


def _read_source(path: Path, root: Path) -> tuple[dict, object]:
    raw = path.read_bytes()
    record = {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{record['path']}: invalid UTF-8 JSON ({exc})") from exc
    return record, payload


def derive_bank_hash(entries: list[dict]) -> str:
    """Return SHA-256 of compact UTF-8 JSON sorted ``[path, sha256]`` pairs."""
    pairs = [
        [entry["path"], entry["sha256"]]
        for entry in sorted(entries, key=lambda entry: entry["path"])
    ]
    encoded = json.dumps(
        pairs, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(root: Path = ROOT) -> dict:
    data_dir = root / "data"
    categories_path = data_dir / "categories.json"
    questions_dir = data_dir / "questions"

    categories, categories_payload = _read_source(categories_path, root)
    if not isinstance(categories_payload, list):
        raise ValueError("data/categories.json: expected an array")

    question_files = []
    source_records = [categories]
    seen_category_ids: set[str] = set()
    for path in sorted(questions_dir.glob("*.json")):
        record, payload = _read_source(path, root)
        if not isinstance(payload, dict):
            raise ValueError(f"{record['path']}: expected an object")
        category_id = payload.get("categoryId")
        questions = payload.get("questions")
        if not isinstance(category_id, str) or not category_id:
            raise ValueError(
                f"{record['path']}: 'categoryId' must be a non-empty string"
            )
        if category_id in seen_category_ids:
            raise ValueError(f"duplicate question file categoryId '{category_id}'")
        if not isinstance(questions, list):
            raise ValueError(f"{record['path']}: 'questions' must be an array")

        seen_category_ids.add(category_id)
        source_records.append(record)
        question_files.append(
            {
                "categoryId": category_id,
                **record,
                "questionCount": len(questions),
            }
        )

    if not question_files:
        raise ValueError("data/questions: no question files found")

    question_files.sort(key=lambda entry: entry["categoryId"])
    return {
        "schemaVersion": 2,
        "bankHash": derive_bank_hash(source_records),
        "totalQuestions": sum(item["questionCount"] for item in question_files),
        "totalBytes": sum(item["bytes"] for item in question_files),
        "categories": categories,
        "questionFiles": question_files,
    }


def _differences(expected, actual, path: str = "$") -> list[str]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences = []
        for key in sorted(expected.keys() | actual.keys()):
            child_path = f"{path}.{key}"
            if key not in actual:
                differences.append(f"{child_path}: missing; expected {expected[key]!r}")
            elif key not in expected:
                differences.append(f"{child_path}: unexpected value {actual[key]!r}")
            else:
                differences.extend(_differences(expected[key], actual[key], child_path))
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        for index in range(max(len(expected), len(actual))):
            child_path = f"{path}[{index}]"
            if index >= len(actual):
                differences.append(
                    f"{child_path}: missing; expected {expected[index]!r}"
                )
            elif index >= len(expected):
                differences.append(
                    f"{child_path}: unexpected value {actual[index]!r}"
                )
            else:
                differences.extend(
                    _differences(expected[index], actual[index], child_path)
                )
        return differences
    if expected != actual:
        return [f"{path}: committed {actual!r}; expected {expected!r}"]
    return []


def _check(expected: dict) -> int:
    if not MANIFEST_PATH.exists():
        print(f"FAILED — missing {MANIFEST_PATH.relative_to(ROOT).as_posix()}")
        return 1
    try:
        actual = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAILED — data/manifest.json: invalid JSON ({exc})")
        return 1

    differences = _differences(expected, actual)
    if differences:
        print(f"FAILED — manifest drift ({len(differences)} difference(s)):")
        for difference in differences:
            print(f"  - {difference}")
        return 1
    print("OK — data/manifest.json matches the canonical data files")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="إنشاء بيان محتوى بنك الأسئلة")
    parser.add_argument(
        "--check",
        action="store_true",
        help="يفحص تطابق البيان الملتزم مع ملفات data دون كتابته",
    )
    args = parser.parse_args()

    try:
        manifest = build_manifest()
    except (OSError, ValueError) as exc:
        print(f"FAILED — {exc}")
        return 1

    if args.check:
        return _check(manifest)

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OK — wrote {MANIFEST_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
