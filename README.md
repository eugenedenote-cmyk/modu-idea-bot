# modu-idea-bot

모두의창업 아이디어 API를 주기적으로 확인하고 신규/삭제 아이디어를 Slack과 Google Sheets에 기록하는 GitHub Actions 봇입니다.

## REFRESH_TOKEN 만료 대응

`REFRESH_TOKEN`은 짧은 만료 시간이 있는 JWT입니다. GitHub Actions에서 토큰을 갱신해도 새 토큰을 GitHub Secret에 다시 저장하지 않으면 다음 날부터 스크래퍼가 실패합니다.

필요한 GitHub repository secrets:

- `REFRESH_TOKEN`: 모두의창업에 다시 로그인해서 추출한 최신 refresh token
- `SLACK_WEBHOOK_URL`: Slack Incoming Webhook URL
- `GSHEET_CREDENTIALS`: Google service account JSON
- `SECRETS_ADMIN_TOKEN`: GitHub Actions secret을 업데이트할 수 있는 GitHub token

`SECRETS_ADMIN_TOKEN`은 fine-grained personal access token으로 만들고, 이 저장소에 대해 `Administration: Read and write` 권한을 부여합니다. 이 secret이 있으면 스크래퍼가 매 실행마다 새 `REFRESH_TOKEN`을 받아 GitHub Secret에 다시 저장합니다.

수동 복구 순서:

1. 모두의창업에 브라우저로 다시 로그인합니다.
2. 개발자 도구에서 새 `refreshToken`을 추출합니다.
3. GitHub repository secret `REFRESH_TOKEN` 값을 새 토큰으로 교체합니다.
4. `SECRETS_ADMIN_TOKEN`이 없으면 위 권한으로 생성해서 repository secret에 추가합니다.
5. GitHub Actions에서 `Idea Scraper` 워크플로를 수동 실행합니다.
