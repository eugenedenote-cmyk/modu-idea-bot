"""기존 아이디어 데이터를 Google Sheets에 일괄 입력 + 상세정보 탭 생성 (1회용)"""

import json
import os
from datetime import datetime
from pathlib import Path

import requests
import gspread
from google.oauth2.service_account import Credentials

BASE_DIR = Path(__file__).parent
SEEN_PATH = BASE_DIR / "seen_ideas.json"
GSHEET_CRED_PATH = BASE_DIR / "gsheet_credentials.json"
SPREADSHEET_ID = "1Jx2XTi-AuqBsZRuQ2occSxindxuOSVU0lmaL7LDhBb4"
ENV_PATH = BASE_DIR / ".env"

API_BASE = "https://poseidon-prod.modoo.or.kr"
REFRESH_URL = f"{API_BASE}/api/v1/token/refresh"
IDEAS_URL = f"{API_BASE}/api/v2/organization-manager/startup-ideas"
IDEA_DETAIL_URL = f"{API_BASE}/api/v1/organization-manager/startup-ideas"

REGION_MAP = {
    "SEOUL": "서울", "BUSAN": "부산", "DAEGU": "대구", "INCHEON": "인천",
    "GWANGJU": "광주", "DAEJEON": "대전", "ULSAN": "울산", "SEJONG": "세종",
    "GYEONGGI": "경기", "GANGWON": "강원", "CHUNGBUK": "충북", "CHUNGNAM": "충남",
    "JEONBUK": "전북", "JEONNAM": "전남", "GYEONGBUK": "경북", "GYEONGNAM": "경남",
    "JEJU": "제주",
}
DIVISION_MAP = {"TECH": "기술", "REGION": "지역", "REGION_INVEST": "지역투자"}
STAGE_MAP = {"FIRST": "1차", "SECOND": "2차"}

# ── 인증 ────────────────────────────────────────────────

scopes = ["https://www.googleapis.com/auth/spreadsheets"]
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


# ── 모두의창업 토큰 갱신 ────────────────────────────────

def get_refresh_token():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return os.environ.get("REFRESH_TOKEN") or env.get("REFRESH_TOKEN", "")


