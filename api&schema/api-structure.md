# מבנה API - פלטפורמת התאמת קו"ח אוטומטית למשרות

> **סטטוס:** MVP ראשוני
> **Base URL:** `/api/v1`
> **ארכיטקטורה:** שרת **API Server** אחד (endpoints מול המשתמש + נתוני חברות + endpoints פנימיים לסוכנים, ראו `apps/api`), **Dispatch Service** עתידי, ו-pipeline של 4 Agents (k8s CronJobs) המחוברים בתורות (queues).

---

## תרשים זרימה כללי

```
משתמש ←→ API Server ←→ Agents Pipeline
              ↑          (2→3→4→5, מחוברים ב-queues)
              │
    Dispatch Service (עתידי, טרם נבנה)
```

---

## 1. Endpoints מול המשתמש

### 1.1 Auth *(Mocked ל-MVP)*
> משתמש יחיד קבוע, ללא הרשמה/התחברות אמיתית בשלב זה. מקום שמור להרחבה עתידית (Session / JWT / ספק מנוהל כמו Auth0).

### 1.2 פרופיל והעדפות

| Method | Path | תיאור |
|---|---|---|
| GET | `/users/me` | פרטי המשתמש |
| PATCH | `/users/me` | עדכון פרטים |
| GET | `/users/me/preferences` | קבלת העדפות (כולל `match_threshold` - סף אחוז ההתאמה למשרה) |
| PUT | `/users/me/preferences` | עדכון העדפות |

### 1.3 שיחות עם Agent 1 (Profiling)

> Agent 1 מנהל שיחה אחת ארוכה עם המשתמש: מציג את עצמו → המשתמש מתאר את ההיסטוריה שלו → הסוכן מוודא פרטים כלליים (שפות תכנות, יכולות, השכלה) → תישאול פרויקט-פרויקט → יצירת building blocks תוך כדי השיחה (לא בסופה) → הצגה, ליטוש ואישור סופי.
>
> ניתן גם לפתוח שיחות נוספות בעתיד (להוספת ניסיון חדש), ושיחות ממוקדות לניסוח מחדש של block ספציפי (`type: refinement`).

| Method | Path | תיאור |
|---|---|---|
| POST | `/conversations` | פתיחת שיחה חדשה (כללית, או ממוקדת עם `type` + reference ל-block/הגשה) |
| GET | `/conversations` | רשימת כל השיחות של המשתמש |
| GET | `/conversations/:id` | שיחה ספציפית + היסטוריית הודעות + building blocks שנוצרו בה |
| POST | `/conversations/:id/messages` | שליחת הודעה → מחזיר תשובת סוכן (ללא streaming) + `building_blocks_created` + `building_blocks_updated` |
| POST | `/conversations/:id/finish` | סימון שהמשתמש סיים את השיחה (סטטוס בלבד, לא מפעיל יצירה) |

**דוגמת מבנה תגובה מ-`/conversations/:id/messages`:**
```json
{
  "agent_reply": "טקסט התשובה של הסוכן",
  "building_blocks_created": [ { "id": "...", "text": "..." } ],
  "building_blocks_updated": [ { "id": "...", "text": "..." } ]
}
```

### 1.4 Building Blocks

| Method | Path | תיאור |
|---|---|---|
| GET | `/building-blocks` | רשימת כל ה-blocks (ניתן לסנן לפי `conversation_id`) |
| GET | `/building-blocks/:id` | block ספציפי |
| PATCH | `/building-blocks/:id` | עריכה ישירה של הטקסט ע"י המשתמש |
| DELETE | `/building-blocks/:id` | מחיקה |
| POST | `/building-blocks/:id/regenerate` | פותח שיחה קצרה וממוקדת (`type: refinement`) לניסוח מחדש, דרך אותם endpoints של `/conversations` |

### 1.5 הגשות ממתינות לאישור (Applications)

> "הגשה" = קו"ח מותאם בלבד (ללא cover letter בשלב זה). המשתמש רואה מסמך מלא, יכול לערוך ישירות **וגם** לבקש ניסוח מחדש דרך הסוכן. לאחר אישור - עדיין לא ברור אם תהיה הגשה אוטומטית, ולכן הפעולה משאירה גמישות: כרגע רק מסמנת סטטוס.

