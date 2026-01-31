"""
YouTube Channel Discovery Bot
구독 채널 기반으로 관련 채널을 자동 발견하여 Notion에 저장
(중복 체크 기능 포함)
"""

import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Set

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
NOTION_DATABASE_ID = os.environ.get('NOTION_DATABASE_ID')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

CHANNELS_JSON_URL = "https://raw.githubusercontent.com/bansungju/youtube/main/channels.json"

SEARCH_KEYWORDS = [
    "AI tutorial",
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "data science",
    "python programming",
    "LLM large language model",
    "GPT tutorial",
    "neural network",
    "tech review"
]

def get_existing_channels() -> Dict[str, str]:
    response = requests.get(CHANNELS_JSON_URL)
    data = response.json()
    return {ch['channel_id']: ch['name'] for ch in data['channels']}


def get_notion_existing_channel_ids() -> Set[str]:
    """Notion DB에 이미 존재하는 Channel ID 목록 조회 (중복 방지용)"""
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        return set()
    
    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    }
    
    existing_ids = set()
    has_more = True
    start_cursor = None
    
    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        
        response = requests.post(
            f'https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query',
            headers=headers,
            json=body
        )
        
        if response.status_code != 200:
            print(f"⚠️ Notion DB 조회 실패: {response.status_code}")
            break
        
        data = response.json()
        
        for page in data.get('results', []):
            channel_id_prop = page.get('properties', {}).get('Channel ID', {}).get('rich_text', [])
            if channel_id_prop:
                channel_id = channel_id_prop[0].get('plain_text', '')
                if channel_id:
                    existing_ids.add(channel_id)
        
        has_more = data.get('has_more', False)
        start_cursor = data.get('next_cursor')
    
    print(f"📋 Notion DB 기존 채널: {len(existing_ids)}개")
    return existing_ids


def get_channel_details(channel_ids: List[str]) -> List[Dict]:
    channels = []
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        url = "https://www.googleapis.com/youtube/v3/channels"
        params = {'key': YOUTUBE_API_KEY, 'id': ','.join(batch), 'part': 'snippet,statistics'}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            channels.extend(response.json().get('items', []))
    return channels


def search_channels_by_keyword(keyword: str, max_results: int = 10) -> List[str]:
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {'key': YOUTUBE_API_KEY, 'q': keyword, 'type': 'channel', 'part': 'snippet', 'maxResults': max_results, 'order': 'relevance'}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return [item['snippet']['channelId'] for item in response.json().get('items', [])]
    print(f"⚠️ Search API 오류 ({keyword}): {response.status_code}")
    return []


def filter_quality_channels(channels: List[Dict], min_subscribers: int = 10000) -> List[Dict]:
    filtered = []
    for ch in channels:
        stats = ch.get('statistics', {})
        if stats.get('hiddenSubscriberCount', False):
            continue
        subscriber_count = int(stats.get('subscriberCount', 0))
        video_count = int(stats.get('videoCount', 0))
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


def save_to_notion(channels: List[Dict], existing_notion_ids: Set[str]) -> int:
    """Notion에 저장 (중복 체크 포함)"""
    print(f"\n🔍 Notion 디버그 정보:")
    print(f"  - API Key 존재: {bool(NOTION_API_KEY)}")
    print(f"  - Database ID: {NOTION_DATABASE_ID}")
    print(f"  - 저장 대상 채널 수: {len(channels)}")
    
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        print("⚠️ Notion API 설정 없음 - 저장 스킵")
        return 0

    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    }
    
    saved_count = 0
    skipped_count = 0
    
    for ch in channels:
        # 🔥 중복 체크: 이미 Notion에 있는 Channel ID면 스킵
        if ch['channel_id'] in existing_notion_ids:
            print(f"  ⏭️ 중복 스킵: {ch['name']} ({ch['channel_id']})")
            skipped_count += 1
            continue
        
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
        
        response = requests.post('https://api.notion.com/v1/pages', headers=headers, json=data)
        
        if response.status_code == 200:
            saved_count += 1
            print(f"  ✅ 저장: {ch['name']}")
            # 저장 후 existing_notion_ids에 추가 (같은 실행 내 중복 방지)
            existing_notion_ids.add(ch['channel_id'])
        else:
            print(f"  ❌ 저장 실패: {ch['name']} - {response.status_code}")
    
    if skipped_count > 0:
        print(f"\n⏭️ 중복으로 스킵된 채널: {skipped_count}개")
    
    return saved_count


