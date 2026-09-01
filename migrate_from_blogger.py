"""
Blogger -> WordPress 이관 스크립트

기존 Blogger 블로그(공개 블로그 기준, OAuth 불필요)의 글을 전부 가져와서
워드프레스로 옮깁니다.

처리 내용:
1) Blogger 공개 JSON 피드에서 전체 글을 페이지 단위로 수집
2) 본문 속 원본 사진은 저작권/초상권 리스크 방지를 위해 완전히 제거하고,
   auto_publish.py와 동일하게 그룹 사전 제작 이미지(있는 경우) 또는
   타이포그래피 그래픽 카드로 대표이미지를 만듭니다
3) 라벨(카테고리) 매핑, 원래 발행일 유지
4) 이미 이관한 글은 건너뛰어서 여러 번 실행해도 중복 없이 이어서 처리 가능
5) config.py의 MIGRATE_SINCE_DATE / MIGRATE_UNTIL_DATE로 특정 날짜(범위)만
   골라서 이관 가능

실행: python migrate_from_blogger.py
config.py에 BLOGGER_BLOG_URL 등 설정값을 채운 뒤 사용하세요.
"""

import base64
import json
import os
import re
import time
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

import config
from auto_publish import (
    generate_typography_card,
    detect_group,
    load_group_images,
    pick_group_image_media_id,
)

MIGRATED_FILE = "migrated_posts.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ---------------------------------------------------------------------------
# 이관 이력 관리
# ---------------------------------------------------------------------------

