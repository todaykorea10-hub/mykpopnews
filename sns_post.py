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

        auth = tweepy.OAuth1UserHandler(
            config.TWITTER_API_KEY,
            config.TWITTER_API_SECRET,
            config.TWITTER_ACCESS_TOKEN,
            config.TWITTER_ACCESS_TOKEN_SECRET,
        )
        api_v1 = tweepy.API(auth)  # 이미지 업로드는 아직 v1.1 API로만 가능
        client = tweepy.Client(
            consumer_key=config.TWITTER_API_KEY,
            consumer_secret=config.TWITTER_API_SECRET,
            access_token=config.TWITTER_ACCESS_TOKEN,
            access_token_secret=config.TWITTER_ACCESS_TOKEN_SECRET,
        )

        media_ids = None
        if image_bytes:
            media = api_v1.media_upload(filename="card.png", file=io.BytesIO(image_bytes))
            media_ids = [media.media_id]

        text = f"{title}\n\n{url}"
        if len(text) > 270:
            text = text[:267] + "..."

        client.create_tweet(text=text, media_ids=media_ids)
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
