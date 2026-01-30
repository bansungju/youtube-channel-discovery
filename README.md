# 🔍 YouTube Channel Discovery

구독한 AI 유튜브 채널을 기반으로 **관련 채널을 자동 발견**하여 Notion에 저장하는 봇

## 🎯 동작 방식

```
기존 구독 채널 (35개)
       ↓
각 채널의 "추천 채널" 섹션 조회 (YouTube API)
       ↓
중복 제거 + 품질 필터링 (구독자 1만+, 영상 10개+)
       ↓
새로 발견된 채널 → Notion "검토 대상" DB에 저장
       ↓
Slack 알림 전송
```

## ⚙️ 설정

### GitHub Secrets 필요

| Secret Name | 설명 |
|-------------|------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 키 |
| `NOTION_API_KEY` | Notion Integration 토큰 |
| `NOTION_DATABASE_ID` | "검토 대상" 데이터베이스 ID |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |

### Notion DB 스키마

| 속성명 | 타입 | 설명 |
|--------|------|------|
| 채널명 | Title | 채널 이름 |
| Channel ID | Text | YouTube 채널 ID |
| URL | URL | 채널 링크 |
| 구독자 | Number | 구독자 수 |
| 영상수 | Number | 업로드된 영상 수 |
| 상태 | Select | 검토 대상/구독 완료/스킵 |
| 발견일 | Date | 발견된 날짜 |

## 🚀 실행

### 자동 실행
- 매일 오전 9시 (KST)에 GitHub Actions로 자동 실행

### 수동 실행
1. GitHub → Actions 탭
2. "YouTube Channel Discovery" 워크플로우 선택
3. "Run workflow" 클릭

## 📊 관련 프로젝트

- [youtube](https://github.com/bansungju/youtube) - YouTube → Slack 알림 봇

## 💰 비용

| 항목 | 비용 |
|------|------|
| YouTube API | 무료 (일일 10,000 유닛) |
| Notion API | 무료 |
| GitHub Actions | 무료 |

---

*마지막 업데이트: 2026년 1월*
