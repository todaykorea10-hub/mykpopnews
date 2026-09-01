"""
어떤 글/페이지에도 연결되지 않은 "고아 미디어 파일"을 찾아서 삭제하는 스크립트.

배경: regenerate_images.py는 대표이미지(featured_media) 1장만 교체·삭제합니다.
하지만 Blogger 이관 글들은 본문 안에 사진이 여러 장 들어있는 경우가 많아서,
본문에서 <img> 태그만 지워도 그 사진 "파일" 자체(미디어 라이브러리 항목)는
그대로 남아 디스크 용량을 계속 차지합니다. 이 스크립트는 그런 파일들을
전부 찾아서 한 번에 정리합니다.

동작 방식:
1) 전체 미디어 라이브러리 목록 수집
2) 전체 글/페이지의 본문을 스캔해서 "실제로 참조되는" 미디어를 식별
   (본문 안의 wp-image-123 클래스, 파일명 매칭 + 대표이미지로 지정된 것)
3) 어느 쪽에도 해당하지 않는 미디어만 "고아"로 분류
4) DRY_RUN=True(기본값)면 삭제하지 않고 목록/용량 추정치만 보여줍니다.
   확인 후 config.py에서 DRY_RUN=False로 바꾸면 실제로 삭제합니다.

실행: python cleanup_orphaned_media.py
"""

import base64
import json
import os
import re
import time

import requests

import config

PROCESSED_FILE = "cleanup_processed.json"


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


def fetch_all(endpoint, fields):
    """/wp-json/wp/v2/{endpoint} 전체를 페이지 단위로 수집 (필요한 필드만 요청해서 가볍게)."""
    items = []
    params = {"per_page": 100, "page": 1, "_fields": ",".join(fields)}
    if endpoint == "posts":
        params["status"] = "publish,draft"

    resp = requests.get(f"{config.WP_URL}/wp-json/wp/v2/{endpoint}", headers=wp_auth_header(), params=params, timeout=30)
    resp.raise_for_status()
    items.extend(resp.json())
    total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))

    for page in range(2, total_pages + 1):
        params["page"] = page
        resp = requests.get(f"{config.WP_URL}/wp-json/wp/v2/{endpoint}", headers=wp_auth_header(), params=params, timeout=30)
        resp.raise_for_status()
        items.extend(resp.json())
        time.sleep(0.3)

    return items


def base_filename(url):
    """URL에서 워드프레스 사이즈 접미사(-900x620 등)를 뗀 원본 파일명만 추출."""
    name = url.rsplit("/", 1)[-1]
    return re.sub(r"-\d+x\d+(?=\.\w+$)", "", name)


def find_referenced_media(posts_and_pages, media_items):
    """본문 텍스트를 스캔해서 실제로 쓰이고 있는 미디어 id 집합을 만든다."""
    referenced_ids = set()

    # wp-image-123 클래스로 직접 참조되는 경우 (가장 확실한 신호)
    id_pattern = re.compile(r"wp-image-(\d+)")
    for item in posts_and_pages:
        content = item.get("content", {}).get("rendered", "") or ""
        for m in id_pattern.finditer(content):
            referenced_ids.add(int(m.group(1)))
        fm = item.get("featured_media")
        if fm:
            referenced_ids.add(fm)

    # 파일명 기준으로도 한 번 더 매칭 (wp-image 클래스가 없는 경우 대비)
    all_content = "\n".join((item.get("content", {}).get("rendered", "") or "") for item in posts_and_pages)
    for media in media_items:
        if media["id"] in referenced_ids:
            continue
        src = media.get("source_url", "")
        if src and base_filename(src) in all_content:
            referenced_ids.add(media["id"])

    return referenced_ids


def delete_media(media_id):
    resp = requests.delete(
        f"{config.WP_URL}/wp-json/wp/v2/media/{media_id}",
        headers=wp_auth_header(),
        params={"force": "true"},
        timeout=20,
    )
    resp.raise_for_status()


def run():
    processed = load_processed()

    print("📥 전체 글/페이지를 가져오는 중...")
    posts = fetch_all("posts", ["id", "content", "featured_media"])
    pages = fetch_all("pages", ["id", "content", "featured_media"])
    posts_and_pages = posts + pages
    print(f"  → 글 {len(posts)}건, 페이지 {len(pages)}건")

    print("📥 전체 미디어 라이브러리를 가져오는 중...")
    media_items = fetch_all("media", ["id", "source_url", "media_details"])
    print(f"  → 미디어 {len(media_items)}건\n")

    print("🔍 실제로 사용 중인 미디어를 분석하는 중...")
    referenced_ids = find_referenced_media(posts_and_pages, media_items)

    orphaned = [m for m in media_items if m["id"] not in referenced_ids and m["id"] not in processed]

    est_total_kb = 0
    for m in orphaned:
        try:
            est_total_kb += m.get("media_details", {}).get("filesize", 0) / 1024
        except Exception:
            pass

    print(f"\n📊 결과: 전체 미디어 {len(media_items)}건 중 고아 미디어(사용 안 함) {len(orphaned)}건")
    if est_total_kb:
        print(f"    예상 절약 용량: 약 {est_total_kb / 1024:.1f} MB (파일 크기 정보가 있는 항목 기준)")

    if getattr(config, "DRY_RUN", True):
        print("\n⚠️  DRY_RUN = True 상태라 실제로 삭제하지 않았습니다.")
        print("    결과가 예상과 맞으면 config.py에서 DRY_RUN = False로 바꾸고 다시 실행하세요.")
        return

    print(f"\n🗑️  {len(orphaned)}건 삭제를 시작합니다...")
    deleted = 0
    for i, m in enumerate(orphaned, 1):
        try:
            delete_media(m["id"])
            processed.add(m["id"])
            deleted += 1
            if i % 20 == 0:
                save_processed(processed)
                print(f"  [{i}/{len(orphaned)}] 진행 중...")
            time.sleep(getattr(config, "CLEANUP_PAUSE_SECONDS", 0.5))
        except Exception as e:
            print(f"  → id {m['id']} 삭제 실패: {e}")

    save_processed(processed)
    print(f"\n🏁 완료. {deleted}건 삭제됨.")


if __name__ == "__main__":
    run()
