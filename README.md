# CM · 班級日常

任務 01：教師註冊、Email 驗證、登入／登出、忘記密碼、建立與編輯自己的班級。

追加任務 01a：導師永久刪除自己的班級。

前端 React／TypeScript／Vite，後端 Django／DRF，資料庫 PostgreSQL。此資料夾為獨立 Git repo，遠端為 [CY-Marowak/ClassManagement](https://github.com/CY-Marowak/ClassManagement)。Brain 不備份這裡的程式碼；請在 app 資料夾提交後執行 `git push`，將產品提交推送至 GitHub。

## 第一次啟動（Windows PowerShell）

在本資料夾開啟終端機。需要 Python 3.12 與 Node.js 22.22 或相容版本。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
npm.cmd ci
Set-Location frontend
npm.cmd ci
Set-Location ..
npm.cmd run db:start
$env:CM_DEBUG='1'
.\.venv\Scripts\python.exe backend/manage.py migrate
node scripts/backend.mjs
```

另開一個終端機，在 app 資料夾執行：

```powershell
npm.cmd run dev
```

開啟 <http://127.0.0.1:5173>。保持使用同一個主機名稱，不要混用 localhost 與 127.0.0.1。

本機 PostgreSQL 監聽 `127.0.0.1:55432`，資料庫 cm，開發帳號 cm／cm-local-only。這組設定僅供本機開發，資料保存在 `.local/postgres/`。不會安裝系統服務，也不會自動刪除資料。停止資料庫：`npm.cmd run db:stop`。

## 如何試用註冊及忘記密碼

開發環境不寄真實郵件。提交註冊後，開啟 `.local/mail/` 最新的 `.log` 信件；由於 MIME 編碼，可用以下命令取得連結：

```powershell
.\.venv\Scripts\python.exe scripts/read-mail.py teacher@example.com verify
```

將 Email 換成你剛註冊的地址；忘記密碼時把 `verify` 換成 `reset`。開啟連結後，按畫面按鈕確認。連結 30 分鐘內有效、只能使用一次；重新寄送會讓舊連結失效。

Email 不需要真實存在就能本機試用。正式上線前必須配置 SMTP、寄件地址、HTTPS、秘密金鑰與正式資料庫。不要把 `.local`、`.env` 或 `.venv` 提交到 Git。

## 如何永久刪除班級

在「我的班級」選擇該班的「編輯班級」，於危險操作區點選「永久刪除班級」。閱讀刪除範圍與無法復原提示，輸入完整且相同的班級名稱後，才可按「確認永久刪除」；取消不改變資料。

僅該班導師可操作。班級、教師成員關係、學生檔案、專屬登入帳號、建立事件與學生 Session 會從 PostgreSQL 真正刪除，教師帳號與其他班級保留。分數、點數、公告及吉祥物後續加入時必須同步支援刪除。此操作不提供復原，也不會清除外部資料庫備份。

## 建立學生與首次登入

導師在班級卡片選「學生名單」，從試算表複製座號、姓名、學號三欄並貼上。每次最多 200 筆，顯示新增／略過／待修正與原始行號；修正錯誤後可再貼一次。完全相同資料略過，衝突不覆寫；學號保留前導零，既有資料可使用名單內的「修改資料」。

複製頁面上的學生登入連結分享給該班，連結預填固定班級登入碼。學生以學號及初始密碼（學號）登入，首次必須設定至少 10 字元、非常見／純數字／過度相似的密碼，才可查看自己的班級、姓名、座號及角色。教師 Email 登入與學生登入分開。

角色為建立時隨機固定的貓、狗、兔，同班可以重複，不可更換。`frontend/src/AnimalAvatar.tsx` 使用原創基本幾何 SVG；Lucide 只作簡單造型程度參考，沒有複製外部路徑或引入圖庫。學生角色與後續班級吉祥物不同。

## 修正學生資料、重設密碼與操作紀錄

在「學生名單」找到學生，選「修改資料」可更新姓名、座號與學號。同班座號或學號重複時，整次修改拒絕。改學號後使用新學號登入，密碼不會跟著改變；尚未首次改密碼者也保留原初始密碼，可另用重設功能協助。學生 ID、固定角色與既有紀錄保留。

「重設密碼」會先顯示學生與影響，按「確認重設密碼」後，密碼重設為目前學號，所有原登入失效，重新登入必須改密碼。

「操作紀錄」僅該班已批准導師可查看，含建立學生、修改資料與重設密碼，按新到舊每頁 25 筆；顯示當時操作者／學生姓名、時間與修改欄位前後差異。重設只記事件，不保存密碼或雜湊。沒有資料變更時不新增紀錄。

修改／重設與紀錄在同一交易完成；查核寫入失敗時操作回滾。永久刪班會清除該班所有學生查核紀錄，其他班級保留。更新既有環境時，啟動前執行 `backend/manage.py migrate`（同上設定 `CM_DEBUG=1`）；0006 將既有建立事件延伸為查核事件並保留原 ID、操作者及時間。

## 驗證

```powershell
$env:CM_DEBUG='1'
.\.venv\Scripts\python.exe backend/manage.py test core --keepdb --noinput
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m mypy
npm.cmd run build
npm.cmd run test:e2e
```

API 測試使用獨立的 `test_cm` PostgreSQL 資料庫。瀏覽器測試使用本機開發資料庫與每次唯一的假 Email，會保留測試資料；不要對正式資料庫執行測試。預設使用已安裝的 Microsoft Edge（headless）；其他平台可調整 playwright.config.ts 的 channel 或安裝 Playwright Chromium。

瀏覽器截圖保存在 `.local/classroom-desktop.png` 與 `.local/classroom-mobile.png`。每次測試使用獨立輸出資料夾，不批量刪除舊結果。

## 從一次請求理解 Django

以建立班級為例：

1. `frontend/src/Classroom.tsx` 收集班級名稱、入學年度與目前年級。
2. `frontend/src/api.ts` 取得 CSRF token，使用登入 Cookie 送出 `POST /api/classes/`。
3. `backend/config/urls.py` 將網址交給 `core/cohorts.py` 的 View。
4. View 確認教師已驗證 Email；Serializer 驗證輸入。
5. Django ORM 在同一個資料庫交易內建立班級與導師 membership。
6. 回傳班級資料，React 更新列表。

`Model` 定義資料及約束；`Migration` 將模型變更套用到資料庫；`Serializer` 驗證 API 輸入及整理輸出；`View` 協調一次操作；`Session` 保存登入狀態。導師是班級角色，不是 Django 超級使用者。

## 範圍與實作選擇

- 已實作任務 01、01a、02、03；共同教師加入、記分與餵食依後續任務完成。
- 學生登入按班級碼＋學號每 15 分鐘 5 次、IP 每 15 分鐘 30 次限流。改密碼保留目前 Session，舊密碼 Session 失效。
- 名單匯入、學生資料修改、登入／改密碼／導師重設與刪班共用班級交易鎖；查核事件與資料修改一起保存。重設與刪班目前逐筆解碼 Session 找出目標帳號，成本隨 Session 數量增加；大量使用前應加入可索引的帳號 Session 關聯。
- 登入依帳號每 15 分鐘 5 次，註冊／復原／重寄各每帳號 3 次；每類操作另有 IP 30 次上限。計數保存在 PostgreSQL 並以鎖保護，多個後端程序共用限制。正式反向代理需規劃可信來源 IP；程式不直接相信外部傳入的 X-Forwarded-For。
- 密碼至少 10 字元，框架拒絕常見、純數字及過度相似密碼。開發與正式環境均使用 Django 密碼雜湊。
- 驗證與重設 token 只儲存雜湊；信件連結放在 URL fragment，避免送到 HTTP access log。
- 欄位輸入邊界：班級名稱最多 80 字，入學年度 1900–2100，目前年級 1–12；這些為本次介面邊界，可依實際學制調整。
- 上線設定由環境變數提供，見 `.env.example`；檔案只供參考，Django 不會自動讀取它。

領域與決策來源：上層 `instructions.md`、`Implementation-decisions.md`、`CONTEXT.md`、`planning/cm-v1/spec.md` 與 `planning/cm-v1/issues/01-teacher-login-class.md`。
