"""
그룹별 이미지를 워드프레스에 업로드하고 group_images.json에 '추가(병합)'한다.

기존 방식과 달리 group_images.json을 덮어쓰지 않고, 이미 있는 media ID는 그대로 둔 채
새로 올린 이미지의 ID만 이어 붙인다. 이미 업로드한 파일은 건너뛴다
(group_images_uploaded.json에 '그룹/파일명'을 기록).

폴더 구조:
  group_images/
    BTS/      01.png 02.png ...
    BLACKPINK/ ...
폴더 이름은 config.GROUP_ALIASES의 그룹 키(BTS 등)와 똑같이 써야 한다.

실행:  python upload_group_images.py
끝나면 group_images.json / group_images_uploaded.json 을 GitHub에 push 해야
GitHub Actions(클라우드)에서도 새 이미지가 반영된다.
"""

import json
import mimetypes
import os

import requests

import config
from auto_publish import wp_auth_header

IMAGES_DIR = "group_images"
UPLOADED_LOG = "group_images_uploaded.json"
EXTS = (".png", ".jpg", ".jpeg", ".webp")


def load(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def main():
    group_images = load(config.GROUP_IMAGES_FILE, {})
    uploaded = set(load(UPLOADED_LOG, []))

    if not os.path.isdir(IMAGES_DIR):
        print(f"'{IMAGES_DIR}' 폴더가 없습니다.")
        return

    added = 0
    for group in sorted(os.listdir(IMAGES_DIR)):
        gdir = os.path.join(IMAGES_DIR, group)
        if not os.path.isdir(gdir):
            continue
        if group not in config.GROUP_ALIASES:
            print(f"⚠️ 폴더 '{group}'는 GROUP_ALIASES에 없는 이름이라 건너뜀")
            continue
        for fname in sorted(os.listdir(gdir)):
            if not fname.lower().endswith(EXTS):
                continue
            key = f"{group}/{fname}"
            if key in uploaded:
                continue
            mime = mimetypes.guess_type(fname)[0] or "image/png"
            with open(os.path.join(gdir, fname), "rb") as f:
                data = f.read()
            resp = requests.post(
                f"{config.WP_URL}/wp-json/wp/v2/media",
                headers={
                    **wp_auth_header(),
                    "Content-Disposition": f'attachment; filename="{group}-{fname}"',
                    "Content-Type": mime,
                },
                data=data,
                timeout=60,
            )
            if resp.status_code not in (200, 201):
                print(f"❌ {key} 업로드 실패: {resp.status_code} {resp.text[:120]}")
                continue
            media_id = resp.json()["id"]
            group_images.setdefault(group, [])
            if media_id not in group_images[group]:
                group_images[group].append(media_id)
            uploaded.add(key)
            added += 1
            print(f"✔ {key} → media ID {media_id}")

    with open(config.GROUP_IMAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(group_images, f, ensure_ascii=False, indent=2)
    with open(UPLOADED_LOG, "w", encoding="utf-8") as f:
        json.dump(sorted(uploaded), f, ensure_ascii=False, indent=2)

    print(f"\n새로 추가 {added}장. 그룹별 현재 개수: "
          + ", ".join(f"{k}:{len(v)}" for k, v in group_images.items()))


if __name__ == "__main__":
    main()
