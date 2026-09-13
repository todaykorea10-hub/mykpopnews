import os

lines = [
    "from config_base import *",
    "import os",
    "",
    'WP_URL = os.environ["WP_URL"]',
    'WP_USERNAME = os.environ["WP_USERNAME"]',
    'WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]',
    "",
    'GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]',
    "",
    'NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")',
    'NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")',
    'KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")',
    "",
    'TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY", "")',
    'TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET", "")',
    'TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN", "")',
    'TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")',
    'ENABLE_TWITTER_POST = bool(TWITTER_API_KEY)',
    "",
    'INSTAGRAM_BUSINESS_ID = os.environ.get("INSTAGRAM_BUSINESS_ID", "")',
    'INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")',
    'ENABLE_INSTAGRAM_POST = bool(INSTAGRAM_BUSINESS_ID)',
]

with open("config.py", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print("config.py 생성 완료")
