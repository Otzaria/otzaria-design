# גרפיקת מסייע ההורדות של אוצריא

התיקייה הזו מייצרת את כל הגרפיקה של **מסייע ההורדות של אוצריא ל-Windows** (אשף Inno Setup,
`installer/download_assistant.iss` בריפו הראשי): אנימציית הספר הנפתח במסך הפתיחה, בלוק הכותרת
(בעברית ובאנגלית),
וכל רכיבי הממשק (כפתורי חלון, כפתורים, כרטיסים, תיבות סימון, אריחי אייקונים, נקודות שלבים,
פס התקדמות, שדה תיקייה ותגי סיום).

הכול נוצר בקוד, מתוך סקריפט אחד — `build_assistant_art.py`. אין כאן קובצי עיצוב ידניים: כדי לשנות
משהו משנים קבוע בסקריפט ומריצים מחדש.

## איך הריפו הראשי צורך את זה

החוזה המיועד (צד הריפו הראשי עדיין לא נכתב):

- הריפו הראשי **לא** מריץ את הסקריפט ולא שומר PNG בגיט. הוא נועץ גרסה אחת (מספר גרסה + SHA-256)
  של ה-zip שב-Release של הריפו הזה.
- לפני הקומפילציה ב-ISCC מורידים את ה-zip, מאמתים SHA-256 ופורסים אותו ל-`installer\assistant_art\`.
- `download_assistant.iss` מבצע `#include "assistant_art\assistant_art.isi"` ולוקח משם את כל המספרים;
  `AA_ART_VERSION` מאפשר לוודא שהגרסה שהורדה היא הנעוצה.

## מבנה