| Method | Path | תיאור |
|---|---|---|
| GET | `/applications` | רשימת הגשות (סינון לפי `status`: `pending_tailoring` / `pending_approval` / `approved` / `rejected`) |
| GET | `/applications/:id` | פרטי הגשה + תוכן הקו"ח המותאם |
| PATCH | `/applications/:id/document` | עריכה ישירה של טקסט הקו"ח |
| POST | `/applications/:id/regenerate` | שיחה ממוקדת עם הסוכן (`type: application_edit`) לניסוח מחדש |
| POST | `/applications/:id/approve` | סימון כמאושר *(הפעולה בפועל אחרי אישור - הגשה אוטומטית או ידנית - טרם הוחלטה)* |
| POST | `/applications/:id/reject` | דחיית ההתאמה |
| GET | `/applications/:id/download` | הורדת הקו"ח כקובץ (PDF/Word) - נדרש במיוחד אם לא יהיה auto-dispatch |

### 1.6 Endpoints פנימיים (Agent-facing בלבד)

> לא נחשפים למשתמש הקצה - משמשים את ה-Agents לתקשורת עם ה-API Server.

| Method | Path | קורא | תיאור |
|---|---|---|---|
| POST | `/internal/applications` | Agent 4 (Evaluation) | יצירת Application חדש כשההתאמה עוברת את `match_threshold` של המשתמש (status: `pending_tailoring`) |
| PATCH | `/internal/applications/:id` | Agent 5 (Tailoring) | עדכון עם הקו"ח המותאם שנוצר (status → `pending_approval`) |

---

## 2. Endpoints של נתוני חברות

> מוגש ע"י אותו **API Server** כמו בסעיף 1. שליחה בפועל נשארת מכוונת בנפרד (ה-**Dispatch Service** העתידי, סעיף 2.4) כדי שתעבורת כתיבה של agents ותעבורת dispatch עתידית לא יבצרו זו את זו.

### 2.1 כתיבה (ע"י Agents 2-4, דרך HTTP פנימי)

| Method | Path | Agent | תיאור |
|---|---|---|---|
| POST | `/companies` | Agent 2 (Discovery) | יצירת/עדכון חברה שנמצאה |
| PATCH | `/companies/:id` | Agent 2 | עדכון פרטי חברה |
| POST | `/jobs` | Agent 3 (Extractor) | יצירת משרה שחולצה (מקבלת `id` עוקב אוטומטית) |
| PATCH | `/jobs/:id` | Agent 3 | עדכון פרטי משרה |

