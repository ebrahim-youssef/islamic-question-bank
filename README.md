# بنك الأسئلة الإسلامي — Islamic Question Bank

بنك أسئلة اختيار من متعدد بالعربية، منظّم حسب أركان الإسلام الخمسة، مستضاف على GitHub ويُستهلك كواجهة JSON ثابتة (Static API).

## الفئات (Category Taxonomy V2)

التاكسونومي الجديد هرمي — كل فئة لها `id` فريد، `name` بالعربية، و `parentId` اختياري.

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

للإنتاج، اربط المستهلكين بإصدار (tag) بدل `main` حتى لا يتغير المحتوى تحتهم فجأة:

```
https://cdn.jsdelivr.net/gh/<owner>/<repo>@v1.0.0/data/questions/salah.json
```

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
| `verification` | object | `{ "status": "pending"|"verified"|"needs_review", "verifiedAt": "ISO8601|null" }` |

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

جميع الأسئلة المهاجرة تبدأ بـ:
```json
"verification": { "status": "pending", "verifiedAt": null }
```

الحالات المسموحة:
- `pending` — في انتظار المراجعة (افتراضي للمهجرة)
- `verified` — تم التحقق بشريًا، `verifiedAt` مطلوب
- `needs_review` — بحاجة لمراجعة متخصصة

التحقق الفعلي للمحتوى الديني يتم **بعد** ترحيل المخطط.

## الحقول المزالة (من المخطط القديم)

| الحقل القديم | البديل في V2 |
|-------------|--------------|
| `category` (int) | `categoryId` (string) |
| `difficulty` (int) | `tier` (int) |
| `correctIndex` (int) | `correctChoiceId` (string) |
| `source` (string) | `references[]` (structured) |
| `status` (enum) | `verification.status` |
| `version` (int) | — مزالة |

ملاحظة: الحالة السابقة `reviewed` **لا** تتحول تلقائيًا إلى `verified`.

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

## الترحيل إلى V2

للترحيل من المخطط القديم، استخدم سكريبت الترحيل:

```bash
python scripts/migrate_to_v2.py
```

السكريبت يقوم بـ:
1. الحفاظ على `id` الحالي
2. تحويل `category` الرقمي إلى `categoryId` النصي
3. إعادة تسمية `difficulty` إلى `tier`
4. تحويل الخيارات الأربعة إلى كائنات `{id, text}` بمعرفات `a,b,c,d`
5. تحويل `correctIndex` إلى `correctChoiceId` المقابل
6. الحفاظ على النص، الشرح، الوسوم، و `ageBand`
7. تحويل `source` إلى `references` منظمة عند الإمكان، وإلا `other`
8. تعيين `verification.status = "pending"` و `verifiedAt = null`
9. إزالة `status` و `version` القديمين

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