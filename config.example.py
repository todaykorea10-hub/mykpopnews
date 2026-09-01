# config.py 로 복사한 후 실제 값을 채워넣으세요.
# 이 파일(config.py)은 절대 깃허브 등에 올리지 마세요.
# (나머지 비밀 아닌 설정은 config_base.py에 있고, 여기서 자동으로 불러옵니다)

from config_base import *

# ── 워드프레스 (Cafe24) ──
WP_URL = "https://your-domain.com"          # 예: https://mykpopnews.kr
WP_USERNAME = "admin"                        # 워드프레스 관리자 아이디
WP_APP_PASSWORD = "xxxx xxxx xxxx xxxx"      # 워드프레스 관리자 > 사용자 > 프로필 > Application Passwords 에서 발급

# ── Gemini API (google-genai SDK 사용) ──
GEMINI_API_KEY = "your-gemini-api-key"       # https://aistudio.google.com/apikey 에서 발급

# ── 네이버 뉴스 검색 (공식 검색 API, developers.naver.com에서 예전에 발급받은 키만 작동) ──
NAVER_CLIENT_ID = "your-naver-client-id"
NAVER_CLIENT_SECRET = "your-naver-client-secret"

# ── 다음(카카오) 뉴스 검색 ──
KAKAO_REST_API_KEY = "your-kakao-rest-api-key"
