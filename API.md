# CM API 路由索引

核對日期：2026-11-06；基準為本機 `0eb2024`。依 `backend/config/urls.py` 與 View 實際方法整理，省略框架 HEAD／OPTIONS。這是路由索引，不是完整 OpenAPI schema；欄位、回應與邊界請沿連結閱讀 Serializer／View 與相應測試。

## 呼叫契約

- 使用同源 Django Session Cookie，先 GET `/api/csrf/`，寫入請求帶 `X-CSRFToken`；公開登入等寫入也檢查CSRF。不是Bearer JWT。
- 教師以Email／密碼登入；學生以class_code、student_number、password登入，首次須改密碼。導師是班級membership，不是全域管理員。
- classes路徑仍核對該班membership；學生路徑由Session推導本人。知道ID不代表有權限。
- 記分、購買等各有UUID及內容匹配契約；重試沿用原識別與內容，不是所有POST都有通用去重機制。
- 400通常為輸入／業務拒絕，403為權限／登入／CSRF，404為不存在或不在可見範圍；部分版本衝突用409，限流429，寄信失敗503。各View為準。
- 部分修改採命令型POST，班級／學生資料另用PATCH／DELETE；稱為HTTP JSON API，不宣稱完全一致的REST CRUD設計。

## 代表請求

| 操作 | 請求 | 語意 |
| --- | --- | --- |
| 購買角色 | POST `/api/student/roles/purchases/`，`{"role":"cat","request_id":"<UUID>"}` | 後端定價20點；初次201、同操作重試200；扣款／交易／持有同一交易 |
| 換角 | POST `/api/student/roles/`，`{"role":"cat"}` | 只接受本人已持有角色，不扣點 |
| 公告確認 | POST `/api/student/announcements/<id>/read/`，`{"content_version":2}` | 舊版本409；查看通知不代替確認 |
| 點數明細 | GET `/api/student/history/points/?start=2026-11-01&end=2026-11-06&kind=purchase` | 路徑kind為scores／points；query kind為award／feed／purchase且僅點數可用 |
| CSV | GET `/api/classes/<pk>/history/scores/export/?student_id=1` | 本班導師限定；學生路由僅本人；台北日期篩選 |
| 通知全部已查看 | POST `/api/notifications/viewed/`，`{"through_id":123}` | 保留載入上界之後的新通知未查看 |
| 未讀提醒 | POST `/api/classes/<pk>/announcements/<id>/reminders/`，`{"request_id":"<UUID>","content_version":2}` | 僅導師；可加student_id單獨提醒。同公告／學生／台北日期最多一次，改版不重置 |

## 全部註冊路由

共56條URL pattern；方法由View與繼承關係核對。用途可由上方模組與實作名稱定位。

