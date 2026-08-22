# بنك الأسئلة الإسلامي — Islamic Question Bank

بنك أسئلة اختيار من متعدد بالعربية، منظّم حسب أركان الإسلام الخمسة، مستضاف على GitHub ويُستهلك كواجهة JSON ثابتة (Static API).

## الفئات

| id | المفتاح | الاسم |
|----|---------|-------|
| 1 | `shahada` | الشهادة |
| 2 | `salah` | الصلاة |
| 3 | `zakah` | الزكاة |
| 4 | `sawm` | الصوم |
| 5 | `hajj` | الحج |

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

`data/categories.json` — مصفوفة الفئات:

```json
[{ "id": 1, "key": "shahada", "name": "الشهادة" }]
```

`data/questions/<key>.json` — أسئلة فئة واحدة:

```json
{
  "categoryId": 1,
  "categoryKey": "shahada",
  "questions": [ ... ]
}
```

## مخطط السؤال

التعريف الكامل في `schema/question.schema.json`.

| الحقل | النوع | الوصف |
|-------|------|-------|
| `id` | string | معرّف فريد بصيغة `pg-<category>-<batch>-<n>` |
| `category` | int | معرّف الفئة (1–5) |
| `difficulty` | int | 1 = مبتدئ، 2 = أساسي، 3 = متوسط، 4 = متقدم، 5 = متخصص |
| `text` | string | نص السؤال |
| `choices` | string[] | الخيارات (2–6) |
| `correctIndex` | int | فهرس الإجابة الصحيحة |
| `explanation` | string | شرح الإجابة |
| `source` | string | مصدر السؤال (حديث، آية، كتاب…) |
| `tags` | string[] | وسوم موضوعية |
| `ageBand` | enum | `kids` / `general` / `scholar` |
| `status` | enum | `draft` / `reviewed` — يُنشر فقط ما هو `reviewed` |
| `version` | int | يُرفع عند أي تعديل جوهري على السؤال |

## المساهمة

1. افتح PR يضيف/يعدّل الأسئلة في ملف الفئة المناسب.
2. CI يتحقق تلقائيًا من صحة المخطط، تفرد المعرفات، ومراجع الفئات.
3. لا يُدمج أي سؤال قبل أن يكون `status: "reviewed"`.

## التحقق محليًا

```bash
pip install jsonschema
python scripts/validate.py
```