| נתיב | מה יש בו |
|---|---|
| `pack_release.py` | אורז את `out\` ל-zip של Release, דטרמיניסטי |
| `build_assistant_art.py` | הסקריפט. כל מה שניתן לכוונן נמצא בבלוק אחד בראשו (צבעים, טקסטים, גדלים, תזמונים, אנימציה, אייקונים) |
| `sources/` | הקלטים בלבד: הלוגו `iconnew.png`, גופני Fluent System Icons וגופן האייקונים של אוצריא (`otzaria_icons.otf`). מקור ורישיון של כל קובץ ב-`sources/LICENSES.md` |
| `CHANGELOG.md` | יומן גרסאות של הגרפיקה |
| `requirements.txt` | גרסאות נעוצות של Pillow, ‏numpy ו-fontTools (רינדור עלול להשתנות בין גרסאות) |
| `out/` | הפלט (לא נשמר בגיט): כל קובצי ה-PNG + `assistant_art.isi` |
| `preview/` | תצוגה מקדימה (לא נשמרת בגיט): `welcome.gif`, `welcome@2x.gif`, `welcome_en.gif`, `welcome_en@2x.gif`, `contact_sheet.png` |

## הכנה (פעם אחת)

**ההרצה חייבת להיות על Windows.** הטקסטים (שני בלוקי הכותרת — `title_N` בעברית ו-`title_en_N`
באנגלית — התצוגה המקדימה ודף הנכסים) כתובים ב-Segoe UI — הגופן שבו האפליקציה ו-Inno מציגים טקסט
ב-Windows. הסקריפט קורא אותו מ-`%WINDIR%\Fonts` (`segoeui.ttf`, `seguisb.ttf`) ונעצר עם הודעה ברורה
אם הוא חסר. **אסור להעתיק את Segoe UI לריפו**: הרישיון של Microsoft לא מתיר להפיץ אותו, והריפו ציבורי.

```powershell
py -m pip install -r requirements.txt
```

`sources/` כבר שמורה בריפו. אם צריך לרענן אותה מתוך הריפו של אוצריא ומה-pub cache של Flutter
(למשל אחרי שינוי לוגו או עדכון חבילת האייקונים):

```powershell
py build_assistant_art.py --collect-sources --otzaria C:\path\to\otzaria
```

ברירת המחדל של `--otzaria` היא `..\..\otzaria` ביחס לסקריפט. גרסת חבילת האייקונים מוגדרת
בקבוע `FLUENT_PACKAGE`. הרצה רגילה לא תלויה בריפו של אוצריא ולא ב-pub cache — רק ב-`sources/`.

## הפקה ותצוגה מקדימה

```powershell
py build_assistant_art.py                       # פלט ל-out\
py build_assistant_art.py --out <תיקייה>        # פלט לתיקייה אחרת (למשל installer\assistant_art בריפו הראשי)
py build_assistant_art.py --preview             # גם תצוגה מקדימה ל-preview\
```

ההרצה לוקחת כמה דקות (האנימציה מרונדרת בתלת-ממד ברזולוציה גבוהה, וכל קנה מידה נגזר ממנה).

התצוגה המקדימה:
- `welcome.gif` / `welcome@2x.gif` — רצף הפתיחה בגודל החלון האמיתי (400×660 ו-800×1320):
  הספר נפתח, עולה, הכותרת נכנסת ואחריה השורה התחתונה והכפתור. בתזמון של הקוד ב-Inno.
- `welcome_en.gif` / `welcome_en@2x.gif` — אותו רצף באנגלית, משמאל לימין (כותרת החלון משמאל,
  מזעור וסגירה מימין) עם `title_en_N`.
- `contact_sheet.png` — כל נכס ב-200% על צבע הדף, עם שמו (הספר והכותרת מוקטנים מ-250%, כמו במסייע).

**תמיד להסתכל על התצוגה המקדימה לפני פרסום.**

## מה הסקריפט מייצר

לכל נכס יש קובץ לכל קנה מידה של DPI ב-`SCALES` (100, 125, 150, 175, 200, 250), בשם
`<נכס>_<קנה מידה>.png`. הגודל בפיקסלים = הגודל ב-100% כפול קנה המידה, מעוגל חצי כלפי מעלה
(כמו `ScaleX` של Inno).

**חוץ מהספר והכותרת:** `book_NN`, ‏`title_N` ו-`title_en_N` (רוב הגודל) נוצרים רק בקנה המידה הגדול ביותר
(`BOOK_SRC_SCALE`, `TITLE_SRC_SCALE` = 250), והמסייע מקטין אותם ב-Stretch של Inno. הקטנה בלבד:
הגדלה מ-200% ל-250% נמדדה 34.9 dB, הקטנה מ-250% לכל קנה מידה אחר 44.5–46.8 dB.

כפתורים, כרטיסים ושדות נוצרים עם פינות שקופות, כך שאותה תמונה משמשת גם על הדף וגם בדו-שיח.
רק כפתורי החלון (`cap_*`) צבועים מראש בצבע סרגל הכותרת.

בנוסף נוצר `assistant_art.isi` — קובץ include ל-Inno עם `#define` לכל מספר שהקוד צריך. הקוד ב-Inno
לוקח את המספרים רק משם, ולכן שינוי גודל או תזמון בסקריפט עובר לקוד אוטומטית והקוד והגרפיקה לא
יכולים להיסחף זה מזה. הקובץ נוצר אוטומטית — לא לערוך ידנית.

### ה-defines ב-`assistant_art.isi`

