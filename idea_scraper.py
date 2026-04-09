"""
모두의창업 아이디어 스크래퍼 v3
- API 직접 호출 (브라우저/Claude Code 불필요)
- refreshToken 자동 갱신
- 신규 아이디어 Slack Webhook 전송
- 로컬 + GitHub Actions 양쪽에서 동작
"""

import json
import logging
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
SEEN_PATH = BASE_DIR / "seen_ideas.json"
LOG_PATH = BASE_DIR / "idea_scraper.log"

API_BASE = "https://poseidon-prod.modoo.or.kr"
REFRESH_URL = f"{API_BASE}/api/v1/token/refresh"
IDEAS_URL = f"{API_BASE}/api/v2/organization-manager/startup-ideas"
STATS_URL = f"{API_BASE}/api/v2/organization-manager/statistics"
IDEA_PAGE_URL = "https://poseidon.modoo.or.kr/idea?size=20&organizationIds=%5B75%5D"

ORG_ID = 75

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── 설정 로드 (환경변수 우선 → .env 파일 fallback) ────────

def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return env


def get_config():
    """환경변수 우선, 없으면 .env 파일에서 읽기"""
    env = load_env()
    return {
        "SLACK_WEBHOOK_URL": os.environ.get("SLACK_WEBHOOK_URL") or env.get("SLACK_WEBHOOK_URL", ""),
        "REFRESH_TOKEN": os.environ.get("REFRESH_TOKEN") or env.get("REFRESH_TOKEN", ""),
    }


def save_env(env: dict):
    lines = [
        "# Connect 워크스페이스의 Slack Incoming Webhook URL",
        f"SLACK_WEBHOOK_URL={env.get('SLACK_WEBHOOK_URL', '')}",
        "",
        "# 모두의창업 Refresh Token (자동 갱신됨)",
        f"REFRESH_TOKEN={env.get('REFRESH_TOKEN', '')}",
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")


# ── 토큰 갱신 ─────────────────────────────────────────────

def refresh_tokens(refresh_token: str) -> dict | None:
    try:
        resp = requests.post(
            REFRESH_URL,
            json={"refreshToken": refresh_token},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data")
            if data and data.get("accessToken"):
                return data
        log.error("토큰 갱신 실패: %s %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        log.error("토큰 갱신 네트워크 오류: %s", e)
    return None


# ── 아이디어 목록 조회 ────────────────────────────────────

def fetch_ideas(access_token: str) -> list | None:
    headers = {"poseidon-token": access_token}
    params = {"organizationIds[]": ORG_ID, "page": 0, "size": 100}
    try:
        resp = requests.get(IDEAS_URL, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data")
            if data:
                return data
        log.error("아이디어 조회 실패: %s %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        log.error("아이디어 조회 네트워크 오류: %s", e)
    return None


def fetch_stats(access_token: str) -> dict | None:
    headers = {"poseidon-token": access_token}
    params = {"organizationIds[]": ORG_ID}
    try:
        resp = requests.get(STATS_URL, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("data")
    except requests.RequestException:
        pass
    return None


# ── seen_ideas 관리 ───────────────────────────────────────

def load_seen() -> list:
    if not SEEN_PATH.exists():
        return []
    return json.loads(SEEN_PATH.read_text(encoding="utf-8"))


def save_seen(seen: list):
    SEEN_PATH.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def make_key(name: str, date: str) -> str:
    return f"{name}_{date}"


# ── Slack 전송 ────────────────────────────────────────────

def send_slack(webhook_url: str, blocks: list) -> bool:
    payload = {"blocks": blocks}
    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        log.error("Slack 전송 실패: %s %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        log.error("Slack 전송 네트워크 오류: %s", e)
    return False


def build_slack_blocks(new_ideas: list, stats: dict | None) -> list:
    count = len(new_ideas)
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"\U0001f195 신규 아이디어 {count}건이 등록되었습니다",
                "emoji": True,
            },
        },
    ]

    if stats:
        t = stats.get("total") or stats
        submitted = t.get("submittedUserCount", "?")
        drafting = t.get("draftUserCount", "?")
        total = t.get("totalIdeaCount", "?")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"\U0001f4ca 제출완료 {submitted} | 작성중 {drafting} | 총합 {total}",
            },
        })

    blocks.append({"type": "divider"})

    for i, idea in enumerate(new_ideas, 1):
        name = idea.get("name", "")
        summary = idea.get("summary", "")
        field = idea.get("field", "")
        stage = idea.get("stage", "")
        date = idea.get("date", "")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{i}. {name}*\n{summary}\n\U0001f3f7\ufe0f {field} \u00b7 {stage} \u00b7 {date}",
            },
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [{
            "type": "button",
            "text": {"type": "plain_text", "text": "\U0001f517 목록 바로가기", "emoji": True},
            "url": IDEA_PAGE_URL,
        }],
    })
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": "아이디어 알림봇 \u00b7 소풍커넥트 \u00b7 29분마다 자동 확인",
        }],
    })

    return blocks


