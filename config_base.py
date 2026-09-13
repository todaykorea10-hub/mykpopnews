# config_base.py — API 키 등 비밀값이 전혀 없는 공통 설정입니다.
# 이 파일은 깃허브에 올려도 안전합니다 (실제 config.py가 이 파일을 불러다 씁니다).

# ── Gemini 모델 ──
GEMINI_MODEL = "gemini-3.1-flash-lite"  # 기사 재작성용 텍스트 모델. Gemini 모델 세대교체가 잦으니, 404(모델 지원 종료) 오류가 뜨면 그 에러 메시지가 안내하는 최신 모델명으로 바로 교체하세요

# ── 검색 소스 켜고 끄기 (비밀값 아님, 토글만) ──
ENABLE_NAVER_SEARCH = False
ENABLE_DAUM_SEARCH = False

# ── SNS 자동 게시 켜고 끄기 (비밀값 아님, 토글만) ──
ENABLE_TWITTER_POST = False
ENABLE_INSTAGRAM_POST = False

# ── 그룹별 별칭 (검색 키워드 생성 + 그룹 이미지 매칭에 공용으로 사용) ──
# 키는 그룹 이미지 폴더명과 반드시 일치해야 합니다 (예: group_images/BTS/)
# 2026년 8월 기준 실제 활동/차트 현황을 참고해 최신 인기 그룹으로 구성
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
RECENCY_DAYS = 1  # 최근 N일 이내 뉴스만 검색
DEDUP_WINDOW_DAYS = 5   # 최근 N일 이내 발행된 제목과만 유사도 비교

# ── K-pop 관련성 검증: 제목에 그룹명이 없어도 이 용어 중 하나가 있으면 통과 ──
GENERIC_KPOP_TERMS = [
    "K-pop", "K-POP", "케이팝", "아이돌 그룹", "걸그룹", "보이그룹",
    "빌보드", "뮤직뱅크", "엠카운트다운", "인기가요", "쇼챔피언", "가요대전",
    "컴백 무대", "월드투어",
]

# ── 그룹별 사전 제작 이미지 (하드 용량 절약용) ──
ENABLE_GROUP_IMAGES = True
GROUP_IMAGES_FILE = "group_images.json"
GROUP_IMAGE_SELECTION = "random"  # "random" 또는 "sequential"

# ── 콘텐츠 언어 ──
# "en"이면 영어로 번역/재작성 (기존 Blogger 자동화와 동일한 글로벌 팬 타겟 방식)
# "ko"면 한국어 그대로 재작성
CONTENT_LANGUAGE = "en"

# ── 발행 정책 ──
MAX_POSTS_PER_RUN = 5          # 실행 1회당 최대 발행 건수
SPREAD_MINUTES = 60            # 이번 실행에서 발행할 글들을 이 시간(분) 안에 나눠서 게시
SIMILARITY_THRESHOLD = 0.3     # 제목 유사도가 이 값 이상이면 중복으로 간주 (0~1)
DEFAULT_CATEGORY = "Chart"     # AI가 카테고리를 못 정하면 사용할 기본 카테고리
POST_STATUS = "publish"        # "draft" 로 바꾸면 발행 전 검수 가능

# ── 자동 반복 실행 (로컬 PC에서 run.bat으로 돌릴 때만 의미 있음) ──
# 깃허브 액션으로 돌릴 때는 워크플로우의 cron 스케줄이 반복을 담당하므로 False로 둡니다.
RUN_CONTINUOUSLY = False
MIN_INTERVAL_MINUTES = 60
MAX_INTERVAL_MINUTES = 120

# ── Blogger 이관 (migrate_from_blogger.py 전용) ──
BLOGGER_BLOG_URL = "https://howto9988.blogspot.com"
IMPORT_POST_STATUS = "draft"
MAX_IMPORT_POSTS_PER_RUN = 20
MIGRATE_BATCH_PAUSE_SECONDS = 15
DEFAULT_IMPORT_CATEGORY = "이전글"
MIGRATE_SINCE_DATE = None
MIGRATE_UNTIL_DATE = None

# ── 기존 사진 일괄 교체 (regenerate_images.py 전용) ──
STRIP_BODY_IMAGES = True
REGENERATE_PAUSE_SECONDS = 2
DELETE_OLD_FEATURED_MEDIA = False

# ── 고아 미디어 정리 (cleanup_orphaned_media.py 전용) ──
DRY_RUN = True
CLEANUP_PAUSE_SECONDS = 0.5
