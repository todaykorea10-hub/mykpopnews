# config_base.py — API 키 등 비밀값이 전혀 없는 공통 설정입니다.
# 이 파일은 깃허브에 올려도 안전합니다 (실제 config.py가 이 파일을 불러다 씁니다).

# ── Gemini 모델 ──
GEMINI_MODEL = "gemini-3.5-flash-lite"

# ── 검색 소스 켜고 끄기 (비밀값 아님, 토글만) ──
ENABLE_NAVER_SEARCH = False
ENABLE_DAUM_SEARCH = False

# ── 그룹별 별칭 (검색 키워드 생성 + 그룹 이미지 매칭에 공용으로 사용) ──
GROUP_ALIASES = {
    "BTS": ["방탄소년단", "BTS"],
    "BLACKPINK": ["블랙핑크", "BLACKPINK"],
    "SEVENTEEN": ["세븐틴", "SEVENTEEN"],
    "Stray Kids": ["스트레이키즈", "Stray Kids"],
    "TWICE": ["트와이스", "TWICE"],
    "aespa": ["에스파", "aespa"],
    "IVE": ["아이브", "IVE"],
    "ATEEZ": ["에이티즈", "ATEEZ"],
    "ILLIT": ["아일릿", "ILLIT"],
    "ENHYPEN": ["엔하이픈", "ENHYPEN"],
    "TXT": ["투모로우바이투게더", "TXT", "TOMORROW X TOGETHER"],
    "ZEROBASEONE": ["제로베이스원", "ZEROBASEONE"],
    "RIIZE": ["라이즈", "RIIZE"],
    "BOYNEXTDOOR": ["보이넥스트도어", "BOYNEXTDOOR"],
    "TREASURE": ["트레저", "TREASURE"],
    "NCT DREAM": ["엔시티드림", "NCT DREAM"],
    "NCT WISH": ["엔시티위시", "NCT WISH"],
    "PLAVE": ["플레이브", "PLAVE"],
    "CORTIS": ["코르티스", "CORTIS"],
    "Hearts2Hearts": ["하츠투하츠", "Hearts2Hearts"],
    "Red Velvet": ["레드벨벳", "Red Velvet"],
    "TWS": ["투어스", "TWS"],
    "(G)I-DLE": ["여자아이들", "(G)I-DLE"],
    "NEXZ": ["넥스지", "NEXZ"],
    "KISS OF LIFE": ["키스오브라이프", "KISS OF LIFE"],
    "RESCENE": ["리센느", "RESCENE"],
    "MEOVV": ["미야오", "MEOVV"],
    "izna": ["이즈나", "izna"],
}
RECENCY_DAYS = 1

# ── K-pop 관련성 검증 ──
GENERIC_KPOP_TERMS = [
    "K-pop", "K-POP", "케이팝", "아이돌 그룹", "걸그룹", "보이그룹",
    "빌보드", "뮤직뱅크", "엠카운트다운", "인기가요", "쇼챔피언", "가요대전",
    "컴백 무대", "월드투어",
]

# ── 그룹별 사전 제작 이미지 ──
ENABLE_GROUP_IMAGES = True
GROUP_IMAGES_FILE = "group_images.json"
GROUP_IMAGE_SELECTION = "random"

# ── 콘텐츠 언어 ──
CONTENT_LANGUAGE = "en"

# ── 발행 정책 ──
MAX_POSTS_PER_RUN = 5
SPREAD_MINUTES = 60
SIMILARITY_THRESHOLD = 0.3
DEFAULT_CATEGORY = "Chart"
POST_STATUS = "publish"

# ── 자동 반복 실행 ──
RUN_CONTINUOUSLY = False
MIN_INTERVAL_MINUTES = 60
MAX_INTERVAL_MINUTES = 120

# ── Blogger 이관 ──
BLOGGER_BLOG_URL = "https://howto9988.blogspot.com"
IMPORT_POST_STATUS = "draft"
MAX_IMPORT_POSTS_PER_RUN = 20
MIGRATE_BATCH_PAUSE_SECONDS = 15
DEFAULT_IMPORT_CATEGORY = "이전글"
MIGRATE_SINCE_DATE = None
MIGRATE_UNTIL_DATE = None

# ── 기존 사진 일괄 교체 ──
STRIP_BODY_IMAGES = True
REGENERATE_PAUSE_SECONDS = 2
DELETE_OLD_FEATURED_MEDIA = False

# ── 고아 미디어 정리 ──
DRY_RUN = True
CLEANUP_PAUSE_SECONDS = 0.5
