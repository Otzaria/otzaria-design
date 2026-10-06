# מקורות ורישיונות

| קובץ | מקור | רישיון |
|---|---|---|
| `FluentSystemIcons-Regular.ttf`, `FluentSystemIcons-Filled.ttf` | Fluent UI System Icons של Microsoft, מהחבילה `fluentui_system_icons` 1.1.273 (`lib/fonts/`) | MIT, Copyright (c) Microsoft Corporation |
| `otzaria_icons.otf` | גופן האייקונים של אוצריא, מהחבילה `otzaria_icons` (`github.com/Otzaria/otzaria_icons`, ref `5a614a7046c17e4321af31066cd9f0feae7c2e47` כפי שנעוץ ב-`pubspec.yaml` של אוצריא, `lib/fonts/`). חלק מהאייקונים בו נגזרים מ-Fluent UI System Icons — פירוט ב-`THIRD_PARTY_NOTICES.md` של החבילה | GPL-3.0-only (החלקים הנגזרים: MIT AND GPL-3.0-only); טקסט הרישיון ב-`otzaria_icons.LICENSE` |
| `iconnew.png` | לוגו אוצריא, `assets/icon/iconnew.png` בריפו של אוצריא | שייך לפרויקט אוצריא; חל עליו הרישיון של הריפו הראשי, לא MIT |

## לא נכלל בריפו

**Segoe UI** (`segoeui.ttf`, `seguisb.ttf`) הוא גופן של Microsoft שאסור להפיץ. הסקריפט קורא אותו
מ-`%WINDIR%\Fonts` בזמן ההרצה, ולכן הוא לא נשמר כאן ואסור להוסיף אותו. הגרפיקה המופקת (PNG)
מכילה טקסט שרונדר ממנו, ועל כן אינה כוללת את קובץ הגופן עצמו.

לרענון הקבצים: `py build_assistant_art.py --collect-sources`.

## טקסט הרישיון של Fluent UI System Icons

```
Fluent UI System Icons
Copyright (c) Microsoft Corporation.

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.```