| define | משמעות |
|---|---|
| `AA_ART_VERSION` | גרסת הגרפיקה (`ART_VERSION`), לאימות מול הנעיצה |
| `AA_SCALES`, `AA_SCALE_COUNT` | רשימת קני המידה (באחוזים, מופרדים בפסיק) ומספרם |
| `AA_BOOK_SRC_SCALE`, `AA_TITLE_SRC_SCALE` | קנה המידה היחיד שבו קיימים `book_NN`, ‏`title_N` ו-`title_en_N`; המסייע מציג אותם מתוחים לגודל `AA_BOOK_W/H`, `AA_TITLE_W/H` |
| `AA_TITLE_EN` | ‏`1` כשבלוק הכותרת האנגלי קיים (`title_en_0`..`title_en_7`, אותו גודל, אותם שלבים ואותו קנה מידה כמו `title_N`). אם הוא לא מוגדר — גרפיקה ישנה בלי אנגלית |
| `AA_BOOK_FRAMES`, `AA_BOOK_FPS`, `AA_BOOK_FRAME_MS` | מספר פריימי הספר, קצב הפריימים ומשך פריים במילישניות |
| `AA_PAGE_FADE_MS` | משך דהיית הדף לפני תחילת האנימציה |
| `AA_BOOK_TOP`, `AA_BOOK_RISE` | מיקום עליון של הספר בפתיחה, וכמה הוא עולה אחר כך |
| `AA_RISE_MS`, `AA_RISE_START_FRAME` | משך העלייה והפריים שבו היא מתחילה |
| `AA_TITLE_TOP`, `AA_TITLE_SLIDE`, `AA_TITLE_FADE_MS`, `AA_TITLE_STEPS` | מיקום בלוק הכותרת, מרחק ההחלקה, משך הדהייה ומספר שלבי הדהייה (`title_0`..`title_7`) |
| `AA_NOTE_TOP`, `AA_START_BUTTON_TOP` | מיקום עליון של השורה התחתונה ושל כפתור ההתחלה |
| `AA_RADIUS` | רדיוס הפינות (8) |
| `AA_BOOK_W/H`, `AA_TITLE_W/H` | גודל פריים הספר ובלוק הכותרת |
| `AA_MARK_SIZE`, `AA_LOGO_SIZE` | גודל הסימן הקטן (`mark_*`) והלוגו (`logo_*`) |
| `AA_TITLE_BAR_H`, `AA_CAP_W/H` | גובה סרגל הכותרת וגודל כפתורי החלון |
| `AA_BTN_PRIMARY/WIDE/GHOST/OUTLINE/TONAL/TONALWIDE_W/H` | גודל ששת סוגי הכפתורים |
| `AA_CARD_W`, `AA_CARD_CAP_H`, `AA_CARD_MID_H`, `AA_CARD_SHADOW` | כרטיס בשלוש פרוסות: רוחב, גובה הקצוות, גובה האמצע וצל (0: כמו AppCard, בלי צל) |
| `AA_TOGGLE_SIZE` | גודל רדיו ותיבת סימון |
| `AA_ICON_SIZE`, `AA_ICON_NAMES` | גודל אריח אייקון ורשימת שמות האייקונים (`ico_<שם>`) |
| `AA_DOT_SIZE`, `AA_DOT_CUR_W` | נקודת שלב רגילה ורוחב הנקודה הנוכחית |
| `AA_BAR_CAP_W`, `AA_BAR_MID_W`, `AA_BAR_H` | פס ההתקדמות: קצה, אמצע וגובה |
| `AA_FIELD_W/H` | גודל מסגרת שדה התיקייה |
| `AA_BADGE_SIZE` | גודל תגי הסיום |
| `AA_CLR_*` | הפלטה כערכי TColor של Inno (`0xBBGGRR`): `PAGE`, `TITLE_BAR`, `TITLE_BAR_BORDER`, `CAPTION_HOVER`, `CAPTION_GLYPH`, `CARD`, `CARD_SEL`, `DIVIDER`, `OUTLINE`, `PRIMARY`, `ON_PRIMARY`, `DISABLED`, `DISABLED_TEXT`, `TEXT`, `MUTED`, `FAINT`, `TILE`, `TILE_GLYPH`, `ERROR`, `FIELD`, `ON_TONAL` (תווית כפתור ה-Tonal) |

## איך משנים

הכול בבלוק הקבועים שבראש `build_assistant_art.py`:

- **צבע** — בלוק `palette`. הערכים נמדדו מערכת הנושא של האפליקציה (Material 3, זרע `#2C1B02`),
  כדי שהמסייע ייראה בדיוק כמו אוצריא. אם ערכת הנושא של האפליקציה משתנה — לעדכן כאן.
- **טקסט** — `TITLE` ו-`SUBTITLE` (נאפים לתוך `title_N_250.png`). עברית מסודרת ידנית מימין לשמאל
  (ל-Pillow אין raqm), ולכן מתאים לשורות בעברית בלבד. אחרי שינוי טקסט לבדוק בדף הנכסים שהוא
  נקרא נכון. `PREVIEW_NOTE` ו-`PREVIEW_BUTTON` משמשים רק לתצוגה המקדימה — הטקסטים האמיתיים
  במסייע נמצאים בקוד ה-Inno.
- **טקסט באנגלית** — `TITLE_EN` ו-`SUBTITLE_EN` (נאפים לתוך `title_en_N_250.png`), משמאל לימין,
  בגדלים `TITLE_EN_PX`/`SUBTITLE_EN_PX` (21/15: באותיות לטיניות הגודל של העברית נראה גדול מדי בכותרת
  וקטן מדי בשורת המשנה; ב-21 הכותרת ברוחב הכותרת העברית). ה-kerning נקרא מטבלת GPOS של הגופן
  בעזרת fontTools, כמו ש-Windows מציג את אותו טקסט (בלי raqm, Pillow לא מפעיל kerning).
  הקבוצה ממורכזת עד קו הבסיס של שורת המשנה — הזנב של `y` יורד מתחתיו. `PREVIEW_NOTE_EN`
  ו-`PREVIEW_BUTTON_EN` — לתצוגה המקדימה בלבד.
