"""
기존에 발행된 글들의 사진을 전부 타이포그래피 그래픽 카드로 교체하는 스크립트.

- 워드프레스의 모든 글(발행글+임시글)을 순회하며 대표이미지(featured image)를
  auto_publish.py와 동일한 방식의 그래픽 카드로 교체합니다.
- 본문 안에 남아있는 <img> 태그(주로 Blogger 이관 글에 포함된 원본 사진)도
  함께 제거합니다 (config.py의 STRIP_BODY_IMAGES로 끄고 켤 수 있음).
- 이미 처리한 글은 regenerated_posts.json에 기록해서, 중간에 멈춰도 다시
  실행하면 이어서 처리합니다.

실행: python regenerate_images.py
"""

import base64
import json
import os
import re
import time

import requests

import config
from auto_publish import generate_typography_card

PROCESSED_FILE = "regenerated_posts.json"


def wp_auth_header():
    token = base64.b64encode(f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def load_processed():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_processed(ids):
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f, ensure_ascii=False, indent=2)


def fetch_all_posts():
    """전체 글(발행글+임시글) 목록을 카테고리 정보 포함해서 가져온다."""
    base_params = {"per_page": 50, "status": "publish,draft", "_embed": "wp:term"}
    resp = requests.get(f"{config.WP_URL}/wp-json/wp/v2/posts", headers=wp_auth_header(),
                         params={**base_params, "page": 1}, timeout=20)
    resp.raise_for_status()
    posts = resp.json()
    total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))

    for page in range(2, total_pages + 1):
        resp = requests.get(f"{config.WP_URL}/wp-json/wp/v2/posts", headers=wp_auth_header(),
                             params={**base_params, "page": page}, timeout=20)
        resp.raise_for_status()
        posts.extend(resp.json())
        time.sleep(0.5)

    return posts


def get_category_name(post):
    try:
        terms = post.get("_embedded", {}).get("wp:term", [[]])[0]
        if terms:
            return terms[0]["name"]
    except Exception:
        pass
    return config.DEFAULT_CATEGORY


def derive_label(title_html):
    """제목에서 HTML 태그/엔티티를 정리해서 카드에 쓸 짧은 문구로 만든다."""
    text = re.sub(r"<[^>]+>", "", title_html)
    entities = {"&#8217;": "'", "&#8216;": "'", "&#8220;": '"', "&#8221;": '"', "&amp;": "&"}
    for code, char in entities.items():
        text = text.replace(code, char)
    text = re.sub(r"&\w+;", "", text)
    text = re.sub(r"^\[.*?\]\s*", "", text)  # "[K-POP] " 같은 접두어 제거
    return text.strip()


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


def update_post(post_id, media_id, new_content=None):
    payload = {"featured_media": media_id}
    if new_content is not None:
        payload["content"] = new_content
    resp = requests.post(f"{config.WP_URL}/wp-json/wp/v2/posts/{post_id}",
                          headers=wp_auth_header(), json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()


def delete_media(media_id):
    """기존 대표이미지를 완전히 삭제해서 디스크 공간을 확보한다."""
    if not media_id:
        return
    try:
        requests.delete(
            f"{config.WP_URL}/wp-json/wp/v2/media/{media_id}",
            headers=wp_auth_header(),
            params={"force": "true"},
            timeout=20,
        )
    except Exception as e:
        print(f"    ⚠️ 기존 이미지(id {media_id}) 삭제 실패: {e}")


def run():
    processed = load_processed()

    print("📥 전체 글 목록을 가져오는 중...")
    posts = fetch_all_posts()
    remaining = [p for p in posts if p["id"] not in processed]
    print(f"📋 총 {len(posts)}건 중 처리 대상 {len(remaining)}건 (이미 처리됨 {len(posts) - len(remaining)}건)\n")

    done = 0
    freed_count = 0
    for i, post in enumerate(remaining, 1):
        title_text = derive_label(post["title"]["rendered"])
        category_name = get_category_name(post)
        old_media_id = post.get("featured_media") or 0
        print(f"[{i}/{len(remaining)}] {title_text}")

        try:
            # 디스크 용량이 0에 가까울 때도 진행되도록, 새 카드를 올리기 전에
            # 기존 이미지부터 먼저 지워서 공간을 확보한다 (삭제는 여유 공간이 없어도 가능).
            if getattr(config, "DELETE_OLD_FEATURED_MEDIA", False) and old_media_id:
                delete_media(old_media_id)
                freed_count += 1
                print(f"    🗑️ 기존 이미지 삭제 (용량 확보)")

            image_bytes, mime_type = generate_typography_card(category_name, title_text)
            media_id = upload_media(image_bytes, "kpop-card.png", mime_type)

            new_content = None
            if getattr(config, "STRIP_BODY_IMAGES", True):
                original_content = post.get("content", {}).get("rendered", "")
                stripped = strip_images_from_content(original_content)
                if stripped != original_content:
                    new_content = stripped

            update_post(post["id"], media_id, new_content)
            print(f"  ✔ 교체 완료 (post id {post['id']})")

            processed.add(post["id"])
            save_processed(processed)
            done += 1
            time.sleep(getattr(config, "REGENERATE_PAUSE_SECONDS", 2))
        except Exception as e:
            print(f"  → 실패: {e}")

    print(f"\n🏁 완료. 이번 실행에서 {done}건 교체, {freed_count}건 기존 이미지 삭제. (전체 {len(posts)}건 중 누적 처리 {len(processed)}건)")


if __name__ == "__main__":
    run()
