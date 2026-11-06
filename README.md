# CM · 班級日常

CM 是一套班級經營 Web 應用，協助教師記錄學生表現、發放獎勵與傳達班級公告，讓學生用點數收藏個人角色、共同培養班級吉祥物。支援導師、共同教師與學生三種角色，可透過桌面或手機瀏覽器使用。

[線上使用](https://class-management-5v40.onrender.com) · [API 文件](API.md) · [部署指南](DEPLOYMENT.md) · [備份與還原](BACKUP.md)

## 主要功能

| 功能    | 說明                                    |
| ----- | ------------------------------------- |
| 班級管理  | 建立班級、貼上試算表名單、修正匯入錯誤、管理學生帳號與共同教師       |
| 行為記分  | 單筆或批次加扣分、原因模板、待補原因整理、紀錄修正與操作查核        |
| 獎勵點數  | 教師依自己的加分紀錄發放點數，學生可查看獲得與消費明細           |
| 個人角色  | 十二生肖與貓共十三種角色，支援購買、收藏及免費切換已擁有角色        |
| 班級吉祥物 | 貓、狗、兔、牛、馬、豬六種動物，透過全班餵食成長，呈現三階段外觀與農場動畫 |
| 公告與通知 | 富文字公告、置頂、教師留言、學生確認已讀、未讀名單與導師手動提醒      |
| 明細匯出  | 依日期與類型查詢分數／點數紀錄，下載權限範圍內的 CSV          |

### 角色與權限

- **導師**：管理自己的班級與學生、審核共同教師、查看工作首頁待辦、管理全班分數紀錄、發布公告及追蹤已讀情況。
- **共同教師**：經導師批准後參與班級記分，修改自己的紀錄、依自己的加分紀錄發點，並閱讀公告及撰寫留言。
- **學生**：查看自己的分數與點數、確認公告已讀、收藏角色、餵食班級吉祥物及匯出個人明細。

班級權限各自獨立；同一位教師可以在不同班級擔任不同角色。學生使用班級登入碼、學號與密碼登入，不需要 Email。

### 分數與點數如何運作

**分數**用來記錄行為表現，**點數**則是學生可花費的獎勵。教師記分後可另行發點；學生消費點數不影響分數，後續修正分數也不會追回已發出的點數。

學生可花 20 點購買一個未擁有的角色，或自願餵食班級吉祥物。餵食每點增加 1 點經驗值，每位學生每天最多餵食 5 點，以台北時間換日。

## 開始使用

1. **導師建立班級**：註冊教師帳號並驗證 Email，登入後建立班級。
2. **加入學生與共同教師**：從試算表複製「座號、姓名、學號」三欄貼入學生名單；需要協作時，分享教師申請碼並審核加入申請。
3. **學生首次登入**：分享班級的學生登入連結。學生以學號及初始密碼（學號）登入，依畫面要求設定新密碼。
4. **進行日常管理**：教師記分、發點及發布公告；學生查看紀錄、確認已讀，並使用獎勵點數。

公告需要學生主動按「確認已讀」；查看通知不等於確認公告。標題或內文更新後須重新確認，導師可對未讀學生發送站內提醒。

若要評估專案而不建立真實班級，可依下方步驟在本機建立展示資料。

## 本機啟動

以下以 **Windows PowerShell** 為例，需要 Git、Python 3.12 與 Node.js 22。專案提供本機 PostgreSQL 啟動工具，不需另裝資料庫服務。

### 安裝與啟動

```powershell
git clone https://github.com/CY-Marowak/ClassManagement.git
Set-Location ClassManagement
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
npm.cmd ci
npm.cmd --prefix frontend ci
npm.cmd run db:start
$env:CM_DEBUG='1'
.\.venv\Scripts\python.exe backend/manage.py migrate
node scripts/backend.mjs
```

另開終端機，在專案根目錄啟動前端：

```powershell
npm.cmd run dev
```

開啟 <http://127.0.0.1:5173>。前端由 Vite 提供，並將 `/api` 請求代理到 Django；使用時請保持相同主機名稱，避免混用 `localhost` 與 `127.0.0.1`。

本機資料庫使用 `127.0.0.1:55432`，資料保存在 `.local/postgres/`。結束使用時，在前後端終端機按 `Ctrl+C`，再執行 `npm.cmd run db:stop`；資料會保留。修改後端程式後需重新啟動後端。

更新程式後，啟動前執行 `backend/manage.py migrate` 套用最新資料庫結構。環境變數說明見 [.env.example](.env.example)；此檔僅供參考，程式不會自動載入 `.env`。

### 建立展示資料

資料庫啟動並完成 migration 後，在專案根目錄的另一個終端機執行：

```powershell
$env:CM_DEBUG='1'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe backend/manage.py create_demo
```

指令會建立獨立的假帳號與兩個班級，包含學生、記分、公告、留言與待辦，並輸出登入資訊。每次執行都會新增一套資料，不覆寫既有內容。

可使用輸出的 `teachers.homeroom` 登入導師帳號，另開無痕視窗，以 `student` 的登入資訊體驗學生流程。教師展示帳號已完成 Email 驗證，學生首次登入仍須改密碼。

建議先從導師工作首頁處理待辦，接著記分、發點，再切換學生查看餘額與餵食；也可用 `teachers.coTeacher` 和 `teachers.other` 比較共同教師權限與跨班資料隔離。

### 本機註冊與密碼復原

開發環境將郵件寫入 `.local/mail/`，不會寄出真實郵件。註冊後執行以下命令取得驗證連結，Email 請換成剛註冊的地址：

```powershell
.\.venv\Scripts\python.exe scripts/read-mail.py teacher@example.com verify
```

測試忘記密碼時，將 `verify` 改為 `reset`。正式寄信服務的設定見[部署指南](DEPLOYMENT.md)。

## 技術架構

| 層級       | 技術                                                                |
| ---------- | ------------------------------------------------------------------- |
| 前端       | React、TypeScript、Vite、Tiptap、SVG／CSS 動畫                      |
| 後端       | Python、Django、Django REST Framework                               |
| 資料庫     | PostgreSQL、Django ORM 與 migrations                                |
| 身分驗證   | Django Session Cookie、CSRF 防護、班級角色授權                      |
| 部署       | Docker、Gunicorn、WhiteNoise；Render 與 Neon 部署配置               |
| 測試與品質 | Django API 測試、Playwright／Edge、TypeScript、Ruff、mypy、Prettier |

正式部署由 Django 與 WhiteNoise 提供 API 及建置後的前端，使用同一個網域；資料儲存在 PostgreSQL。套件版本以 [requirements.lock](requirements.lock) 與各目錄的 npm lockfile 為準。

### 設計重點

- **資料一致性**：記分、點數發放、購買與餵食使用資料庫交易、班級鎖與約束，避免部分完成或併發造成餘額錯誤。
- **重試與衝突處理**：重要寫入操作以 UUID 識別重試，避免網路回應遺失後重複扣點或記分；版本檢查防止舊畫面覆蓋新資料。
- **權限隔離**：後端依目前班級成員資格授權；學生只能存取本人資料，密碼重設或身分撤銷後會重新檢查登入有效性。
- **紀錄可追溯**：分數修正保留操作歷史，點數交易與分數分開保存，公告已讀對應實際內容版本。
- **輸入與輸出防護**：富文字採支援格式白名單，CSV 匯出處理公式注入風險，登入與帳號復原設有請求限流。

### 原始碼導覽

| 路徑                               | 內容                                     |
| ---------------------------------- | ---------------------------------------- |
| [frontend/src/](frontend/src/)     | 使用者畫面、API client、角色與吉祥物呈現 |
| [backend/core/](backend/core/)     | 業務邏輯、資料模型、權限及 API 測試      |
| [backend/config/](backend/config/) | Django 路由與環境設定                    |
| [e2e/](e2e/)                       | 教師與學生的瀏覽器工作流測試             |
| [scripts/](scripts/)               | 本機啟動、郵件讀取及維運工具             |

API 入口、呼叫方式與實作對照見 [API.md](API.md)。

## 測試與驗證

測試涵蓋真實 PostgreSQL 上的 API 工作流，以及瀏覽器中的登入、記分、發點、角色購買、餵食與公告互動；另包含權限隔離、重試、併發、交易回滾及資料刪除情境。

完成本機安裝並啟動資料庫後，在專案根目錄執行：

```powershell
$env:CM_DEBUG='1'
.\.venv\Scripts\python.exe backend/manage.py test core --keepdb --noinput
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m mypy
npm.cmd run build
npm.cmd run test:e2e
```

API 測試預設使用獨立的 `test_cm` 資料庫；瀏覽器測試會在開發資料庫建立並保留假資料，預設使用已安裝的 Microsoft Edge。請使用本機測試環境，不要將測試指向正式資料庫。其他瀏覽器的設定可調整 [playwright.config.ts](playwright.config.ts)。

## 使用範圍與部署

- 通知在開啟或手動更新時載入；未讀提醒由導師手動發送，透過站內通知呈現。
- 學生可匯出本人紀錄，導師可匯出本班紀錄；共同教師沒有全班明細匯出權限。
- 永久刪除學生或班級會清除對應帳號與歷史，操作前需要確認；外部備份依備份保留規則處理。
- 目前未完成大規模負載驗證；擴大使用前需評估班級併發寫入、Session 撤銷及大量匯出的效能。

自行部署請參考 [DEPLOYMENT.md](DEPLOYMENT.md)，包含環境變數、HTTPS、資料庫與寄信設定；加密備份及還原程序見 [BACKUP.md](BACKUP.md)。
