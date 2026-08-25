#!/usr/bin/env python3
"""Migration script: Convert questions from old schema to Schema V2.

Old schema fields:
- id (string) -> preserve
- category (int 1-5) -> categoryId (string key)
- difficulty (int 1-5) -> tier (int 1-5)
- text (string) -> preserve
- choices (string[4]) -> choices[{id:"a"|"b"|"c"|"d", text: string}]
- correctIndex (int 0-3) -> correctChoiceId ("a"|"b"|"c"|"d")
- explanation (string) -> preserve
- source (string) -> references[structured]
- tags (string[]) -> preserve (unique, non-empty)
- ageBand (kids|general|scholar) -> preserve
- status (enum) -> verification.status = "pending"
- version (int) -> removed
"""

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "questions"
CATEGORIES_PATH = ROOT / "data" / "categories.json"

# Map numeric category ID to string key
CATEGORY_MAP = {
    1: "shahada",
    2: "salah",
    3: "zakah",
    4: "sawm",
    5: "hajj",
}

CHOICE_IDS = ["a", "b", "c", "d"]

# Known hadith collections for normalization
HADITH_COLLECTIONS = {
    "bukhari": "sahih-bukhari",
    "البخاري": "sahih-bukhari",
    "صحيح البخاري": "sahih-bukhari",
    "muslim": "sahih-muslim",
    "مسلم": "sahih-muslim",
    "صحيح مسلم": "sahih-muslim",
    "متفق عليه": "muttafaqun-alayh",
    "المتفق عليه": "muttafaqun-alayh",
    "أبو داود": "sunan-abi-dawud",
    "أبي داود": "sunan-abi-dawud",
    "سنن أبي داود": "sunan-abi-dawud",
    "الترمذي": "sunan-tirmidhi",
    "سنن الترمذي": "sunan-tirmidhi",
    "النسائي": "sunan-nasai",
    "سنن النسائي": "sunan-nasai",
    "ابن ماجه": "sunan-ibn-majah",
    "سنن ابن ماجه": "sunan-ibn-majah",
    "مالك": "muwatta-malik",
    "موطأ مالك": "muwatta-malik",
    "أحمد": "musnad-ahmad",
    "مسند أحمد": "musnad-ahmad",
    "البيهقي": "sunan-bayhaqi",
    "سنن البيهقي": "sunan-bayhaqi",
    "الطبراني": "mujam-tabarani",
    "معجم الطبراني": "mujam-tabarani",
    "الدارقطني": "sunan-darqutni",
    "سنن الدارقطني": "sunan-darqutni",
    "الحاكم": "mustadrak-hakim",
    "مستدرك الحاكم": "mustadrak-hakim",
    "الذهبي": "siyar-alam-nubala",
    "سير أعلام النبلاء": "siyar-alam-nubala",
    "ابن حبان": "sahih-ibn-hibban",
    "صحيح ابن حبان": "sahih-ibn-hibban",
    "ابن خزيمة": "sahih-ibn-khuzayma",
    "صحيح ابن خزيمة": "sahih-ibn-khuzayma",
}


def normalize_hadith_collection(text: str) -> str | None:
    """Extract and normalize hadith collection from source text."""
    text_lower = text.lower()
    for key, value in HADITH_COLLECTIONS.items():
        if key in text_lower:
            return value
    return None