def load_migrated():
    if os.path.exists(MIGRATED_FILE):
        try:
            with open(MIGRATED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_migrated(migrated):
    with open(MIGRATED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(migrated), f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 1. Blogger 공개 피드에서 전체 글 수집
# ---------------------------------------------------------------------------

def fetch_all_blogger_posts(batch_size=150):
    """공개 Blogger 블로그의 전체 글을 발행일 오래된 순으로 가져온다."""
    posts = []
    start_index = 1
    while True:
        url = (
            f"{config.BLOGGER_BLOG_URL}/feeds/posts/default"
            f"?alt=json&max-results={batch_size}&start-index={start_index}"
            f"&orderby=published"
        )
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        entries = resp.json().get("feed", {}).get("entry", [])
        if not entries:
            break

        for entry in entries:
            title = entry.get("title", {}).get("$t", "").strip()
            content_html = entry.get("content", {}).get("$t", "")
            published = entry.get("published", {}).get("$t", "")
            alt_link = next(
                (l["href"] for l in entry.get("link", []) if l.get("rel") == "alternate"),
                None,
            )
            labels = [c["term"] for c in entry.get("category", [])]
            posts.append({
                "title": title,
                "content": content_html,
                "published": published,
                "url": alt_link,
                "labels": labels,
            })

        print(f"  … {len(entries)}건 수집 (누적 {len(posts)}건)")
        if len(entries) < batch_size:
            break
        start_index += batch_size
        time.sleep(1)

    return posts


# ---------------------------------------------------------------------------
# 2. 이미지: 본문 사진은 완전히 제거하고, 그룹 사전 제작 이미지 또는
#    타이포그래피 카드로 대표이미지를 만든다 (저작권/초상권 리스크 없음)
# ---------------------------------------------------------------------------

def wp_auth_header():
    token = base64.b64encode(f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def strip_images_from_content(html):
    return re.sub(r"<img[^>]*>", "", html)


def upload_media(image_bytes, filename, mime_type="image/png"):
    resp = requests.post(
        f"{config.WP_URL}/wp-json/wp/v2/media",
        headers={**wp_auth_header(), "Content-Disposition": f"attachment; filename={filename}", "Content-Type": mime_type},
        data=image_bytes,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def build_featured_media(title, category_name):
    """그룹 사전 제작 이미지가 있으면 그걸 재사용하고, 없으면 타이포그래피 카드를 새로 만든다."""
    detected_group = detect_group(title)
    if getattr(config, "ENABLE_GROUP_IMAGES", False) and detected_group:
        group_images = load_group_images()
        media_id = pick_group_image_media_id(detected_group, group_images)
        if media_id:
            return media_id

    try:
        image_bytes, mime_type = generate_typography_card(category_name, title)
        return upload_media(image_bytes, "kpop-card.png", mime_type)
    except Exception as e:
        print(f"    ⚠️ 그래픽 카드 생성 실패(이미지 없이 발행): {e}")
        return None


# ---------------------------------------------------------------------------
# 3. 카테고리 매핑 + 발행
# ---------------------------------------------------------------------------

def get_or_create_category(name):
    resp = requests.get(f"{config.WP_URL}/wp-json/wp/v2/categories", headers=wp_auth_header(), params={"search": name}, timeout=10)
    resp.raise_for_status()
    results = resp.json()
    if results:
        return results[0]["id"]
    create = requests.post(f"{config.WP_URL}/wp-json/wp/v2/categories", headers=wp_auth_header(), json={"name": name}, timeout=10)
    create.raise_for_status()
    return create.json()["id"]


def parse_blogger_date_to_gmt(published_str):
    """Blogger의 ISO8601(+타임존) 날짜를 워드프레스가 원하는 UTC 문자열로 변환."""
    try:
        cleaned = published_str.replace("Z", "+00:00")
        dt = __import__("datetime").datetime.fromisoformat(cleaned)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def publish_migrated_post(title, content_html, category_ids, featured_media_id, date_gmt, original_url):
    payload = {
        "title": title,
        "content": content_html,
        "status": config.IMPORT_POST_STATUS,
        "categories": category_ids or [],
        "meta": {"source_url": original_url, "source_name": "이전 블로그 이관 글"},
    }
    if featured_media_id:
        payload["featured_media"] = featured_media_id
    if date_gmt:
        payload["date_gmt"] = date_gmt

    resp = requests.post(f"{config.WP_URL}/wp-json/wp/v2/posts", headers=wp_auth_header(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 메인 루프
# ---------------------------------------------------------------------------

def filter_by_date_range(posts):
    """config.py의 MIGRATE_SINCE_DATE / MIGRATE_UNTIL_DATE 설정에 따라 날짜 범위로 걸러낸다."""
    since = getattr(config, "MIGRATE_SINCE_DATE", None)
    until = getattr(config, "MIGRATE_UNTIL_DATE", None)
    if not since and not until:
        return posts

    filtered = []
    for post in posts:
        if not post.get("published"):
            continue
        try:
            post_date = post["published"][:10]  # "2026-08-31T09:05:33..." → "2026-08-31"
        except Exception:
            continue
        if since and post_date < since:
            continue
        if until and post_date > until:
            continue
        filtered.append(post)
    return filtered


def run():
    migrated = load_migrated()

    print("📥 Blogger에서 전체 글 목록을 가져오는 중...")
    posts = fetch_all_blogger_posts()

    posts = filter_by_date_range(posts)
    since = getattr(config, "MIGRATE_SINCE_DATE", None)
    until = getattr(config, "MIGRATE_UNTIL_DATE", None)
    if since or until:
        print(f"📅 날짜 필터 적용: {since or '(제한없음)'} ~ {until or '(제한없음)'} → {len(posts)}건 해당")

    remaining = [p for p in posts if p["url"] and p["url"] not in migrated]
    print(f"📋 총 {len(posts)}건 중 이관 대상 {len(remaining)}건 (이미 이관됨 {len(posts) - len(remaining)}건)\n")

    total_done = 0
    batch_size = config.MAX_IMPORT_POSTS_PER_RUN or len(remaining)

    for batch_start in range(0, len(remaining), batch_size):
        batch = remaining[batch_start:batch_start + batch_size]
        print(f"\n--- 배치 {batch_start // batch_size + 1} 시작 (남은 {len(remaining) - batch_start}건) ---")

        for post in batch:
            print(f"[{total_done + 1}/{len(remaining)}] {post['title']}")
            try:
                new_content = strip_images_from_content(post["content"])

                category_ids = []
                category_labels = post["labels"] or [config.DEFAULT_IMPORT_CATEGORY]
                for label in category_labels:
                    category_ids.append(get_or_create_category(label))

                featured_id = build_featured_media(post["title"], category_labels[0])

                date_gmt = parse_blogger_date_to_gmt(post["published"]) if post["published"] else None

                result = publish_migrated_post(
                    title=post["title"],
                    content_html=new_content,
                    category_ids=category_ids,
                    featured_media_id=featured_id,
                    date_gmt=date_gmt,
                    original_url=post["url"],
                )
                print(f"  ✔ 이관 완료: {result.get('link')}")
                migrated.add(post["url"])
                save_migrated(migrated)
                total_done += 1
                time.sleep(2)  # 워드프레스/이미지 서버 부담 완화
            except Exception as e:
                print(f"  → 이관 실패: {e}")

        if batch_start + batch_size < len(remaining):
            print(f"⏳ 배치 간 휴식 {config.MIGRATE_BATCH_PAUSE_SECONDS}초...")
            time.sleep(config.MIGRATE_BATCH_PAUSE_SECONDS)

    print(f"\n🏁 전체 완료. 이번 실행에서 {total_done}건 이관. (전체 {len(posts)}건 중 누적 이관 {len(migrated)}건)")


if __name__ == "__main__":
    run()
