"""
YouTube Channel Discovery Bot
구독 채널 기반으로 관련 채널을 자동 발견하여 Notion에 저장
"""

import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Set

# API Keys (GitHub Secrets에서 가져옴)
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
NOTION_DATABASE_ID = os.environ.get('NOTION_DATABASE_ID')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

# 기존 채널 목록 URL
CHANNELS_JSON_URL = "https://raw.githubusercontent.com/bansungju/youtube/main/channels.json"


def get_existing_channels() -> Dict[str, str]:
    """기존 구독 채널 목록 가져오기"""
    response = requests.get(CHANNELS_JSON_URL)
    data = response.json()
    return {ch['channel_id']: ch['name'] for ch in data['channels']}


def get_channel_details(channel_ids: List[str]) -> List[Dict]:
    """YouTube API로 채널 상세 정보 조회"""
    channels = []

    # API는 한 번에 50개까지 조회 가능
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        url = "https://www.googleapis.com/youtube/v3/channels"
        params = {
            'key': YOUTUBE_API_KEY,
            'id': ','.join(batch),
            'part': 'snippet,statistics,brandingSettings'
        }

        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            channels.extend(data.get('items', []))
        else:
            print(f"⚠️ API 오류: {response.status_code}")

    return channels


def get_featured_channels(channel_id: str) -> List[str]:
    """채널의 추천 채널(Featured Channels) 목록 가져오기"""
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        'key': YOUTUBE_API_KEY,
        'id': channel_id,
        'part': 'brandingSettings'
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        items = data.get('items', [])
        if items:
            branding = items[0].get('brandingSettings', {})
            channel_settings = branding.get('channel', {})
            featured = channel_settings.get('featuredChannelsUrls', [])
            return featured
    return []


def search_related_channels(query: str, max_results: int = 5) -> List[Dict]:
    """키워드로 관련 채널 검색"""
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        'key': YOUTUBE_API_KEY,
        'q': query,
        'type': 'channel',
        'part': 'snippet',
        'maxResults': max_results,
        'relevanceLanguage': 'en'
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get('items', [])
    return []


def filter_quality_channels(channels: List[Dict], min_subscribers: int = 10000) -> List[Dict]:
    """품질 필터: 구독자 수, 영상 수 기준"""
    filtered = []

    for ch in channels:
        stats = ch.get('statistics', {})
        subscriber_count = int(stats.get('subscriberCount', 0))
        video_count = int(stats.get('videoCount', 0))

        # 필터 조건: 구독자 1만 이상, 영상 10개 이상
        if subscriber_count >= min_subscribers and video_count >= 10:
            filtered.append({
                'channel_id': ch['id'],
                'name': ch['snippet']['title'],
                'description': ch['snippet'].get('description', '')[:200],
                'subscriber_count': subscriber_count,
                'video_count': video_count,
                'thumbnail': ch['snippet']['thumbnails']['default']['url'],
                'url': f"https://www.youtube.com/channel/{ch['id']}"
            })

    return filtered


def save_to_notion(channels: List[Dict]) -> int:
    """발견된 채널을 Notion DB에 저장"""
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        print("⚠️ Notion API 설정 없음 - 저장 스킵")
        return 0

    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    }

    saved_count = 0

    for ch in channels:
        data = {
            'parent': {'database_id': NOTION_DATABASE_ID},
            'properties': {
                '채널명': {'title': [{'text': {'content': ch['name']}}]},
                'Channel ID': {'rich_text': [{'text': {'content': ch['channel_id']}}]},
                'URL': {'url': ch['url']},
                '구독자': {'number': ch['subscriber_count']},
                '영상수': {'number': ch['video_count']},
                '상태': {'select': {'name': '검토 대상'}},
                '발견일': {'date': {'start': datetime.now().isoformat()[:10]}}
            }
        }

        response = requests.post(
            'https://api.notion.com/v1/pages',
            headers=headers,
            json=data
        )

        if response.status_code == 200:
            saved_count += 1
        else:
            print(f"⚠️ Notion 저장 실패: {ch['name']} - {response.status_code}")

    return saved_count