> **הערה:** `companies.id` ו-`jobs.id` הם מספרים עוקבים (BIGINT), לא UUID - זה מה שמאפשר את מנגנון הסריקה בסעיף 2.3 למטה. שאר הטבלאות במערכת (users, applications וכו') נשארות UUID.

### 2.2 קריאה (ע"י Frontend, ישירות)

| Method | Path | תיאור |
|---|---|---|
| GET | `/jobs` | רשימת משרות (חיפוש/סינון) |
| GET | `/jobs/:id` | פרטי משרה ספציפית - נקרא ע"י Frontend יחד עם פרטי ה-Application (שתי קריאות נפרדות, לא אחת דרך השנייה) |
| GET | `/companies/:id` | פרטי חברה |

### 2.3 מנגנון סריקת התאמות (Agent 4) - ללא endpoint, ללא טבלת matches

Agent 4 **לא** כותב רשומת התאמה לכל בדיקה. במקום זה, לכל משתמש יש "סמן" (`last_checked_job_id`) שמציין עד איזו משרה (לפי מספר עוקב) הוא כבר נסרק. בכל ריצה:

1. Agent 4 שולף את `last_checked_job_id` הנוכחי של המשתמש.
2. סורק את `jobs` בסדר עולה, החל מהמספר הבא, ומחשב התאמה מול כל משרה.
3. אם הציון ≥ `match_threshold` → קורא ל-API Server (`POST /internal/applications`).
4. מעדכן את `last_checked_job_id` למספר המשרה האחרונה שנבדקה.

**איפוס הסמן:** כש-`user_preferences` או `building_blocks` של המשתמש משתנים, ה-API Server מאפס את `last_checked_job_id` בחזרה ל-0, כדי שהמשרות הישנות (שאולי נפסלו בעבר) ייבדקו מחדש מול הקריטריונים החדשים.

> **הערה:** פירוט הדרישות/עמידה שמרכיב את הציון עדיין נשמר בלוגי ריצת Agent 4 בלבד (`GET /agents/evaluation/runs/:run_id/logs`), לא ב-DB.

### 2.4 Dispatch Service *(שלד להרחבה עתידית)*

עדיין לא קיים כשירות HTTP. כש-`POST /applications/:id/approve` נקרא ב-API Server, מתפרסם אירוע לתור `application-approved-queue`. כש-Dispatch Service ייבנה, הוא רק יאזין לתור הזה - בלי לשנות דבר ב-API Server.

### 2.5 ניטור פנימי (Agents 2-5)

| Method | Path | תיאור |
|---|---|---|
| GET | `/agents/status` | סטטוס כל ה-agents (ריצה אחרונה, הצלחה/כישלון, גודל תור נוכחי) |
| GET | `/agents/:name/status` | סטטוס agent ספציפי |
| GET | `/agents/:name/runs` | היסטוריית ריצות (timestamps + סטטוס) |
| GET | `/agents/:name/runs/:run_id/logs` | לוגים מריצה ספציפית - לתחקור לוגיקה |

### 2.6 תורות פנימיים (Message Queue, לא REST)

| שם התור | מפרסם (Producer) | צורך (Consumer) |
|---|---|---|
| `company-discovery-queue` | Agent 2 (Discovery) | Agent 3 (Extractor) |
| `job-extraction-queue` | Agent 3 (Extractor) | Agent 4 (Evaluation) |
| `evaluation-queue` | Agent 4 (Evaluation) | Agent 5 (Tailoring) |
| `application-approved-queue` | API Server (בעת approve) | *(עתידי)* Dispatch Service |

---

## 3. זרימת יצירת Application - סיכום מלא

1. **Agent 2 (Discovery)** מוצא חברות רלוונטיות → כותב ל-API Server, מפרסם ל-`company-discovery-queue`.
2. **Agent 3 (Extractor)** שואב משרות מהחברות → כותב ל-API Server, מפרסם ל-`job-extraction-queue`.
3. **Agent 4 (Evaluation)** סורק משרות לפי הסמן (`last_checked_job_id`) של המשתמש, בסדר עולה, ומחשב ציון התאמה לכל אחת:
   - **אם הציון ≥ `match_threshold`** שהמשתמש הגדיר → קורא ל-API Server (`POST /internal/applications`) ליצירת Application חדש (status: `pending_tailoring`), ומפרסם ל-`evaluation-queue`.
   - בכל מקרה (גם אם לא עבר את הסף) - מעדכן את `last_checked_job_id` למשרה הנוכחית, כדי שהריצה הבאה תמשיך משם.
   - פירוט מלא של הדרישות/עמידה נשמר בלוגי הריצה, לא ב-DB.
4. **Agent 5 (Tailoring)** לוקח משימות מ-`evaluation-queue`, מייצר קו"ח מותאם, ומעדכן את ה-Application (`PATCH /internal/applications/:id`, status → `pending_approval`).
5. **המשתמש** רואה את ההגשה ב-`GET /applications`, עורך/מנסח מחדש לפי הצורך, ומאשר (`POST /applications/:id/approve`).
6. אירוע `application.approved` מתפרסם ל-`application-approved-queue`. **Dispatch Service עתידי** יאזין לתור הזה כשייבנה. בינתיים - המשתמש מוריד את הקו"ח (`GET /applications/:id/download`) ומגיש בעצמו.

---

## נקודות פתוחות לדיון עתידי

1. **Authentication אמיתי** - טרם נבחר (Session / JWT / ספק מנוהל). המבנה הנוכחי מניח משתמש יחיד קבוע.
2. **Dispatch אוטומטי** - טרם הוחלט אם ייבנה בכלל; אם כן, יש לתכנן human-in-the-loop נוסף, טיפול ב-ToS של אתרי משרות, ו-CAPTCHA/bot detection.
3. **Legality של scraping** - יש לוודא מבחינה משפטית שהשאיבה ממקורות המשרות החיצוניים מותרת.
4. **סקאלת API Server** - כרגע שירות יחיד שמטפל גם ב-endpoints מול המשתמש וגם בנתוני חברות; אם התעבורה תגדל (למשל כתיבות סוכנים שמבצרות קריאות מול המשתמש), כדאי לשקול הפרדה חזרה לשירותים נפרדים (הם כבר מדברים REST ביניהם על אותם נתונים, כך שזה שינוי פריסה (deployment) ולא כתיבה מחדש).
