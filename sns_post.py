"""
새 글이 발행될 때 X(트위터), 인스타그램에 자동으로 홍보 게시물을 올리는 모듈.

- X(트위터): tweepy 라이브러리로 텍스트 + 이미지 트윗 (OAuth 1.0a, 앱 권한 "Read and Write" 필요)
- 인스타그램: Facebook Graph API로 이미지 + 캡션 게시 (Business/Creator 계정 + 연결된 Facebook 페이지 필요)

둘 다 config.py에서 ENABLE_TWITTER_POST / ENABLE_INSTAGRAM_POST 로 켜고 끌 수 있고,
꺼져있으면 아무 일도 하지 않습니다 (안전하게 기본값 False).
"""

import io

import requests

import config


def post_to_twitter(title, url, image_bytes=None):
    if not getattr(config, "ENABLE_TWITTER_POST", False):
        return
    try:
        import tweepy

        # 참고: X API 무료 등급은 이미지 업로드(v1.1 media_upload)를 지원하지 않아
        # 유료 등급(Basic $200/월~)이 필요합니다. 그래서 이미지 첨부 없이 텍스트+링크만
        # 게시합니다 — 링크를 걸면 X가 사이트의 OG 이미지를 자동으로 가져와
        # 미리보기 카드를 만들어주므로, 이미지 업로드 없이도 카드형으로 보입니다.
        client = tweepy.Client(
            consumer_key=config.TWITTER_API_KEY,
            consumer_secret=config.TWITTER_API_SECRET,
            access_token=config.TWITTER_ACCESS_TOKEN,
            access_token_secret=config.TWITTER_ACCESS_TOKEN_SECRET,
        )

        text = f"{title}\n\n{url}"
        if len(text) > 270:
            text = text[:267] + "..."

        client.create_tweet(text=text)
        print("  🐦 X(트위터) 게시 완료")
    except Exception as e:
        print(f"  ⚠️ X(트위터) 게시 실패: {e}")


def post_to_instagram(caption, image_url):
    if not getattr(config, "ENABLE_INSTAGRAM_POST", False):
        return
    if not image_url:
        print("  ⚠️ 인스타그램 게시 건너뜀: 이미지 URL이 없음")
        return
    try:
        base = f"https://graph.facebook.com/v19.0/{config.INSTAGRAM_BUSINESS_ID}"

        resp = requests.post(
            f"{base}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=20,
        )
        resp.raise_for_status()
        creation_id = resp.json()["id"]

        resp2 = requests.post(
            f"{base}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=20,
        )
        resp2.raise_for_status()
        print("  📸 인스타그램 게시 완료")
    except Exception as e:
        print(f"  ⚠️ 인스타그램 게시 실패: {e}")