def send_slack_notification(new_channels: List[Dict]):
    """슬랙으로 발견 결과 알림"""
    if not SLACK_WEBHOOK_URL or not new_channels:
        return

    message = f"🔍 *새로운 AI 채널 {len(new_channels)}개 발견!*\n\n"

    for ch in new_channels[:5]:  # 상위 5개만 표시
        subscribers = f"{ch['subscriber_count']:,}"
        message += f"• *{ch['name']}* ({subscribers} 구독자)\n"
        message += f"  {ch['url']}\n\n"

    if len(new_channels) > 5:
        message += f"_...외 {len(new_channels) - 5}개 더_\n"

    message += "\n📋 Notion '검토 대상' DB에서 확인하세요!"

    payload = {'text': message}
    requests.post(SLACK_WEBHOOK_URL, json=payload)


def load_discovered_channels() -> Set[str]:
    """이미 발견된 채널 ID 로드"""
    try:
        with open('discovered_channels.json', 'r') as f:
            data = json.load(f)
            return set(data.get('channel_ids', []))
    except FileNotFoundError:
        return set()


def save_discovered_channels(channel_ids: Set[str]):
    """발견된 채널 ID 저장"""
    with open('discovered_channels.json', 'w') as f:
        json.dump({
            'channel_ids': list(channel_ids),
            'last_updated': datetime.now().isoformat()
        }, f, indent=2)


def main():
    print("🚀 YouTube Channel Discovery 시작")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)

    # 1. 기존 채널 목록 가져오기
    existing_channels = get_existing_channels()
    existing_ids = set(existing_channels.keys())
    print(f"📺 기존 구독 채널: {len(existing_ids)}개")

    # 2. 이미 발견된 채널 로드
    discovered_ids = load_discovered_channels()
    print(f"📋 이미 발견된 채널: {len(discovered_ids)}개")

    # 3. 각 채널의 추천 채널 수집
    all_related_ids = set()

    for channel_id, channel_name in existing_channels.items():
        featured = get_featured_channels(channel_id)
        if featured:
            print(f"  ✅ {channel_name}: {len(featured)}개 추천 채널")
            all_related_ids.update(featured)

    print(f"\n🔗 총 관련 채널 발견: {len(all_related_ids)}개")

    # 4. 새로운 채널만 필터링 (기존 + 이미 발견된 채널 제외)
    new_ids = all_related_ids - existing_ids - discovered_ids
    print(f"🆕 새로운 채널: {len(new_ids)}개")

    if not new_ids:
        print("\n✨ 새로운 채널이 없습니다.")
        return

    # 5. 새 채널 상세 정보 조회
    new_channels_detail = get_channel_details(list(new_ids))
    print(f"📊 상세 정보 조회 완료: {len(new_channels_detail)}개")

    # 6. 품질 필터링
    quality_channels = filter_quality_channels(new_channels_detail)
    print(f"⭐ 품질 필터 통과: {len(quality_channels)}개")

    if not quality_channels:
        print("\n✨ 품질 기준을 충족하는 새 채널이 없습니다.")
        # 발견된 채널 ID 저장 (중복 방지)
        discovered_ids.update(new_ids)
        save_discovered_channels(discovered_ids)
        return

    # 7. 구독자 수 기준 정렬
    quality_channels.sort(key=lambda x: x['subscriber_count'], reverse=True)

    # 8. Notion에 저장
    saved = save_to_notion(quality_channels)
    print(f"💾 Notion 저장: {saved}개")

    # 9. 슬랙 알림
    send_slack_notification(quality_channels)
    print("📤 Slack 알림 전송 완료")

    # 10. 발견된 채널 ID 저장
    discovered_ids.update(new_ids)
    save_discovered_channels(discovered_ids)

    print("\n" + "=" * 50)
    print(f"✅ 완료! {len(quality_channels)}개 새 채널 발견")

    # 결과 출력
    print("\n📋 발견된 채널 목록:")
    for ch in quality_channels[:10]:
        print(f"  • {ch['name']} ({ch['subscriber_count']:,} 구독자)")


if __name__ == "__main__":
    main()
