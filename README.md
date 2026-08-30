# بنك الأسئلة الإسلامي — Islamic Question Bank

بنك أسئلة اختيار من متعدد بالعربية، منظّم حسب أركان الإسلام الخمسة، مستضاف على GitHub ويُستهلك كواجهة JSON ثابتة (Static API).

> **ملاحظة:** يُعدّ `data/` حاليًا بنك الأسئلة المرجعي (canonical) الذي يستخدمه تطبيق Arkan.

## الفئات (Category Taxonomy V2)

التاكسونومي الجديد هرمي — كل فئة لها `id` فريد، `name` بالعربية، و `parentId` مطلوب؛ تكون قيمته `null` للفئة الجذرية، أو معرّف الفئة الأب للفئات الفرعية.

| id | الاسم | parentId |
|----|-------|----------|
| `arkan-al-islam` | أركان الإسلام | `null` (جذر) |
| `shahada` | الشهادة | `arkan-al-islam` |
| `salah` | الصلاة | `arkan-al-islam` |
| `zakah` | الزكاة | `arkan-al-islam` |
| `sawm` | الصوم | `arkan-al-islam` |
| `hajj` | الحج | `arkan-al-islam` |

الأسئلة تخزن `categoryId` الذي يشير لفئة ورقة (leaf) فقط — لا يوجد تكرار لمعلومات الفئة الأب داخل السؤال.

## الاستهلاك كـ API

كل ملف متاح عبر raw.githubusercontent.com أو jsDelivr (مع تخزين مؤقت وترويسات CORS):

```
https://cdn.jsdelivr.net/gh/<owner>/<repo>@main/data/categories.json
https://cdn.jsdelivr.net/gh/<owner>/<repo>@main/data/questions/salah.json
```

للإنتاج، اربط المستهلكين بفرع `release` بدل `main` حتى لا يتغير المحتوى تحتهم فجأة:

```
https://cdn.jsdelivr.net/gh/<owner>/<repo>@release/data/questions/salah.json
```

## الفرق بين `main` و `release`

`main` هو سجل المحتوى: كل سؤال يصل إليه عبر PR مراجَع، ودمجه يدوي لا آلي.

`release` هو ما تشحنه التطبيقات فعلًا، وهو مجموعة جزئية مختارة من `main`. الفرق
ليس في التوقيت وحده: فئة على `main` قد تحمل سؤالًا واحدًا وهي بذلك غير صالحة
للّعب، فلا تُنقل إلى `release` حتى تكتمل. لذلك قد يحمل الفرعان عددًا مختلفًا من
الفئات، وهذا مقصود.

يترتب على ذلك أن لكل فرع بيانه الخاص: بعد أي دمج من `main` إلى `release` يجب
إعادة توليد `data/manifest.json` على `release`، وإلا وصف البيانُ بنكًا غير
الموجود. فحص `scripts/validate.py` يمنع ذلك، ويعمل على الفرعين.

## بيان المحتوى

يصف `data/manifest.json` ملفات بنك الأسئلة المرجعي وأحجامها وتجزئات SHA-256
الخاصة ببايتاتها الخام. يجلبه المستهلك أولًا ويقارن `bankHash` بالقيمة المخزنة
لديه، فلا ينزّل ملفات الأسئلة إلا عندما يتغير المحتوى، ثم يتحقق من تجزئة كل
ملف قبل اعتماده.

تجمع `totalBytes` أحجام ملفات الأسئلة، ويبقى حجم `data/categories.json` مبينًا
في سجل `categories` المستقل.

البيان ملف مولّد بواسطة `python scripts/build_manifest.py` ولا يُعدّل يدويًا.
ولا يتضمن `generatedAt` عمدًا؛ لأن وقت الإنشاء لا يصف المحتوى، وإضافته تجعل
البيان يختلف بين تشغيلين متطابقين وتمنع `--check` من كشف الانحراف بلا ضوضاء.

### شكل الملفات

`data/categories.json` — مصفوفة الفئات الهرمية:

```json
[
  { "id": "arkan-al-islam", "name": "أركان الإسلام", "parentId": null },
  { "id": "shahada", "name": "الشهادة", "parentId": "arkan-al-islam" }
]
```

`data/questions/<key>.json` — أسئلة فئة واحدة:

```json
{
  "categoryId": "salah",
  "questions": [ ... ]
}
```

