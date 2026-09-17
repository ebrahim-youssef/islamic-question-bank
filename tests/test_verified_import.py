import unittest
import json
from pathlib import Path

from scripts.import_verified_markdown import convert_file


class VerifiedMarkdownImportTest(unittest.TestCase):
    def test_imported_canonical_file_has_source_derived_contract(self):
        root = Path(__file__).parents[1]
        data = json.loads((root / "data/questions/salah.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["questions"]), 75)
        self.assertEqual(data["questions"][0]["evidence"][0]["kind"], "hadith_inference")
        self.assertEqual(data["questions"][0]["verificationNote"], "رقم الحديث ووجه الدلالة طوبقا على متن الصحيح")

    def test_salah_source_converts_all_questions_with_provenance(self):
        root = Path(__file__).parents[1]
        questions = convert_file(root / "tests/fixtures/verified_sample.md", "salah", "2025-01-01T00:00:00Z", strict=False)
        self.assertEqual(len(questions), 1)
        first = questions[0]
        self.assertEqual(first["id"], "salah-kids-t1-q01")
        self.assertEqual(first["correctChoiceId"], "b")
        self.assertEqual(first["evidence"][0]["kind"], "quran_text")
        self.assertEqual(len(first["evidence"]), 2)
        self.assertEqual(first["verificationNote"], "تم التحقق من المصدر")
        self.assertEqual(first["verification"], {"status": "verified", "verifiedAt": "2025-01-01T00:00:00Z"})
        self.assertEqual(first["tags"], ["category:salah", "age:kids", "tier:1", "evidence:quran_text"])

    def test_quran_range_is_structured(self):
        root = Path(__file__).parents[1]
        questions = convert_file(root / "tests/fixtures/verified_sample.md", "hajj", "2025-01-01T00:00:00Z", strict=False)
        quran_refs = [r for q in questions for r in q["references"] if r["type"] == "quran"]
        self.assertTrue(quran_refs)
        self.assertTrue(any("ayahEnd" in ref for ref in quran_refs))

    def test_malformed_source_is_rejected(self):
        root = Path(__file__).parents[1]
        malformed = root / "tests/fixtures/malformed.md"
        with self.assertRaises(ValueError):
            convert_file(malformed, "salah", "2025-01-01T00:00:00Z", strict=False)


if __name__ == "__main__":
    unittest.main()