def send_slack_notification(new_channels: List[Dict]):
    if not SLACK_WEBHOOK_URL or not new_channels:
        return
    message = f"🔍 *새로운 AI 채널 {len(new_channels)}개 발견!*\n\n"
    for ch in new_channels[:5]:
        message += f"• *{ch['name']}* ({ch['subscriber_count']:,} 구독자)\n  {ch['url']}\n\n"
    if len(new_channels) > 5:
        message += f"_...외 {len(new_channels) - 5}개 더_\n"
    message += "\n📋 Notion '검토 대상' DB에서 확인하세요!"
    requests.post(SLACK_WEBHOOK_URL, json={'text': message})


def load_discovered_channels() -> Set[str]:
    try:
        with open('discovered_channels.json', 'r') as f:
            return set(json.load(f).get('channel_ids', []))
    except FileNotFoundError:
        return set()


def save_discovered_channels(channel_ids: Set[str]):
    with open('discovered_channels.json', 'w') as f:
        json.dump({'channel_ids': list(channel_ids), 'last_updated': datetime.now().isoformat()}, f, indent=2)


def main():
    print("🚀 YouTube Channel Discovery 시작")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    existing_channels = get_existing_channels()
    existing_ids = set(existing_channels.keys())
    print(f"📺 기존 구독 채널: {len(existing_ids)}개")
    
    # 🔥 Notion DB에서 기존 Channel ID 조회 (중복 방지)
    existing_notion_ids = get_notion_existing_channel_ids()
    
    discovered_ids = load_discovered_channels()
    print(f"📋 이미 발견된 채널 (로컬): {len(discovered_ids)}개")
    
    print(f"\n🔍 {len(SEARCH_KEYWORDS)}개 키워드로 검색 중...")
    all_found_ids = set()
    for keyword in SEARCH_KEYWORDS:
        found_ids = search_channels_by_keyword(keyword, max_results=10)
        if found_ids:
            print(f"  ✅ '{keyword}': {len(found_ids)}개 채널")
            all_found_ids.update(found_ids)
    
    print(f"\n🔗 총 검색된 채널: {len(all_found_ids)}개")
    
    # 기존 구독 채널, 로컬 발견 목록, Notion DB에 있는 채널 모두 제외
    new_ids = all_found_ids - existing_ids - discovered_ids - existing_notion_ids
    print(f"🆕 새로운 채널: {len(new_ids)}개")
    
    if not new_ids:
        print("\n✨ 새로운 채널이 없습니다.")
        return
    
    new_channels_detail = get_channel_details(list(new_ids))
    print(f"📊 상세 정보 조회 완료: {len(new_channels_detail)}개")
    
    quality_channels = filter_quality_channels(new_channels_detail)
    print(f"⭐ 품질 필터 통과: {len(quality_channels)}개")
    
    if not quality_channels:
        print("\n✨ 품질 기준을 충족하는 새 채널이 없습니다.")
        discovered_ids.update(new_ids)
        save_discovered_channels(discovered_ids)
        return
    
    quality_channels.sort(key=lambda x: x['subscriber_count'], reverse=True)
    
    # 🔥 중복 체크 포함된 저장 함수 호출
    saved = save_to_notion(quality_channels, existing_notion_ids)
    print(f"💾 Notion 저장: {saved}개")
    
    # Slack 알림은 실제 저장된 채널만
    if saved > 0:
        # 실제 저장된 채널만 필터링
        saved_channels = [ch for ch in quality_channels if ch['channel_id'] in existing_notion_ids]
        send_slack_notification(saved_channels[-saved:] if saved_channels else quality_channels[:saved])
        print("📤 Slack 알림 전송 완료")
    
    discovered_ids.update(new_ids)
    save_discovered_channels(discovered_ids)
    
    print("\n" + "=" * 50)
    print(f"✅ 완료! {saved}개 새 채널 저장 (중복 제외)")


if __name__ == "__main__":
    main()