def parse_source(source: str) -> list[dict]:
    """Convert old source string to structured references array."""
    if not source or not source.strip():
        return [{"type": "other", "label": "غير محدد"}]

    source = source.strip()
    refs = []

    # Try to parse Quran references: "سورة X N" or "القرآن — سورة X N"
    # Pattern: سورة <name/number> <ayah>
    quran_pattern = r"سورة\s+([^\d\s]+?)\s+(\d+)"
    quran_match = re.search(quran_pattern, source)
    if quran_match:
        surah_name = quran_match.group(1).strip()
        ayah = int(quran_match.group(2))
        # Try to convert surah name to number
        surah_num = surah_name_to_number(surah_name)
        if surah_num:
            refs.append({"type": "quran", "surah": surah_num, "ayah": ayah})
            return refs

    # Pattern: "القرآن — سورة <name> <ayah>"
    quran_pattern2 = r"القرآن\s*[—-]\s*سورة\s+([^\d\s]+?)\s+(\d+)"
    quran_match2 = re.search(quran_pattern2, source)
    if quran_match2:
        surah_name = quran_match2.group(1).strip()
        ayah = int(quran_match2.group(2))
        surah_num = surah_name_to_number(surah_name)
        if surah_num:
            refs.append({"type": "quran", "surah": surah_num, "ayah": ayah})
            return refs

    # Pattern: "سورة X آية Y" or "سورة X Y"
    quran_pattern3 = r"سورة\s+(\d+)\s+(\d+)"
    quran_match3 = re.search(quran_pattern3, source)
    if quran_match3:
        surah = int(quran_match3.group(1))
        ayah = int(quran_match3.group(2))
        refs.append({"type": "quran", "surah": surah, "ayah": ayah})
        return refs

    # Try to parse Hadith references
    hadith_collection = normalize_hadith_collection(source)
    if hadith_collection:
        # Try to extract hadith number
        number_match = re.search(r"(?:رقم|حديث|عدد)\s*[:#]?\s*(\d+)", source)
        number = number_match.group(1) if number_match else "غير محدد"
        refs.append({"type": "hadith", "collection": hadith_collection, "number": number})
        return refs

    # Check for "حديث جبريل" or similar named hadiths
    if "حديث جبريل" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث جبريل"})
        return refs

    if "حديث ابن عمر" in source or "ابن عمر" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث ابن عمر"})
        return refs

    if "حديث أنس" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث أنس"})
        return refs

    if "حديث أبي هريرة" in source or "أبي هريرة" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث أبي هريرة"})
        return refs

    if "حديث عائشة" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث عائشة"})
        return refs

    if "حديث جابر" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث جابر"})
        return refs

    if "حديث ابن عباس" in source or "ابن عباس" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث ابن عباس"})
        return refs

    if "حديث ابن مسعود" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث ابن مسعود"})
        return refs

    if "حديث عمر" in source and "ابن الخطاب" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث عمر بن الخطاب"})
        return refs

    if "حديث علي" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث علي بن أبي طالب"})
        return refs

    if "حديث أبي ذر" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث أبي ذر"})
        return refs

    if "حديث معاذ" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث معاذ بن جبل"})
        return refs

    if "حديث عبادة" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث عبادة بن الصامت"})
        return refs

    if "حديث المسيء" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "حديث المسيء صلاته"})
        return refs

    if "حديث بدء الأذان" in source:
        refs.append({"type": "hadith", "collection": "sunan-abi-dawud", "number": "حديث بدء الأذان"})
        return refs

    if "حديث ابن عمر — متفق عليه" in source or "متفق عليه" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "متفق عليه"})
        return refs

    if "الصحيحان" in source or "البخاري ومسلم" in source:
        refs.append({"type": "hadith", "collection": "muttafaqun-alayh", "number": "الصحيحان"})
        return refs

    # Book references - known books
    book_patterns = [
        (r"الرحيق المختوم", "الرحيق المختوم"),
        (r"فقه الزكاة", "فقه الزكاة"),
        (r"فقه الصلاة", "فقه الصلاة"),
        (r"فقه الصوم", "فقه الصوم"),
        (r"فقه الحج", "فقه الحج"),
        (r"السيرة النبوية", "السيرة النبوية"),
        (r"السيرة والتاريخ", "السيرة النبوية"),
        (r"علوم القرآن", "علوم القرآن"),
        (r"عقيدة أهل السنة", "عقيدة أهل السنة"),
        (r"فقه الزكاة المعاصر", "فقه الزكاة المعاصر"),
        (r"التقويم الهجري", "التقويم الهجري"),
        (r"فقه العيدين", "فقه العيدين"),
        (r"فقه الوضوء", "فقه الوضوء"),
        (r"فقه الطهارة", "فقه الطهارة"),
        (r"فقه الجنائز", "فقه الجنائز"),
        (r"فقه النكاح", "فقه النكاح"),
        (r"فقه المواريث", "فقه المواريث"),
        (r"فقه المعاملات", "فقه المعاملات"),
        (r"فقه الطعام", "فقه الطعام"),
        (r"فقه الأيمان", "فقه الأيمان"),
        (r"فقه الطب", "فقه الطب"),
        (r"فقه الصلاة", "فقه الصلاة"),
        (r"فقه الحج", "فقه الحج"),
        (r"فقه الصوم", "فقه الصوم"),
        (r"فقه الزكاة", "فقه الزكاة"),
        (r"صفة الصلاة", "صفة الصلاة"),
        (r"أحاديث مقادير الصدقات", "أحاديث مقادير الصدقات"),
        (r"حديث الصدقات", "أحاديث مقادير الصدقات"),
    ]

    for pattern, title in book_patterns:
        if re.search(pattern, source):
            # Try to extract a locator (chapter/section)
            locator = None
            # Look for "باب ..." or "فصل ..."
            locator_match = re.search(r"(?:باب|فصل|قاعدة)\s+([^،,.;]+)", source)
            if locator_match:
                locator = locator_match.group(1).strip()
            refs.append({"type": "book", "title": title, "locator": locator} if locator else {"type": "book", "title": title})
            return refs

    # If we can't parse it, fall back to "other"
    refs.append({"type": "other", "label": source})
    return refs


