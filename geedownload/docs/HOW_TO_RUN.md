# كيف أشغّل geedownload؟ (من الصفر، بثلاث طرق)

## 0. التحضير (مرة واحدة)

**1) بايثون 3.9 أو أحدث**، ثم أنشئ بيئة نظيفة وثبّت الحزمة:

```bash
python -m venv gd-env
# Windows:      gd-env\Scripts\activate
# Linux / Mac:  source gd-env/bin/activate

pip install "geedownload[all] @ git+https://github.com/yamenetoo/RremoteSensing.git#subdirectory=geedownload"
```

> على لينكس (Ubuntu/Debian) لنافذة Tkinter ثبّت أيضاً: `sudo apt install python3-tk`

**2) حساب Google Earth Engine** (لتنزيل صور الأقمار الصناعية فقط؛ البحث وخرائط الحدود لا تحتاجه):

1. أنشئ مشروعاً في Google Cloud وفعّل Earth Engine: <https://earthengine.google.com/signup>
2. سجّل الدخول مرة واحدة: `earthengine authenticate`
3. اسم المشروع (`my-ee-project`) ستمرّره للحزمة، أو اضبطه كمتغير بيئة:
   ```bash
   export EE_PROJECT=my-ee-project        # Windows PowerShell:  $env:EE_PROJECT="my-ee-project"
   ```

**3) اختبار سريع:** `geedownload about` ثم `geedownload datasets`.

---

## الطريقة 1: بالكود (Python)

```python
import geedownload as gd
gd.set_verbose()

# أ) ابحث عن المنطقة وانظر المرشّحين
for i, p in enumerate(gd.search_area("Masyaf, Syria")):
    print(i, p)

# ب) نزّل صورة Sentinel-2 + حدود المنطقة shapefile + خريطة معاينة
res = gd.download_area(
    "Masyaf, Syria", "sentinel2", "2023-06-01", "2023-09-30",
    out_dir="out", cloud_max=10, bands=["B4", "B3", "B2", "B8"],
    mask_clouds=True, project="my-ee-project")
print(res.folder, res.shapefile, res.stack)

# ج) خريطة JPG (شبكة، إحداثيات، مقياس رسم، مفتاح خارج الإطار، خريطة الدولة المصغّرة خارج الإطار)
gd.plot_map(res.stack, "masyaf.jpg", area="Masyaf, Syria", bands=["B4", "B3", "B2"])
```

نفس العمل بسطر أوامر (CLI):

```bash
geedownload download "Masyaf, Syria" -d sentinel2 --start 2023-06-01 --end 2023-09-30 \
        --cloud 10 --bands B4 B3 B2 --out out --project my-ee-project --map
```

بلا Earth Engine (حدود فقط): `gd.search_and_save("Masyaf, Syria", out_dir="out")`.

---

## الطريقة 2: بالواجهة الرسومية (Tkinter) — عربي / فارسي / English

```bash
geedownload gui               # الإنجليزية
geedownload gui --lang ar     # العربية   (أو --lang fa للفارسية)
```

الخطوات داخل النافذة:

1. **تبويب 1 (البحث):** اكتب اسم المنطقة ← «بحث» ← اختر نتيجة ← «استخدام هذه المنطقة» (أو «حفظ shapefile…»).
2. **تبويب 2 (التنزيل):** اختر المجموعة (sentinel2…)، التاريخ، النطاقات، مجلد الإخراج، واكتب **مشروع Earth Engine** ← «بدء التنزيل». تظهر خريطة المعاينة عند الانتهاء، والسجل أسفل النافذة.
3. **تبويب 3 (الخرائط):** خريطة من ملف GeoTIFF، أو خريطة حدود لمنطقة/دولة.
4. **حول:** معلومات المؤلف.

اللغة تتبدّل من القائمة أعلى النافذة في أي وقت. إن ظهرت الحروف العربية مقطّعة على لينكس: `pip install arabic-reshaper python-bidi`.

---

## الطريقة 3: عبر localhost (خادم REST API + واجهة المتصفح)

```bash
export EE_PROJECT=my-ee-project
export GEEDOWNLOAD_API_KEY=change-me        # اختياري: يطلب مفتاحاً في كل طلب
geedownload webgui                          # يشغّل الخادم ويفتح http://127.0.0.1:8000/app
# أو الخادم فقط:   geedownload serve --port 8000
```

| الرابط | ما هو |
|---|---|
| <http://127.0.0.1:8000/app> | واجهة المتصفح بثلاث لغات (إن وُضع مفتاح API فاكتبه في خانة «مفتاح API») |
| <http://127.0.0.1:8000/docs> | توثيق الـ API التفاعلي (Swagger) لتجربة كل الدوال |

مثال من الطرفية (`curl`):

```bash
H='X-API-Key: change-me'
curl -H "$H" "http://127.0.0.1:8000/search?q=Masyaf,%20Syria"
curl -H "$H" -H 'Content-Type: application/json' -X POST http://127.0.0.1:8000/jobs/download \
     -d '{"area":"Masyaf, Syria","dataset":"sentinel2","start":"2023-06-01","end":"2023-09-30","cloud_max":10}'
# -> {"job_id": "3f9c1a7b2d44", ...}     ثم تابع:  curl -H "$H" http://127.0.0.1:8000/jobs/3f9c1a7b2d44
```

لفتح الخادم لأجهزة أخرى في الشبكة استعمل `--host 0.0.0.0` (ومعه `GEEDOWNLOAD_API_KEY` دائماً).

---

## مشاكل شائعة

| المشكلة | الحل |
|---|---|
| `Earth Engine ... not authenticated` | نفّذ `earthengine authenticate` ومرّر `project=` أو `EE_PROJECT` |
| `No module named tkinter` | `sudo apt install python3-tk` (لينكس) |
| البحث لا يعطي نتائج | أضف اسم الدولة: `"Masyaf, Syria"` |
| حدود الدولة غير ظاهرة على الخريطة | تُحمَّل مرة واحدة من Natural Earth وتحتاج إنترنت؛ بدونها تُرسم الخريطة بلا تلك الطبقات |
| الطلب كبير جداً | الحزمة تقسّم المنطقة تلقائياً؛ قلّل `scale` أو المساحة (حدّ الـ API `GEEDOWNLOAD_MAX_AREA_KM2`) |

المؤلف: محمد يامن المحمد — yamenmohamad@tabrizu.ac.ir
