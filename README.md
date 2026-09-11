# CM · 班級日常

任務 01：教師註冊、Email 驗證、登入／登出、忘記密碼、建立與編輯自己的班級。

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

- 本次只完成任務 01，學生帳號、共同教師加入、記分與餵食依後續任務完成。
- 登入依帳號每 15 分鐘 5 次，註冊／復原／重寄各每帳號 3 次；每類操作另有 IP 30 次上限。計數保存在 PostgreSQL 並以鎖保護，多個後端程序共用限制。正式反向代理需規劃可信來源 IP；程式不直接相信外部傳入的 X-Forwarded-For。
- 密碼至少 10 字元，框架拒絕常見、純數字及過度相似密碼。開發與正式環境均使用 Django 密碼雜湊。
- 驗證與重設 token 只儲存雜湊；信件連結放在 URL fragment，避免送到 HTTP access log。
- 欄位輸入邊界：班級名稱最多 80 字，入學年度 1900–2100，目前年級 1–12；這些為本次介面邊界，可依實際學制調整。
- 上線設定由環境變數提供，見 `.env.example`；檔案只供參考，Django 不會自動讀取它。

領域與決策來源：上層 `instructions.md`、`Implementation-decisions.md`、`CONTEXT.md`、`planning/cm-v1/spec.md` 與 `planning/cm-v1/issues/01-teacher-login-class.md`。
