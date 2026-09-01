"""
그룹별로 미리 만들어둔 이미지를 워드프레스에 한 번만 업로드하고,
그 결과(media ID)를 group_images.json에 저장하는 스크립트.

사용법:
1) 이 스크립트와 같은 폴더에 "group_images" 폴더를 만들고, 그 안에
   config.py의 GROUP_ALIASES 키와 정확히 같은 이름의 하위 폴더를 만든 뒤
   이미지를 넣습니다. 예:

   group_images/
     BTS/
       1.jpg
       2.jpg
       ...
     BLACKPINK/
       1.jpg
       2.jpg

2) python upload_group_images.py 실행

3) 이미 업로드된 파일은 건너뛰고, 새로 추가된 파일만 업로드합니다
   (같은 파일명을 다시 넣어도 중복 업로드되지 않습니다).

실행 후 auto_publish.py가 자동으로 group_images.json을 읽어서,
해당 그룹 기사가 나올 때마다 새로 만들지 않고 이 중 하나를 재사용합니다.
"""

import base64
import json
import os

import requests

import config

LOCAL_FOLDER = "group_images"
MAPPING_FILE = config.GROUP_IMAGES_FILE
UPLOADED_LOG_FILE = "group_images_uploaded.json"


def wp_auth_header():
    token = base64.b64encode(f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def upload_media(image_bytes, filename, mime_type):
    resp = requests.post(
        f"{config.WP_URL}/wp-json/wp/v2/media",
        headers={**wp_auth_header(), "Content-Disposition": f"attachment; filename={filename}", "Content-Type": mime_type},
        data=image_bytes,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def guess_mime(filename):
    ext = filename.lower().rsplit(".", 1)[-1]
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp",
    }.get(ext, "image/jpeg")


def run():
    if not os.path.isdir(LOCAL_FOLDER):
        print(f"❌ '{LOCAL_FOLDER}' 폴더가 없습니다. 이 스크립트와 같은 위치에 만들어주세요.")
        return

    group_images = load_json(MAPPING_FILE, {})
    uploaded_log = load_json(UPLOADED_LOG_FILE, {})  # {"BTS/1.jpg": media_id, ...}

    valid_groups = set(config.GROUP_ALIASES.keys())
    total_new = 0

    for group_name in sorted(os.listdir(LOCAL_FOLDER)):
        group_path = os.path.join(LOCAL_FOLDER, group_name)
        if not os.path.isdir(group_path):
            continue
        if group_name not in valid_groups:
            print(f"⚠️  '{group_name}' 폴더는 config.py의 GROUP_ALIASES에 없는 이름입니다. "
                  f"철자를 맞추거나 GROUP_ALIASES에 추가해주세요. (건너뜀)")
            continue

        group_images.setdefault(group_name, [])
        print(f"\n📁 {group_name}")

        for filename in sorted(os.listdir(group_path)):
            file_key = f"{group_name}/{filename}"
            file_path = os.path.join(group_path, filename)
            if not os.path.isfile(file_path):
                continue
            if file_key in uploaded_log:
                print(f"  - {filename} (이미 업로드됨, 건너뜀)")
                continue

            try:
                with open(file_path, "rb") as f:
                    image_bytes = f.read()
                media_id = upload_media(image_bytes, filename, guess_mime(filename))
                uploaded_log[file_key] = media_id
                group_images[group_name].append(media_id)
                total_new += 1
                print(f"  ✔ {filename} → media id {media_id}")
            except Exception as e:
                print(f"  → {filename} 업로드 실패: {e}")

    save_json(MAPPING_FILE, group_images)
    save_json(UPLOADED_LOG_FILE, uploaded_log)

    print(f"\n🏁 완료. 새로 업로드된 이미지 {total_new}장.")
    print(f"   그룹별 보유 이미지 수: " + ", ".join(f"{k}={len(v)}" for k, v in group_images.items() if v))


if __name__ == "__main__":
    run()