| 方法 | 路徑 | 實作 |
| --- | --- | --- |
| `GET` | `/api/notifications/` | [NotificationsView](backend/core/notifications.py) |
| `POST` | `/api/notifications/viewed/` | [ViewAllNotificationsView](backend/core/notifications.py) |
| `POST` | `/api/notifications/<int:notification_id>/open/` | [OpenNotificationView](backend/core/notifications.py) |
| `GET/POST` | `/api/classes/<int:pk>/announcements/<int:announcement_id>/reminders/` | [AnnouncementRemindersView](backend/core/reminders.py) |
| `POST` | `/api/student/announcements/<int:announcement_id>/read/` | [StudentAnnouncementReadView](backend/core/announcements.py) |
| `GET` | `/api/classes/<int:pk>/announcements/<int:announcement_id>/read-receipts/` | [AnnouncementReceiptsView](backend/core/announcements.py) |
| `GET` | `/api/student/history/<str:kind>/` | [HistoryView](backend/core/history.py) |
| `GET` | `/api/student/history/<str:kind>/export/` | [HistoryView](backend/core/history.py) |
| `GET` | `/api/classes/<int:pk>/history/<str:kind>/` | [HistoryView](backend/core/history.py) |
| `GET` | `/api/classes/<int:pk>/history/<str:kind>/export/` | [HistoryView](backend/core/history.py) |
| `GET/POST` | `/api/student/roles/` | [StudentRolesView](backend/core/role_collection.py) |
| `POST` | `/api/student/roles/purchases/` | [StudentRolePurchasesView](backend/core/role_collection.py) |
| `GET` | `/healthz` | [health](backend/config/deployment.py) |
| `GET` | `/api/classes/<int:pk>/import-issues/` | [ImportIssuesView](backend/core/import_issues.py) |
| `POST` | `/api/classes/<int:pk>/import-issues/<int:issue_id>/` | [ResolveImportIssueView](backend/core/import_issues.py) |
| `GET` | `/api/classes/<int:pk>/dashboard/` | [DashboardView](backend/core/dashboard.py) |
| `POST` | `/api/classes/<int:pk>/announcements/<int:announcement_id>/comments/<int:comment_id>/` | [CommentChangeView](backend/core/comments.py) |
| `GET/POST` | `/api/classes/<int:pk>/announcements/<int:announcement_id>/comments/` | [CommentsView](backend/core/comments.py) |
| `GET` | `/api/student/announcements/<int:announcement_id>/comments/` | [StudentCommentsView](backend/core/comments.py) |
| `GET/POST` | `/api/classes/<int:pk>/announcements/` | [AnnouncementsView](backend/core/announcements.py) |
| `POST` | `/api/classes/<int:pk>/announcements/<int:announcement_id>/` | [AnnouncementChangeView](backend/core/announcements.py) |
| `GET` | `/api/student/announcements/` | [StudentAnnouncementsView](backend/core/announcements.py) |
| `GET/POST` | `/api/student/mascot/` | [StudentMascotView](backend/core/mascots.py) |
| `GET` | `/api/classes/<int:pk>/mascot/` | [ClassMascotView](backend/core/mascots.py) |
| `GET/POST` | `/api/classes/<int:pk>/point-awards/` | [PointAwardsView](backend/core/awards.py) |
| `GET` | `/api/classes/<int:pk>/scores/<int:record_id>/edit-preview/` | [ScoreEditPreviewView](backend/core/score_changes.py) |
| `POST` | `/api/classes/<int:pk>/score-changes/` | [ScoreChangesView](backend/core/score_changes.py) |
| `GET/POST` | `/api/classes/<int:pk>/pending-reasons/` | [PendingReasonsView](backend/core/batch_scores.py) |
| `POST` | `/api/classes/<int:pk>/score-batches/` | [ScoreBatchesView](backend/core/batch_scores.py) |
| `GET` | `/api/classes/<int:pk>/score-roster/` | [ScoreRosterView](backend/core/scores.py) |
| `GET/POST` | `/api/classes/<int:pk>/scores/` | [ScoresView](backend/core/scores.py) |
| `GET` | `/api/classes/<int:pk>/score-events/` | [ScoreEventsView](backend/core/scores.py) |
| `GET` | `/api/student/scores/` | [StudentScoresView](backend/core/scores.py) |
| `GET/POST` | `/api/teacher-applications/` | [TeacherApplicationsView](backend/core/memberships.py) |
| `GET` | `/api/classes/<int:pk>/teachers/` | [TeachersView](backend/core/memberships.py) |
| `POST` | `/api/classes/<int:pk>/teachers/<int:member_id>/` | [TeacherDecisionView](backend/core/memberships.py) |
| `GET` | `/api/classes/<int:pk>/teacher-events/` | [TeacherEventsView](backend/core/memberships.py) |
| `POST` | `/api/classes/<int:pk>/teacher-code/` | [TeacherCodeView](backend/core/memberships.py) |
| `GET/POST` | `/api/classes/` | [ClassesView](backend/core/cohorts.py) |
| `DELETE/GET/PATCH` | `/api/classes/<int:pk>/` | [ClassDetailView](backend/core/cohorts.py) |
| `GET/POST` | `/api/classes/<int:pk>/students/` | [StudentsView](backend/core/students.py) |
| `DELETE/PATCH` | `/api/classes/<int:pk>/students/<int:student_id>/` | [StudentDetailView](backend/core/student_management.py) |
| `POST` | `/api/classes/<int:pk>/students/<int:student_id>/reset-password/` | [ResetStudentPasswordView](backend/core/student_management.py) |
| `GET` | `/api/classes/<int:pk>/student-events/` | [StudentEventsView](backend/core/student_management.py) |
| `POST` | `/api/student/login/` | [StudentLoginView](backend/core/students.py) |
| `POST` | `/api/student/change-password/` | [StudentPasswordView](backend/core/students.py) |
| `GET` | `/api/student/me/` | [StudentMeView](backend/core/students.py) |
| `GET` | `/api/csrf/` | [csrf](backend/core/views.py) |
| `POST` | `/api/auth/register/` | [RegisterView](backend/core/views.py) |
| `POST` | `/api/auth/verify/` | [VerifyView](backend/core/views.py) |
| `POST` | `/api/auth/login/` | [LoginView](backend/core/views.py) |
| `GET` | `/api/auth/me/` | [MeView](backend/core/views.py) |
| `POST` | `/api/auth/logout/` | [LogoutView](backend/core/views.py) |
| `POST` | `/api/auth/forgot-password/` | [RequestEmailView](backend/core/views.py) |
| `POST` | `/api/auth/resend-verification/` | [ResendVerificationView](backend/core/views.py) |
| `POST` | `/api/auth/reset-password/` | [ResetView](backend/core/views.py) |

## 外部服務

CM後端包含Brevo `POST https://api.brevo.com/v3/smtp/email` 與Resend `POST https://api.resend.com/emails` 郵件adapter。Neon透過PostgreSQL協定由ORM存取，不是前端REST API。R2備份走S3相容介面；備份工作流不是使用者產品API。供應商金鑰只放私密環境設定。