## مخطط السؤال (Schema V2)

التعريف الكامل في `schema/question.schema.json`.

| الحقل | النوع | الوصف |
|-------|------|-------|
| `id` | string | معرّف فريد مستقر (مثال: `pg-1-1-1`, `kid-sh-3`) |
| `categoryId` | string | مفتاح الفئة من التاكسونومي (مثال: `shahada`) |
| `ageBand` | enum | `kids` / `general` / `scholar` — الجمهور المستهدف |
| `tier` | integer | 1–5 — مستوى التقدم داخل الـ age band |
| `text` | string | نص السؤال بالعربية (غير فارغ) |
| `choices` | object[4] | 4 خيارات بالضبط، كل خيار: `{ "id": "a"|"b"|"c"|"d", "text": "..." }` |
| `correctChoiceId` | string | `a` أو `b` أو `c` أو `d` — يطابق `choices[].id` |
| `explanation` | string | شرح الإجابة الصحيحة (غير فارغ) |
| `references` | object[] | مراجع منظمة — قرآن، حديث، كتاب، أو `other` |
| `tags` | string[] | وسوم موضوعية فريدة غير فارغة |
| `verification` | object | `{ "status": "pending"\|"verified"\|"needs_review", "verifiedAt": "RFC 3339 date-time"\|null }` |

### أنواع المراجع (References)

**قرآن:**
```json
{ "type": "quran", "surah": 2, "ayah": 255 }
```

**حديث:**
```json
{ "type": "hadith", "collection": "sahih-bukhari", "number": "8" }
```

**كتاب/مرجع فقهي:**
```json
{ "type": "book", "title": "الرحيق المختوم", "locator": "باب الهجرة" }
```

**مصدر آخر/غير محدد:**
```json
{ "type": "other", "label": "نص المصدر الأصلي" }
```

### حالة التحقق (Verification)

جميع الأسئلة تبدأ بـ:
```json
"verification": { "status": "pending", "verifiedAt": null }
```

الحالات المسموحة:
- `pending` — في انتظار المراجعة (افتراضي). `verifiedAt` يكون `null`
- `verified` — تم التحقق بشريًا. `verifiedAt` **مطلوب** ويجب أن يكون timestamp بتنسيق RFC 3339 (مثال: `"2025-01-15T10:30:00Z"`)
- `needs_review` — بحاجة لمراجعة متخصصة. `verifiedAt` يكون `null`

## التحقق من المحتوى

يتم التحقق من صحة المحتوى الديني بشكل منفصل عن التحقق من المخطط.

## المساهمة

1. افتح PR يضيف/يعدّل الأسئلة في ملف الفئة المناسب (`data/questions/<key>.json`).
2. CI يتحقق تلقائيًا من:
   - صحة المخطط (JSON Schema V2)
   - تفرد المعرفات (`id` و `choices[].id`)
   - مراجع الفئات (`categoryId` موجود في التاكسونومي)
   - عدد الخيارات = 4، و `correctChoiceId` يطابق خيارًا واحدًا
   - `tier` في 1..5، `ageBand` صالح
   - الوسوم فريدة وغير فارغة
   - المراجع تتبع أحد الأنماط المدعومة
   - `verification.status` صالح، و `verifiedAt` معدوم إلا عند `verified`
   - لا نصوص أسئلة مكررة + ageBand داخل نفس الفئة
3. لا يُدمج أي سؤال قبل أن يكون `verification.status` مناسبًا (للأسئلة الجديدة: `pending`، للمراجعة: `needs_review`، للمصادق عليها: `verified`).

## التحقق محليًا

```bash
pip install jsonschema
python scripts/validate.py
```

## Property: ثبات الإجابة الصحيحة

السبب الرئيسي لاستبدال `correctIndex` بـ `correctChoiceId` هو جعل الصحة مستقلة عن ترتيب الخيارات.

هذا يجب أن يظل صحيحًا دائمًا:
```json
{
  "choices": [
    { "id": "c", "text": "..." },
    { "id": "a", "text": "..." },
    { "id": "d", "text": "..." },
    { "id": "b", "text": "..." }
  ],
  "correctChoiceId": "b"
}
```

أي خلط (shuffling)، تسلسل (serialization)، جلب (fetching)، أو ترحيل (migration) يجب ألا يغير الإجابة الصحيحة بصمت.
