#!/usr/bin/env python3
"""Convert the verified Fastabiqu Markdown sources into Schema V2 questions."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

AGE_BANDS = {"Kids": "kids", "General": "general", "Scholar": "scholar"}
EVIDENCE_LABELS = {
    "نص الدليل القرآني": "quran_text",
    "نص الدليل من السنة": "hadith_text",
    "وجه الدلالة من السنة": "hadith_inference",
    "دليل التفسير": "tafsir",
}
SURAH_NAMES = {
    "الفاتحة": 1, "البقرة": 2, "آل عمران": 3, "النساء": 4, "المائدة": 5,
    "الأنعام": 6, "الأعراف": 7, "الأنفال": 8, "التوبة": 9, "يونس": 10,
    "هود": 11, "يوسف": 12, "الرعد": 13, "إبراهيم": 14, "الحجر": 15,
    "النحل": 16, "الإسراء": 17, "الكهف": 18, "مريم": 19, "طه": 20,
    "الأنبياء": 21, "الحج": 22, "المؤمنون": 23, "النور": 24, "الفرقان": 25,
    "الشعراء": 26, "النمل": 27, "القصص": 28, "العنكبوت": 29, "الروم": 30,
    "لقمان": 31, "السجدة": 32, "الأحزاب": 33, "سبأ": 34, "فاطر": 35,
    "يس": 36, "الصافات": 37, "ص": 38, "الزمر": 39, "غافر": 40,
    "فصلت": 41, "الشورى": 42, "الزخرف": 43, "الدخان": 44, "الجاثية": 45,
    "الأحقاف": 46, "محمد": 47, "الفتح": 48, "الحجرات": 49, "ق": 50,
    "الذاريات": 51, "الطور": 52, "النجم": 53, "القمر": 54, "الرحمن": 55,
    "الواقعة": 56, "الحديد": 57, "المجادلة": 58, "الحشر": 59, "الممتحنة": 60,
    "الصف": 61, "الجمعة": 62, "المنافقون": 63, "التغابن": 64, "الطلاق": 65,
    "التحريم": 66, "الملك": 67, "القلم": 68, "الحاقة": 69, "المعارج": 70,
    "نوح": 71, "الجن": 72, "المزمل": 73, "المدثر": 74, "القيامة": 75,
    "الإنسان": 76, "المرسلات": 77, "النبأ": 78, "النازعات": 79, "عبس": 80,
    "التكوير": 81, "الانفطار": 82, "المطففين": 83, "الانشقاق": 84, "البروج": 85,
    "الطارق": 86, "الأعلى": 87, "الغاشية": 88, "الفجر": 89, "البلد": 90,
    "الشمس": 91, "الليل": 92, "الضحى": 93, "الشرح": 94, "التين": 95,
    "العلق": 96, "القدر": 97, "البينة": 98, "الزلزلة": 99, "العاديات": 100,
    "القارعة": 101, "التكاثر": 102, "العصر": 103, "الهمزة": 104, "الفيل": 105,
    "قريش": 106, "الماعون": 107, "الكوثر": 108, "الكافرون": 109, "النصر": 110,
    "المسد": 111, "الإخلاص": 112, "الفلق": 113, "الناس": 114,
}
HADITH_COLLECTIONS = {
    "صحيح البخاري": "sahih-bukhari", "صحيح مسلم": "sahih-muslim",
    "سنن أبي داود": "sunan-abi-dawud", "سنن الترمذي": "jami-at-tirmidhi",
    "سنن النسائي": "sunan-an-nasa'i", "سنن ابن ماجه": "sunan-ibn-majah",
    "موطأ مالك": "muwatta-malik", "مسند أحمد": "musnad-ahmad",
}


def _clean(value: str) -> str:
    return value.strip()


def _reference(line: str) -> dict:
    line = _clean(line)
    quran = re.search(r"(?:القرآن(?: الكريم)?\s*[—:-]\s*)?(.+?)\s+(\d+):(\d+)(?:\s*[-–—]\s*(\d+))?$", line)
    if quran:
        surah = SURAH_NAMES.get(quran.group(1).strip())
        if surah:
            result = {"type": "quran", "surah": surah, "ayah": int(quran.group(3))}
            if quran.group(4):
                result["ayahEnd"] = int(quran.group(4))
            return result
    for name, collection in HADITH_COLLECTIONS.items():
        match = re.match(rf"^{re.escape(name)}\s+(\d+)(?:\s*[—:-].*)?$", line)
        if match:
            return {"type": "hadith", "collection": collection, "number": match.group(1)}
    return {"type": "other", "label": line}


def _parse_block(lines: list[str], category: str, age: str, tier: int, timestamp: str) -> dict:
    number = int(re.search(r"Q(\d+)", lines[0]).group(1))
    values: dict[str, str] = {}
    evidence: list[dict[str, str]] = []
    choices: list[dict[str, str]] = []
    references: list[dict] = []
    current = None
    for line in lines[1:]:
        label = re.match(r"\*\*([^*:]+):\*\*\s*(.*)$", line)
        if label:
            current = label.group(1)
            value = label.group(2).strip()
            if current in EVIDENCE_LABELS:
                evidence.append({"kind": EVIDENCE_LABELS[current], "text": value})
            else:
                if current in values:
                    raise ValueError(f"duplicate required label {current!r} in Q{number:02d}")
                values[current] = value
            continue
        if current == "الاختيارات":
            choice = re.match(r"-\s*([A-D])\.\s*(.*?)(?:\s*✅)?$", line)
            if choice:
                choices.append({"id": choice.group(1).lower(), "text": choice.group(2).strip()})
        elif current == "المراجع" and line.startswith("- "):
            references.append(_reference(line[2:]))
        elif line.strip() and current in EVIDENCE_LABELS and evidence:
            evidence[-1]["text"] = (evidence[-1]["text"] + " " + line.strip()).strip()
    required = {"السؤال", "الإجابة الصحيحة", "الشرح", "التحقق"}
    missing = required - values.keys()
    if missing or not evidence or not references:
        raise ValueError(f"incomplete question Q{number:02d}: missing={sorted(missing)}, evidence={len(evidence)}, references={len(references)}")
    correct = re.match(r"^([A-D])\.\s+", values["الإجابة الصحيحة"])
    if not correct or len(choices) != 4 or {choice["id"] for choice in choices} != {"a", "b", "c", "d"}:
        raise ValueError(f"invalid question Q{number:02d} in {category}")
    evidence_kind = evidence[0]["kind"]
    age_id = AGE_BANDS[age]
    return {
        "id": f"{category}-{age_id}-t{tier}-q{number:02d}",
        "categoryId": category,
        "ageBand": age_id,
        "tier": tier,
        "text": values["السؤال"],
        "choices": choices,
        "correctChoiceId": correct.group(1).lower(),
        "explanation": values["الشرح"],
        "evidence": evidence,
        "references": references,
        "tags": [f"category:{category}", f"age:{age_id}", f"tier:{tier}", f"evidence:{evidence_kind}"],
        "verification": {"status": "verified", "verifiedAt": timestamp},
        "verificationNote": values["التحقق"],
    }


def convert_file(path: Path, category: str, timestamp: str, strict: bool = True) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    questions: list[dict] = []
    age = None
    tier = None
    coverage: set[tuple[str, int]] = set()
    seen_numbers: set[int] = set()
    block: list[str] | None = None
    for line in lines:
        heading = re.match(r"##\s+(Kids|General|Scholar)\b.*Tier\s+(\d+)", line)
        if heading:
            if block:
                question = _parse_block(block, category, age, tier, timestamp)
                if question["id"] in {q["id"] for q in questions}:
                    raise ValueError(f"duplicate question Q{question['id'].split('-q')[-1]} in {path}")
                seen_numbers.add(int(re.search(r"q(\d+)$", question["id"]).group(1)))
                coverage.add((age, tier))
                questions.append(question)
                block = None
            age, tier = heading.group(1), int(heading.group(2))
        elif re.match(r"###\s+Q\d+", line):
            if block:
                question = _parse_block(block, category, age, tier, timestamp)
                if int(re.search(r"q(\d+)$", question["id"]).group(1)) in seen_numbers:
                    raise ValueError(f"duplicate question number in {path}")
                seen_numbers.add(int(re.search(r"q(\d+)$", question["id"]).group(1)))
                coverage.add((age, tier))
                questions.append(question)
            block = [line]
        elif block is not None and not line.strip() == "---":
            block.append(line)
    if block:
        question = _parse_block(block, category, age, tier, timestamp)
        if int(re.search(r"q(\d+)$", question["id"]).group(1)) in seen_numbers:
            raise ValueError(f"duplicate question number in {path}")
        seen_numbers.add(int(re.search(r"q(\d+)$", question["id"]).group(1)))
        coverage.add((age, tier))
        questions.append(question)
    expected = {(name, tier) for name in AGE_BANDS for tier in range(1, 6)}
    if strict and (len(questions) != 75 or coverage != expected or sorted(seen_numbers) != list(range(1, 76))):
        raise ValueError(f"{path}: invalid coverage/count/question numbers")
    return questions


def import_all(root: Path, timestamp: str | None = None) -> None:
    timestamp = timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for path in sorted((root / "fastabiqu_375_final_verified_md").glob("*_75_final_verified.md")):
        category = path.name.split("_", 1)[0]
        questions = convert_file(path, category, timestamp)
        if len(questions) != 75:
            raise ValueError(f"{path}: expected 75 questions, got {len(questions)}")
        (root / "data/questions" / f"{category}.json").write_text(json.dumps({"categoryId": category, "questions": questions}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--timestamp")
    args = parser.parse_args()
    import_all(args.root, args.timestamp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
