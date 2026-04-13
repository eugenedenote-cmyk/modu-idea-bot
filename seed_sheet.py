"""기존 seen_ideas.json 데이터를 Google Sheets에 일괄 입력 (1회용)"""

import json
import os
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

BASE_DIR = Path(__file__).parent
SEEN_PATH = BASE_DIR / "seen_ideas.json"
GSHEET_CRED_PATH = BASE_DIR / "gsheet_credentials.json"
SPREADSHEET_ID = "1Jx2XTi-AuqBsZRuQ2occSxindxuOSVU0lmaL7LDhBb4"

scopes = ["https://www.googleapis.com/auth/spreadsheets"]

# 인증
cred_json = os.environ.get("GSHEET_CREDENTIALS")
if cred_json:
    cred_data = json.loads(cred_json)
    creds = Credentials.from_service_account_info(cred_data, scopes=scopes)
elif GSHEET_CRED_PATH.exists():
    creds = Credentials.from_service_account_file(str(GSHEET_CRED_PATH), scopes=scopes)
else:
    raise RuntimeError("Google Sheets 인증 정보 없음")

client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)
ws = spreadsheet.sheet1

# 헤더 추가
header = ["접수자", "아이디어 요약", "분야", "단계", "접수일", "상태", "감지 시각"]
ws.clear()
ws.append_row(header)

# seen_ideas.json 읽기
seen = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
now = datetime.now().strftime("%Y-%m-%d %H:%M")

rows = []
for idea in seen:
    rows.append([
        idea.get("name", ""),
        idea.get("summary", ""),
        idea.get("field", ""),
        idea.get("stage", ""),
        idea.get("date", ""),
        "등록",
        now,
    ])

if rows:
    ws.append_rows(rows)

print(f"완료! {len(rows)}건을 Google Sheets에 입력했습니다.")