SURAH_NAME_TO_NUMBER = {
    "الفاتحة": 1,
    "البقرة": 2,
    "آل عمران": 3,
    "النساء": 4,
    "المائدة": 5,
    "الأنعام": 6,
    "الأعراف": 7,
    "الأنفال": 8,
    "التوبة": 9,
    "يونس": 10,
    "هود": 11,
    "يوسف": 12,
    "الرعد": 13,
    "إبراهيم": 14,
    "الحجر": 15,
    "النحل": 16,
    "الإسراء": 17,
    "الكهف": 18,
    "مريم": 19,
    "طه": 20,
    "الأنبياء": 21,
    "الحج": 22,
    "المؤمنون": 23,
    "النور": 24,
    "الفرقان": 25,
    "الشعراء": 26,
    "النمل": 27,
    "القصص": 28,
    "العنكبوت": 29,
    "الروم": 30,
    "لقمان": 31,
    "السجدة": 32,
    "الأحزاب": 33,
    "سبأ": 34,
    "فاطر": 35,
    "يس": 36,
    "الصافات": 37,
    "ص": 38,
    "الزمر": 39,
    "غافر": 40,
    "فصلت": 41,
    "الشورى": 42,
    "الزخرف": 43,
    "الدخان": 44,
    "الجاثية": 45,
    "الأحقاف": 46,
    "محمد": 47,
    "الفتح": 48,
    "الحجرات": 49,
    "ق": 50,
    "الذاريات": 51,
    "الطور": 52,
    "النجم": 53,
    "القمر": 54,
    "الرحمن": 55,
    "الواقعة": 56,
    "الحديد": 57,
    "المجادلة": 58,
    "الحشر": 59,
    "الممتحنة": 60,
    "الصف": 61,
    "الجمعة": 62,
    "المنافقون": 63,
    "التغابن": 64,
    "الطلاق": 65,
    "التحريم": 66,
    "الملك": 67,
    "القلم": 68,
    "الحاقة": 69,
    "المعارج": 70,
    "نوح": 71,
    "الجن": 72,
    "المزمل": 73,
    "المدثر": 74,
    "القيامة": 75,
    "الإنسان": 76,
    "المرسلات": 77,
    "النبأ": 78,
    "النازعات": 79,
    "عبس": 80,
    "التكوير": 81,
    "الانفطار": 82,
    "المطففين": 83,
    "الانشقاق": 84,
    "البروج": 85,
    "الطارق": 86,
    "الأعلى": 87,
    "الغاشية": 88,
    "الفجر": 89,
    "البلد": 90,
    "الشمس": 91,
    "الليل": 92,
    "الضحى": 93,
    "الشرح": 94,
    "التين": 95,
    "العلق": 96,
    "القدر": 97,
    "البينة": 98,
    "الزلزلة": 99,
    "العاديات": 100,
    "القارعة": 101,
    "التكاثر": 102,
    "العصر": 103,
    "الهمزة": 104,
    "الفيل": 105,
    "قريش": 106,
    "الماعون": 107,
    "الكوثر": 108,
    "الكافرون": 109,
    "النصر": 110,
    "المسد": 111,
    "الإخلاص": 112,
    "الفلق": 113,
    "الناس": 114,
}


