# بنك الأسئلة الإسلامي — Islamic Question Bank

بنك أسئلة اختيار من متعدد بالعربية، مستضاف على GitHub ويُستهلك كواجهة JSON ثابتة (Static API).

## المصدر الأساسي للمحتوى

المحتوى المعتمد حاليًا للتطبيق موجود تحت `data/`:

- `data/categories.json` — التاكسونومي الهرمي للفئات.
- `data/questions/<categoryId>.json` — أسئلة كل فئة ورقية (leaf category).

مجلد `content/` ليس جزءًا من مسار التحقق الحالي ولا يُعد المصدر الأساسي لبيانات التطبيق في هذه المرحلة.

## الفئات (Category Taxonomy V2)

كل فئة لها `id` فريد و`name` بالعربية و`parentId`. الجذر يستخدم `parentId: null`، والأسئلة ترتبط فقط بفئات ورقية.

| id | الاسم | parentId |
|----|-------|----------|
| `arkan-al-islam` | أركان الإسلام | `null` |
| `shahada` | الشهادة | `arkan-al-islam` |
| `salah` | الصلاة | `arkan-al-islam` |
| `zakah` | الزكاة | `arkan-al-islam` |
| `sawm` | الصوم | `arkan-al-islam` |
| `hajj` | الحج | `arkan-al-islam` |

## الاستهلاك كـ API

```text
https://cdn.jsdelivr.net/gh/<owner>/<repo>@main/data/categories.json
https://cdn.jsdelivr.net/gh/<owner>/<repo>@main/data/questions/salah.json
```

للإنتاج، يُفضّل الربط بإصدار (tag) بدل `main`.

## Question Schema V2

التعريف الكامل في `schema/question.schema.json`.

| الحقل | الوصف |
|-------|-------|
| `id` | معرّف فريد ومستقر للسؤال |
| `categoryId` | فئة ورقية من `data/categories.json` |
| `ageBand` | `kids` / `general` / `scholar` |
| `tier` | رقم من 1 إلى 5 داخل الـ age band |
| `text` | نص السؤال |
| `choices` | أربعة كائنات `{ id, text }` بالضبط |
| `correctChoiceId` | معرّف الخيار الصحيح، مستقل عن ترتيب المصفوفة |
| `explanation` | شرح الإجابة |
| `references` | مراجع منظمة |
| `tags` | وسوم فريدة غير فارغة |
| `verification` | حالة التحقق وتاريخها |

### الخيارات والإجابة الصحيحة

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

صحة الإجابة تعتمد على `id` وليس على موضع الخيار في المصفوفة؛ لذلك تغيير ترتيب الخيارات لا يغير الإجابة الصحيحة.

### أنواع المراجع

**قرآن**

```json
{ "type": "quran", "surah": 2, "ayah": 255 }
```

**حديث**

```json
{ "type": "hadith", "collection": "sahih-bukhari", "number": "8" }
```

**كتاب/مرجع**

```json
{ "type": "book", "title": "الرحيق المختوم", "locator": "باب الهجرة" }
```

**مصدر آخر أو غير محسوم**

```json
{ "type": "other", "label": "نص المصدر كما هو" }
```

لا تُخمن بيانات مرجع غير موجودة في المصدر. إذا تعذر تمثيل المرجع بدقة، استخدم `other` إلى أن تتم مراجعته.

### التحقق

```json
"verification": {
  "status": "pending",
  "verifiedAt": null
}
```

الحالات المسموحة:

- `pending`
- `verified` — يتطلب `verifiedAt` بصيغة date-time.
- `needs_review`

`verifiedAt` يجب أن يكون `null` ما لم تكن الحالة `verified`.

## المساهمة

1. عدّل السؤال في ملف الفئة المناسب تحت `data/questions/`.
2. لا تغيّر `correctChoiceId` بسبب إعادة ترتيب الخيارات؛ قارنه دائمًا بمعرّفات الخيارات.
3. لا تعتبر المحتوى `verified` إلا بعد التحقق الفعلي من السؤال والإجابة والشرح والمراجع.
4. شغّل التحقق قبل الدمج.

## التحقق محليًا

```bash
pip install jsonschema
python scripts/validate.py
```

التحقق يفشل عند وجود، من ضمن أمور أخرى:

- JSON Schema غير صالح أو سؤال لا يطابق Question Schema V2.
- فئة غير موجودة، parent غير صالح، دورة في شجرة الفئات، أو سؤال مربوط بفئة غير ورقية.
- `id` سؤال مكرر.
- عدد خيارات غير 4 أو معرّفات/نصوص خيارات مكررة.
- `correctChoiceId` لا يطابق خيارًا واحدًا بالضبط.
- `tier` أو `ageBand` أو `verification` غير صالح.
- مرجع لا يطابق أحد أنواع المراجع الأربعة.
- نص سؤال مكرر لنفس `ageBand` داخل الفئة نفسها.