def refresh_tokens(refresh_token):
    resp = requests.post(REFRESH_URL, json={"refreshToken": refresh_token}, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("data")
    return None


# ── 메인 ────────────────────────────────────────────────

print("1. 모두의창업 토큰 갱신 중...")
tokens = refresh_tokens(get_refresh_token())
if not tokens:
    raise RuntimeError("토큰 갱신 실패")
access_token = tokens["accessToken"]
print("   토큰 갱신 완료")

print("2. 아이디어 목록 조회 중...")
headers = {"poseidon-token": access_token}
resp = requests.get(IDEAS_URL, headers=headers, params={"organizationIds[]": 75, "page": 0, "size": 100}, timeout=10)
items = resp.json().get("data", [])
if isinstance(items, dict):
    items = items.get("content") or items.get("items") or []
print(f"   {len(items)}건 조회 완료")

now = datetime.now().strftime("%Y-%m-%d %H:%M")

# ── 시트1: 메인 시트 (기존 + 지역) ──────────────────────

print("3. 메인 시트 업데이트 중...")
ws1 = spreadsheet.sheet1
ws1.clear()
main_header = ["접수자", "아이디어 요약", "분야", "단계", "접수일", "상태", "감지 시각", "지역"]
ws1.append_row(main_header)

main_rows = []
for item in items:
    applicant = item.get("applicant") or {}
    nickname = applicant.get("nickname") or "알수없음"
    division = item.get("division") or ""
    stage = item.get("stage") or ""
    created = item.get("createdAt") or ""
    if "T" in created:
        created = created[:10].replace("-", ".")

    main_rows.append([
        nickname,
        item.get("summary", ""),
        DIVISION_MAP.get(division, division),
        STAGE_MAP.get(stage, stage),
        created,
        "등록",
        now,
        "",  # 지역은 상세 조회 후 업데이트
    ])

if main_rows:
    ws1.append_rows(main_rows)
print(f"   메인 시트 {len(main_rows)}건 입력 완료")

# ── 시트2: 상세정보 탭 ──────────────────────────────────

print("4. 상세정보 탭 생성 중...")
try:
    ws2 = spreadsheet.worksheet("상세정보")
    ws2.clear()
except gspread.exceptions.WorksheetNotFound:
    ws2 = spreadsheet.add_worksheet(title="상세정보", rows=200, cols=20)

detail_header = [
    "접수자", "아이디어 요약", "지역", "지원분야",
    "팀원 정보",
    "Q1 질문", "Q1 답변",
    "Q2 질문", "Q2 답변",
    "Q3 질문", "Q3 답변",
    "접수일", "감지 시각",
]
ws2.append_row(detail_header)

print("5. 각 아이디어 상세 조회 중...")
detail_rows = []
region_updates = []  # 메인 시트 지역 컬럼 업데이트용

for idx, item in enumerate(items):
    idea_id = item.get("id")
    applicant = item.get("applicant") or {}
    nickname = applicant.get("nickname") or "알수없음"
    created = item.get("createdAt") or ""
    if "T" in created:
        created = created[:10].replace("-", ".")

    print(f"   [{idx+1}/{len(items)}] {nickname} 상세 조회...")

    detail = None
    if idea_id:
        try:
            r = requests.get(f"{IDEA_DETAIL_URL}/{idea_id}", headers=headers, timeout=10)
            if r.status_code == 200:
                detail = r.json().get("data")
                if idx == 0:
                    print(f"   상세 API 응답 키: {list(detail.keys()) if detail else 'None'}")
        except Exception as e:
            print(f"   상세 조회 실패: {e}")

    region = ""
    support_area = ""
    member_str = ""
    qa_cells = ["", "", "", "", "", ""]

    if detail:
        raw_region = detail.get("region") or ""
        region = REGION_MAP.get(raw_region, raw_region)
        support_area = detail.get("supportArea") or ""

        # 팀원
        members = detail.get("teamMembers") or detail.get("members") or []
        if isinstance(members, list):
            member_str = ", ".join(
                (m.get("name", "") + "(" + m.get("role", "") + ")"
                 if isinstance(m, dict) else str(m))
                for m in members
            )

        # Q&A
        qa = detail.get("answers") or detail.get("qna") or detail.get("questions") or []
        qa_cells = []
        for j in range(3):
            if j < len(qa):
                q_item = qa[j]
                if isinstance(q_item, dict):
                    qa_cells.append(q_item.get("question", q_item.get("title", "")))
                    qa_cells.append(q_item.get("answer", q_item.get("content", "")))
                else:
                    qa_cells.append(str(q_item))
                    qa_cells.append("")
            else:
                qa_cells.append("")
                qa_cells.append("")

    # 메인 시트 지역 업데이트 (row idx+2 because of header)
    if region:
        region_updates.append((idx + 2, 8, region))

    detail_rows.append([
        nickname,
        item.get("summary", ""),
        region,
        support_area,
        member_str,
        *qa_cells,
        created,
        now,
    ])

if detail_rows:
    ws2.append_rows(detail_rows)
print(f"   상세정보 {len(detail_rows)}건 입력 완료")

# 메인 시트 지역 컬럼 backfill
if region_updates:
    print("6. 메인 시트 지역 컬럼 업데이트 중...")
    for row, col, val in region_updates:
        ws1.update_cell(row, col, val)
    print(f"   {len(region_updates)}건 지역 정보 업데이트 완료")

# seen_ideas.json도 id + region 포함하여 업데이트
print("7. seen_ideas.json 업데이트 중...")
seen = []
for idx, item in enumerate(items):
    applicant = item.get("applicant") or {}
    nickname = applicant.get("nickname") or "알수없음"
    division = item.get("division") or ""
    stage = item.get("stage") or ""
    created = item.get("createdAt") or ""
    if "T" in created:
        created = created[:10].replace("-", ".")
    entry = {
        "id": item.get("id"),
        "name": nickname,
        "summary": item.get("summary", ""),
        "field": DIVISION_MAP.get(division, division),
        "stage": STAGE_MAP.get(stage, stage),
        "date": created,
    }
    # 상세정보에서 region 가져오기
    if idx < len(detail_rows):
        entry["region"] = detail_rows[idx][2]  # region column
    seen.append(entry)

SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"   seen_ideas.json {len(seen)}건 업데이트 완료")

print("\n✅ 전체 완료!")