def surah_name_to_number(name: str) -> int | None:
    """Convert surah name to number."""
    name = name.strip()
    # Try direct number
    if name.isdigit():
        num = int(name)
        if 1 <= num <= 114:
            return num
    # Try name lookup
    return SURAH_NAME_TO_NUMBER.get(name)


def migrate_question(old_q: dict, category_key: str) -> dict:
    """Convert a single question from old format to V2."""
    # Build choices with ids a,b,c,d
    old_choices = old_q.get("choices", [])
    choices = []
    for i, choice_text in enumerate(old_choices):
        if i < 4:
            choices.append({"id": CHOICE_IDS[i], "text": choice_text})

    # Ensure exactly 4 choices
    while len(choices) < 4:
        choices.append({"id": CHOICE_IDS[len(choices)], "text": ""})

    # Map correctIndex to correctChoiceId
    correct_index = old_q.get("correctIndex", 0)
    correct_choice_id = CHOICE_IDS[correct_index] if 0 <= correct_index < 4 else "a"

    # Parse source to references
    source = old_q.get("source", "")
    references = parse_source(source)

    # Tags - ensure unique and non-empty
    tags = old_q.get("tags", [])
    tags = [t for t in tags if t and isinstance(t, str)]
    # Deduplicate while preserving order
    seen = set()
    unique_tags = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique_tags.append(t)

    # Build V2 question
    v2_question = {
        "id": old_q["id"],
        "categoryId": category_key,
        "ageBand": old_q.get("ageBand", "general"),
        "tier": old_q.get("difficulty", 1),
        "text": old_q["text"],
        "choices": choices,
        "correctChoiceId": correct_choice_id,
        "explanation": old_q["explanation"],
        "references": references,
        "tags": unique_tags,
        "verification": {
            "status": "pending",
            "verifiedAt": None,
        },
    }
    return v2_question


def migrate_file(filepath: Path, category_key: str) -> dict:
    """Migrate a single category file."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    old_questions = data.get("questions", [])
    migrated_questions = [migrate_question(q, category_key) for q in old_questions]

    return {
        "categoryId": category_key,
        "questions": migrated_questions,
    }


def main():
    print("Starting migration to Schema V2...")
    print(f"Reading categories from {CATEGORIES_PATH}")

    # Verify categories exist
    with open(CATEGORIES_PATH, encoding="utf-8") as f:
        categories = json.load(f)
    cat_keys = {c["id"] for c in categories}
    print(f"Found categories: {sorted(cat_keys)}")

    for cat_id, cat_key in CATEGORY_MAP.items():
        filepath = DATA_DIR / f"{cat_key}.json"
        if not filepath.exists():
            print(f"WARNING: {filepath} not found, skipping")
            continue

        print(f"\nMigrating {filepath.name}...")
        migrated_data = migrate_file(filepath, cat_key)

        # Write back
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(migrated_data, f, ensure_ascii=False, indent=2)

        print(f"  Migrated {len(migrated_data['questions'])} questions")

    print("\nMigration complete!")


if __name__ == "__main__":
    main()