# ── API 응답에서 아이디어 파싱 ─────────────────────────────

DIVISION_MAP = {"TECH": "기술", "REGION": "지역", "REGION_INVEST": "지역투자"}
STAGE_MAP = {"FIRST": "1차", "SECOND": "2차"}
RESULT_MAP = {"PENDING": "대기", "PASS": "합격", "FAIL": "불합격", "CANCEL": "취소"}


def parse_idea(item: dict) -> dict:
    applicant = item.get("applicant") or {}
    nickname = applicant.get("nickname") or "알수없음"
    summary = item.get("summary") or ""
    division = item.get("division") or ""
    stage = item.get("stage") or ""
    created = item.get("createdAt") or ""
    if "T" in created:
        created = created[:10].replace("-", ".")
    return {
        "name": nickname,
        "summary": summary,
        "field": DIVISION_MAP.get(division, division),
        "stage": STAGE_MAP.get(stage, stage),
        "date": created,
    }


# ── 메인 ──────────────────────────────────────────────────

def main():
    log.info("=== 아이디어 스크래퍼 시작 ===")

    config = get_config()
    webhook_url = config["SLACK_WEBHOOK_URL"]
    refresh_token = config["REFRESH_TOKEN"]

    if not webhook_url or webhook_url == "YOUR_WEBHOOK_URL_HERE":
        log.error("SLACK_WEBHOOK_URL이 설정되지 않았습니다.")
        return

    if not refresh_token or refresh_token == "여기에_토큰_붙여넣기":
        log.error("REFRESH_TOKEN이 설정되지 않았습니다. 브라우저 로그인 후 토큰을 추출하세요.")
        return

    # 1. 토큰 갱신
    tokens = refresh_tokens(refresh_token)
    if not tokens:
        log.error("토큰 갱신 실패. 재로그인이 필요할 수 있습니다.")
        return

    access_token = tokens["accessToken"]
    new_refresh = tokens.get("refreshToken", refresh_token)

    # .env에 새 refreshToken 저장 (로컬 실행 시)
    env = load_env()
    env["SLACK_WEBHOOK_URL"] = webhook_url
    env["REFRESH_TOKEN"] = new_refresh
    save_env(env)
    log.info("토큰 갱신 완료")

    # 2. 아이디어 목록 조회
    data = fetch_ideas(access_token)
    if data is None:
        log.error("아이디어 목록 조회 실패")
        return

    # API 응답 구조 파악
    if isinstance(data, dict):
        items = data.get("content") or data.get("ideas") or data.get("items") or []
        log.info("API 응답 키: %s, 아이디어 수: %d", list(data.keys()), len(items))
    elif isinstance(data, list):
        items = data
        log.info("API 응답: 리스트, 아이디어 수: %d", len(items))
    else:
        log.error("예상치 못한 API 응답 형태: %s", type(data))
        return

    if not items:
        log.info("조회된 아이디어가 없습니다")
        return

    # 첫 아이템 구조 로그 (디버깅용)
    log.info("첫 아이템 키: %s", list(items[0].keys()) if items else "없음")

    # 3. 파싱 + 비교
    parsed = [parse_idea(item) for item in items]
    seen = load_seen()
    seen_keys = {make_key(s["name"], s["date"]) for s in seen}

    new_ideas = [p for p in parsed if make_key(p["name"], p["date"]) not in seen_keys]

    if not new_ideas:
        log.info("새로운 아이디어가 없습니다")
        return

    log.info("신규 아이디어 %d건 발견", len(new_ideas))

    # 4. 통계 조회
    stats = fetch_stats(access_token)

    # 5. Slack 전송
    blocks = build_slack_blocks(new_ideas, stats)
    if send_slack(webhook_url, blocks):
        log.info("Slack 전송 성공")
    else:
        log.error("Slack 전송 실패")
        return

    # 6. seen_ideas 업데이트
    seen.extend(new_ideas)
    save_seen(seen)
    log.info("seen_ideas.json 업데이트 완료 (총 %d건)", len(seen))

    log.info("=== 완료 ===")


if __name__ == "__main__":
    main()
