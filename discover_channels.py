"""
YouTube Channel Discovery Bot
구독 채널 기반으로 관련 채널을 자동 발견하여 Notion에 저장
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

def save_to_notion(channels: List[Dict]) -> int:
    print(f"\n🔍 Notion 디버그 정보:")
    print(f"  - API Key 존재: {bool(NOTION_API_KEY)}")
    print(f"  - API Key 앞 10자: {NOTION_API_KEY[:10] if NOTION_API_KEY else 'None'}...")
    print(f"  - Database ID: {NOTION_DATABASE_ID}")
    print(f"  - 저장할 채널 수: {len(channels)}")
    
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        print("⚠️ Notion API 설정 없음 - 저장 스킵")
        return 0

    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    }
    
    saved_count = 0
    
    # 첫 번째 채널로 테스트
    if channels:
        ch = channels[0]
        print(f"\n🧪 첫 번째 채널 테스트: {ch['name']}")
        
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
        
        print(f"  - Request data: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}...")
        
        response = requests.post('https://api.notion.com/v1/pages', headers=headers, json=data)
        
        print(f"  - Response status: {response.status_code}")
        print(f"  - Response body: {response.text[:500]}")
        
        if response.status_code == 200:
            saved_count += 1
            print("  ✅ 첫 번째 채널 저장 성공!")
        else:
            print(f"  ❌ 첫 번째 채널 저장 실패!")
            return 0  # 첫 번째가 실패하면 나머지도 실패할 것이므로 중단

    # 나머지 채널 저장
    for ch in channels[1:]:
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
    
    discovered_ids = load_discovered_channels()
    print(f"📋 이미 발견된 채널: {len(discovered_ids)}개")
    
    print(f"\n🔍 {len(SEARCH_KEYWORDS)}개 키워드로 검색 중...")
    all_found_ids = set()
    for keyword in SEARCH_KEYWORDS:
        found_ids = search_channels_by_keyword(keyword, max_results=10)
        if found_ids:
            print(f"  ✅ '{keyword}': {len(found_ids)}개 채널")
            all_found_ids.update(found_ids)
    
    print(f"\n🔗 총 검색된 채널: {len(all_found_ids)}개")
    
    new_ids = all_found_ids - existing_ids - discovered_ids
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
    
    saved = save_to_notion(quality_channels)
    print(f"💾 Notion 저장: {saved}개")
    
    send_slack_notification(quality_channels)
    print("📤 Slack 알림 전송 완료")
    
    discovered_ids.update(new_ids)
    save_discovered_channels(discovered_ids)
    
    print("\n" + "=" * 50)
    print(f"✅ 완료! {len(quality_channels)}개 새 채널 발견")

if __name__ == "__main__":
    main()
