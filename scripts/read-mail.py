"""Read a development email link for browser tests. Never used by application routes."""
import email
import re
import sys
from pathlib import Path

mail_dir = Path(__file__).resolve().parent.parent / ".local" / "mail"
for path in sorted(mail_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
    message = email.message_from_bytes(path.read_bytes())
    if sys.argv[1] not in str(message["To"]):
        continue
    payload = message.get_payload(decode=True)
    body = payload.decode(message.get_content_charset() or "utf-8")
    link = re.search(r"http://127\.0\.0\.1:5173/#" + sys.argv[2] + r"\?token=[\w-]+", body)
    if link:
        print(link[0])
        break
else:
    raise SystemExit("Development email not found")