- **אנימציית הספר** — בלוק `book animation`: עובי כל חצי (`BLOCK`), עובי הכריכה (`BOARD`),
  עוצמת הפרספקטיבה (`CAMERA`, קטן יותר = חזק יותר), הנחיתה והקפיצה הקטנה בסוף (`LAND_FRAME`,
  `OVERSHOOT`), הנצנוץ בהתחלה (`GLINT_FRAMES`), תאורה, צללים וצבעי הזהב.
- **תזמונים ומיקומים של מסך הפתיחה** — בלוק `welcome sequence` (`BOOK_FPS`, `BOOK_TOP`, `BOOK_RISE`,
  `RISE_MS`, `TITLE_TOP`, `TITLE_FADE_MS`, `NOTE_TOP`, `BUTTON_TOP` ועוד). הם נכנסים ל-`.isi` (טבלה למעלה),
  והקוד ב-Inno קורא אותם משם. שינוי תזמון/מיקום משנה רק את ה-`.isi`, אבל מומלץ להריץ מחדש ולהסתכל בתצוגה המקדימה.
- **גודל נכס** — בבלוק `window and asset geometry`. שינוי גודל משנה את ה-define המתאים ב-`.isi`.
- **אייקון** — טבלת `ICONS`: סגנון, נקודת קוד וגודל העיצוב של אייקון מ-Fluent System Icons.
  את נקודות הקוד מוצאים ב-`lib/src/fluent_icons.dart` של החבילה `fluentui_system_icons`
  (לדוגמה `desktop_24_regular` ← `62298`). הסגנון `Otzaria` הוא גופן האייקונים של התוכנה
  (`otzaria_icons`, נקודות הקוד ב-`lib/src/generated/otzaria_icons_data.dart` שלו). אייקון של הצעה בעמוד "מה להוריד" נקרא `preset_<מזהה ההצעה>`,
  עם קו תחתון במקום מקף (`full-indexed` ← `preset_full_indexed`).

**שמות קבצים הם חוזה עם הקוד ב-Inno.** הוספת נכס בטוחה; שינוי שם או מחיקה ישברו את המסייע
בריפו הראשי, ומחייבים שינוי מתואם שם.

## פרסום גרסה חדשה לריפו הראשי

הריפו הראשי לא מריץ את הסקריפט: לפני הקומפילציה ב-ISCC הוא מוריד zip של הפלט בגרסה נעוצה.

1. מעלים את `ART_VERSION` בראש הסקריפט (למשל `1.0.0` ← `1.1.0`).
2. מפיקים לתיקייה נקייה ובודקים את התצוגה המקדימה:
   ```powershell
   Remove-Item -Recurse -Force out -ErrorAction SilentlyContinue
   py build_assistant_art.py --out out --preview
   ```
3. אורזים את `out\` ל-zip ומקבלים את ה-SHA-256. `pack_release.py` אורז קבצים שטוחים, ממוינים ובתאריך קבוע,
   כך שאותו פלט נותן תמיד אותו hash (`Compress-Archive` אינו כזה):
   ```powershell
   py pack_release.py            # כותב download-assistant-art-<גרסה>.zip ומדפיס גרסה, גודל ו-SHA-256
   ```
4. מבצעים commit, יוצרים תגית `download-assistant-art-v1.1.0` ו-Release בריפו הזה, ומצרפים את ה-zip.
5. בריפו הראשי מעדכנים את הנעיצה (גרסה + SHA-256) לפי ההוראות שם. `AA_ART_VERSION` שב-`.isi`
   מאפשר לוודא שה-zip שהורד הוא אכן הגרסה הנעוצה.

כל קובצי ה-PNG נשמרים כ-RGBA מלא (truecolor, ‏PNG colour type 6) — לעולם לא כ-PNG עם פלטה:
ה-VCL של Inno משאיר בקובץ פלטה רק שקיפות של כן/לא, וההילה והצל הרכים נהרסים. הסקריפט בודק
זאת על כל קובץ שהוא כותב. הגודל הכולל (כ-5.9MB, רובו פריימי הספר ב-250%) מודפס בסוף כל הרצה.
