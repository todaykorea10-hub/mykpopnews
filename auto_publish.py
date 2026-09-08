"""
K-pop 뉴스 자동 발행 파이프라인 (워드프레스용)

기존에 검증된 블로거 자동화 스크립트(blogger_auto.py)의 핵심 로직을 이식했습니다:
- google-genai 공식 SDK 사용 (raw REST 호출 대신 — 계정별 키 형식 차이에 안전)
- 아티스트/트렌드 키워드를 넓게 조합한 구글 뉴스 검색
- 제목 유사도 기반 중복 방지 (게시 이력 누적)
- 발행 간 무작위 대기로 스팸 신호 방지

흐름:
1) 다수 키워드로 구글 뉴스 RSS 검색 → 리다이렉트 URL을 실제 언론사 URL로 변환
2) 이미 다룬 기사(제목 유사도)와 중복 제거
3) Gemini로 재작성 (제목/본문/카테고리/메타설명/카드문구)
4) 연예인 사진을 전혀 쓰지 않는 타이포그래피 그래픽 카드를 자동 생성
   (저작권·초상권 리스크 원천 차단)
5) 워드프레스 REST API로 업로드 + 발행

실행: python auto_publish.py
config.example.py 를 config.py 로 복사하고 값을 채운 뒤 사용하세요.
"""

import base64
import difflib
import io
import json
import os
import random
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from google import genai
from googlenewsdecoder import gnewsdecoder

import config
from sns_post import post_to_twitter, post_to_instagram

POSTED_LINKS_FILE = "posted_links.json"
POSTED_TITLES_FILE = "posted_titles.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
}

VIDEO_DOMAINS = ("youtube.com", "youtu.be", "m.youtube.com")

NON_ARTICLE_TITLE_PATTERNS = re.compile(
    r"\[K-Fancam\]|\[K-Choreo|Facecam|얼빡직캠|\[Playlist\]|Music Bank\]|"
    r"포토슬라이드|포토\s?갤러리|화보\s?슬라이드|슬라이드쇼|\[\w*포토\]|\[화보\]|"
    r"Weverse\s.*(Image|Media)|커뮤니티의?\s?투고|コミュニティの投稿",
    re.IGNORECASE,
)

genai_client = genai.Client(api_key=config.GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# 게시 이력 (중복 방지)
# ---------------------------------------------------------------------------

def load_json_set(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def load_json_list(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_posted_link(link):
    links = load_json_set(POSTED_LINKS_FILE)
    links.add(link)
    with open(POSTED_LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(links), f, ensure_ascii=False, indent=2)


def save_posted_title(title):
    titles = load_json_list(POSTED_TITLES_FILE)
    titles.append(title)
    titles = titles[-500:]  # 무한 증가 방지
    with open(POSTED_TITLES_FILE, "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False, indent=2)


def is_similar_to_existing(title):
    for existing in load_json_list(POSTED_TITLES_FILE):
        ratio = difflib.SequenceMatcher(None, title.lower(), existing.lower()).ratio()
        if ratio >= config.SIMILARITY_THRESHOLD:
            return True
    return False


def get_recent_titles_for_dedup(limit=15):
    titles = load_json_list(POSTED_TITLES_FILE)
    return titles[-limit:] if titles else []


# ---------------------------------------------------------------------------
# 1. 수집: 넓은 키워드 조합으로 구글 뉴스 검색
# ---------------------------------------------------------------------------

def build_search_keywords():
    recency = f"when:{config.RECENCY_DAYS}d"
    keywords = []
    for aliases in config.GROUP_ALIASES.values():
        keywords.extend(aliases)
    return [f"{kw} {recency}" for kw in keywords]


def detect_group(text):
    """제목/원문 텍스트에서 어떤 그룹을 다루는 기사인지 감지 (그룹 이미지 매칭용)."""
    if not text:
        return None
    lowered = text.lower()
    for group_key, aliases in config.GROUP_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lowered:
                return group_key
    return None


def resolve_real_url(google_news_url):
    """구글 뉴스 RSS의 리다이렉트 URL을 실제 언론사 URL로 변환. 실패 시 원래 URL 반환."""
    try:
        result = gnewsdecoder(google_news_url, interval=1)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception as e:
        print(f"  ⚠️ 링크 디코딩 실패: {e}")
    return google_news_url


def is_video_link(url):
    domain = urlparse(url).netloc.lower()
    return any(vd in domain for vd in VIDEO_DOMAINS)


def is_likely_non_article(title):
    return bool(NON_ARTICLE_TITLE_PATTERNS.search(title))


def is_kpop_relevant(title):
    """제목에 그룹명 또는 K-pop 관련 일반 용어가 전혀 없으면 무관한 기사로 간주."""
    if detect_group(title):
        return True
    lowered = title.lower()
    return any(term.lower() in lowered for term in config.GENERIC_KPOP_TERMS)


def fetch_google_news_candidates(count_per_keyword=15):
    import xml.etree.ElementTree as ET
    import urllib.parse as up

    keywords = build_search_keywords()
    seen_links = set()
    news_list = []

    for i, keyword in enumerate(keywords):
        encoded = up.quote(keyword)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:count_per_keyword]:
                title = item.find("title").text or ""
                link = item.find("link").text or ""
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                news_list.append({"title": re.sub(r"\s+-\s+[^-]+$", "", title).strip(), "link": link})
        except Exception as e:
            print(f"  ⚠️ [Google] '{keyword}' 검색 중 오류: {e}")

        if i < len(keywords) - 1:
            time.sleep(random.uniform(1.5, 3))

    return news_list


def strip_html_tags(text):
    return re.sub(r"<[^>]+>", "", text or "")


def fetch_naver_news_candidates(count_per_keyword=10):
    """네이버 공식 검색 API(뉴스)를 이용한 검색. Client ID/Secret 필요.
    developers.naver.com(구버전)에서 예전에 발급받은 키는 이관 유예 기간
    (2027년 6월까지) 동안 openapi.naver.com + 구버전 헤더로 계속 정상 작동한다.
    NCP에서 새로 발급받은 키는 이 방식으로 인증되지 않으니, 반드시
    developers.naver.com에서 예전에 발급받은 키를 사용해야 한다."""
    if not getattr(config, "ENABLE_NAVER_SEARCH", False):
        return []

    news_list = []
    seen_links = set()
    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }
    keywords = []
    for aliases in config.GROUP_ALIASES.values():
        keywords.extend(aliases)

    for i, keyword in enumerate(keywords):
        for attempt in range(2):  # 429면 한 번 더 재시도
            try:
                resp = requests.get(
                    "https://openapi.naver.com/v1/search/news.json",
                    headers=headers,
                    params={"query": keyword, "display": count_per_keyword, "sort": "date"},
                    timeout=10,
                )
                if resp.status_code == 429 and attempt == 0:
                    time.sleep(2)
                    continue
                if resp.status_code != 200:
                    print(f"  ⚠️ [네이버] '{keyword}' 검색 실패: {resp.status_code} {resp.text[:150]}")
                    break
                for item in resp.json().get("items", []):
                    link = item.get("originallink") or item.get("link")
                    if not link or link in seen_links:
                        continue
                    seen_links.add(link)
                    title = strip_html_tags(item.get("title", ""))
                    news_list.append({"title": title.strip(), "link": link})
                break
            except Exception as e:
                print(f"  ⚠️ [네이버] '{keyword}' 검색 중 오류: {e}")
                break

        if i < len(keywords) - 1:
            time.sleep(random.uniform(1, 1.5))

    return news_list


def fetch_daum_news_candidates(count_per_keyword=50):
    """카카오(다음) 웹 검색 API를 다음뉴스 도메인으로 필터링해서 사용.
    다음은 별도 뉴스 전용 검색 API를 제공하지 않아 웹 검색으로 대체합니다.
    카카오 API의 요청당 최대치(50)로 가져와서 daum.net 도메인이 걸릴 확률을 높인다."""
    if not getattr(config, "ENABLE_DAUM_SEARCH", False):
        return []

    news_list = []
    seen_links = set()
    headers = {"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"}
    keywords = []
    for aliases in config.GROUP_ALIASES.values():
        keywords.extend(aliases)

    for i, keyword in enumerate(keywords):
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/search/web",
                headers=headers,
                params={"query": f"{keyword} 뉴스", "size": count_per_keyword},
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"  ⚠️ [다음] '{keyword}' 검색 실패: {resp.status_code} {resp.text[:150]}")
                continue
            for doc in resp.json().get("documents", []):
                link = doc.get("url", "")
                if not link or "daum.net" not in link:
                    continue  # 다음뉴스 도메인만 채택 (일반 웹검색 결과 중 필터링)
                if link in seen_links:
                    continue
                seen_links.add(link)
                title = strip_html_tags(doc.get("title", ""))
                news_list.append({"title": title.strip(), "link": link})
        except Exception as e:
            print(f"  ⚠️ [다음] '{keyword}' 검색 중 오류: {e}")

        if i < len(keywords) - 1:
            time.sleep(random.uniform(0.5, 1))

    return news_list


def fetch_news_candidates(count_per_keyword=15):
    """구글/네이버/다음 뉴스를 모두 모아 링크 기준으로 중복 제거."""
    combined = []
    seen_links = set()

    for source_name, fetch_fn in (
        ("Google", lambda: fetch_google_news_candidates(count_per_keyword)),
        ("Naver", lambda: fetch_naver_news_candidates(count_per_keyword)),
        ("Daum", lambda: fetch_daum_news_candidates(50)),
    ):
        try:
            results = fetch_fn()
        except Exception as e:
            print(f"  ⚠️ [{source_name}] 검색 전체 실패: {e}")
            results = []
        added = 0
        for item in results:
            if item["link"] in seen_links:
                continue
            seen_links.add(item["link"])
            combined.append(item)
            added += 1
        print(f"  📡 {source_name}: {added}건 추가")

    return combined


def fetch_full_text(url, max_chars=4000):
    try:
        resp = requests.get(url, timeout=8, headers=HEADERS)
        soup = BeautifulSoup(resp.text, "html.parser")
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = "\n".join(p for p in paragraphs if len(p) > 30)
        return text[:max_chars]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 2. Gemini 재작성 (google-genai SDK 사용)
# ---------------------------------------------------------------------------

# ── 콘텐츠 다양성: 매 글마다 무작위로 다른 "관점"과 "구조"를 강제해서
#    비슷한 톤으로 반복되지 않도록 함 ──
ANGLE_STYLES = [
    "Fan community reaction angle: focus heavily on how fans (in Korea and globally) are reacting online, describing the general mood (not real usernames or invented quotes), and why this news matters emotionally to the fanbase.",
    "Industry & business angle: analyze this news in terms of chart performance, brand value, agency strategy, and what it signals about the group's/artist's trajectory in the K-pop industry.",
    "Career timeline angle: place this news in the context of the artist's/group's career so far — key past milestones, how this moment compares, and what it sets up next.",
    "Comparative angle: compare this news/moment to a similar past event from the same artist or a peer group in the industry, highlighting what's different this time.",
    "Q&A/explainer angle: structure the piece around 4-5 questions global fans would naturally ask about this news, answering each in detail.",
    "Behind-the-scenes/context angle: focus on the lesser-known context — preparation, production, or circumstances behind this news — rather than just the headline event.",
    "Data/ranking angle: where relevant, frame the piece around numbers — chart rankings, streaming/view counts, ticket sales, award tallies — and what they mean.",
]

STRUCTURE_STYLES = [
    "Use standard prose paragraphs under each <h3> subtitle.",
    "Include one short HTML bullet list (<ul><li>) summarizing key facts or a timeline, in addition to prose paragraphs.",
    "Include one simple HTML table (<table>) comparing before/after, or two related data points, in addition to prose paragraphs.",
    "Open with a short 1-2 sentence italicized (<i>) hook/teaser before the first subtitle, then continue with prose paragraphs.",
    "Include a short pull-quote style callout using <blockquote> summarizing the core takeaway, in addition to prose paragraphs.",
]


def rewrite_with_gemini(title, raw_text, source_name, recent_titles):
    angle = random.choice(ANGLE_STYLES)
    structure = random.choice(STRUCTURE_STYLES)

    recent_block = ""
    if recent_titles:
        joined = "\n".join(f"- {t}" for t in recent_titles)
        if config.CONTENT_LANGUAGE == "en":
            recent_block = (
                f"\n[Recently published titles — do NOT repeat the same angle]\n{joined}\n"
                "If today's topic overlaps with any title above, pick a different angle, "
                "focus, or specific detail so this reads as genuinely new content.\n"
            )
        else:
            recent_block = f"\n[최근 발행한 제목 목록 — 같은 각도로 반복하지 말 것]\n{joined}\n"

    if config.CONTENT_LANGUAGE == "en":
        prompt = f"""You are a K-pop news editor writing for a global English-speaking fan audience.
        Based on the Korean source info below, write an ORIGINAL, IN-DEPTH English-language article.

        CRITICAL REQUIREMENTS (this content will be reviewed for ad-network quality standards,
        so originality and depth matter a lot):
        - Target length: at least 1,000 words total. Do not pad with filler — earn the length
          through genuine added analysis, not repetition.
        - This must NOT read like a summary or translation of the source. Structure it with
          real editorial depth across these angles, each getting real substance:
          1) A strong lead paragraph stating what happened.
          2) Background/context: how this fits the artist's or group's broader career trajectory
             or K-pop industry trends.
          3) Original analysis: your own interpretation of why this matters, comparisons to
             similar past moments in K-pop, or what it signals about industry direction. Do not
             invent specific facts, statistics, or quotes not present in the source — analysis
             should be framed as interpretation ("this suggests", "this mirrors a pattern seen
             when...") rather than presented as new facts.
          4) General fan/community sentiment: describe how this type of news typically resonates
             with fandoms, in general terms — do not invent specific quotes attributed to named
             real individuals (fans, artists, or officials) who did not actually say them.
          5) A forward-looking closing on what this could mean next.
        - Keep all facts accurate to the source; only the analysis/interpretation sections should
          go beyond the raw source material, clearly framed as commentary, not fact.

        [Mandatory angle for this specific article — commit to this as the main lens throughout,
        don't just mention it in passing]
        {angle}

        [Mandatory structural element — include this in addition to the 5-part structure above]
        {structure}

        [Korean source title] {title}
        [Source outlet] {source_name}
        [Source content excerpt] {raw_text}
        {recent_block}
        [CRITICAL JSON SAFETY — your output must be valid JSON that a strict parser can read]
        - Never use straight double quotes (") inside any field's text. Use single quotes (')
          for any quoted phrase or title mentioned within the body, e.g. Jennie's new track 'Antifreeze'.
        - Do not include literal line breaks inside string values — write body_html as one
          continuous string using <p> tags to separate paragraphs, not actual newlines.

        Respond with ONLY this JSON structure (no extra text, no code fences):
        {{
          "title": "Catchy, trendy English title for global K-pop fans (under ~70 characters), reflecting the mandatory angle above rather than just restating the raw headline",
          "body_html": "Original English article, at least 1000 words, 8-12 paragraphs each wrapped in <p> tags, following the 5-part structure above with real analytical depth, plus 2-3 <h3> subheadings to break up sections, and including the mandatory structural element",
          "category": "One of: Comeback | Chart | Tour/Concert | Photoshoot/Interview | Rumor/Issue | Global Reaction",
          "slug": "short SEO-friendly URL slug, 3-6 words, lowercase, hyphen-separated, no stopwords like 'the/a/of', capturing the core topic (e.g. 'ive-liz-red-carpet-comeback')",
          "meta_description": "SEO meta description for Google search results, 140-155 characters, summarizing the article's hook in one compelling sentence (no quotes, no hashtags)",
          "card_label": "2-5 word punchy phrase for a graphic card (no photo), capturing the core topic in caps-friendly words (e.g. 'JENNIE GOES MINIMAL', 'BTS TOUR RECORD')"
        }}"""
    else:
        prompt = f"""당신은 K-pop 전문 뉴스 에디터입니다. 아래 원문 정보를 참고하여
        저작권에 문제되지 않도록 사실관계만 유지한 채 완전히 새로운 문장으로,
        광고 네트워크 심사 기준(콘텐츠 독창성·깊이)을 통과할 수 있는 수준의
        심층 기사를 작성하세요.

        필수 요건:
        - 분량: 최소 1,000단어(한글 기준 넉넉히 2,000자 이상) — 반복이 아니라
          실제 분석 내용으로 분량을 채우세요.
        - 단순 요약/번역처럼 보이면 안 됩니다. 아래 구조로 실질적인 내용을 채우세요:
          1) 핵심 사실을 담은 리드 문단
          2) 배경/맥락: 이 소식이 해당 아티스트·그룹의 커리어나 K-pop 업계 흐름에서
             어떤 의미를 갖는지
          3) 오리지널 분석: 왜 이게 중요한지에 대한 본인의 해석, 과거 유사 사례와의
             비교, 업계 방향성에 대한 시사점 (원문에 없는 사실·수치·발언을
             지어내지 말고, "이는 ~와 유사한 패턴을 보인다"처럼 해석으로 명확히
             구분해서 서술)
          4) 일반적인 팬덤 반응: 실존 인물(팬, 아티스트, 관계자)이 실제로 하지 않은
             발언을 인용구로 지어내지 말고, 이런 소식에 팬덤이 보통 어떻게
             반응하는 경향이 있는지 일반적인 서술로 설명
          5) 앞으로의 전망으로 마무리
        - 사실관계는 원문 기준으로 정확하게 유지하고, 분석/해석 부분만 원문을 넘어서는
          내용으로 채우되 반드시 "해석"임을 알 수 있게 서술하세요.

        [이 기사에 적용할 필수 관점 — 잠깐 언급만 하지 말고 기사 전체의 중심 시각으로 삼을 것]
        {angle}

        [필수 구조 요소 — 위 5단계 구조에 더해 이것도 포함할 것]
        {structure}

        [원문 제목] {title}
        [원문 출처] {source_name}
        [원문 내용 일부] {raw_text}
        {recent_block}
        [JSON 형식 안전 규칙 — 반드시 지켜야 파싱 오류가 안 남]
        - 본문 어디에도 큰따옴표(")를 직접 쓰지 마세요. 인용구나 제목을 강조할 땐
          작은따옴표(')를 쓰세요 (예: 제니의 신곡 '안티프리즈').
        - 문자열 값 안에 실제 줄바꿈을 넣지 마세요 — body_html은 <p> 태그로만
          문단을 구분하고, 하나의 이어진 문자열로 작성하세요.

        다음 JSON 형식으로만 응답하세요 (다른 텍스트나 코드블록 없이 순수 JSON만):
        {{
          "title": "재작성된 제목 (30자 내외, 클릭을 유도하되 과장 금지, 위 필수 관점을 반영)",
          "body_html": "재작성된 본문 (최소 1,000단어 분량, 문단마다 <p> 태그로 8~12문단, 위 5단계 구조를 실제 분석 내용으로 채움, 섹션 구분용 <h3> 소제목 2~3개 포함, 필수 구조 요소 포함)",
          "category": "컴백 | 차트 | 투어/공연 | 화보/인터뷰 | 루머/이슈 | 해외반응 중 하나",
          "slug": "핵심 키워드만 담은 짧은 영문 URL 슬러그, 3~6단어, 소문자, 하이픈으로 연결 (예: 'ive-liz-red-carpet-comeback')",
          "meta_description": "구글 검색결과에 노출될 SEO 요약문, 140~155자 내외로 기사의 핵심을 한 문장으로 (따옴표나 해시태그 없이)",
          "card_label": "사진 없는 그래픽 카드에 들어갈 2~5단어의 임팩트 있는 문구, 대문자로 써도 어울리게 (예: 'JENNIE GOES MINIMAL')"
        }}"""


    response = call_gemini_with_retry(config.GEMINI_MODEL, prompt)
    result = parse_gemini_json(response.text)

    if result is None:
        # 파싱 실패: JSON 형식이 깨진 응답을 한 번 더 새로 생성해서 재시도
        print("  🔁 JSON 파싱 실패, 재생성 시도...")
        response = call_gemini_with_retry(config.GEMINI_MODEL, prompt)
        result = parse_gemini_json(response.text)

    if result is None:
        raise ValueError("Gemini가 올바른 JSON을 반환하지 않았습니다 (재시도 후에도 실패).")

    result["body_html"] = strip_stray_images(result.get("body_html", ""))
    return result


def parse_gemini_json(raw_text):
    """Gemini 응답에서 JSON을 최대한 관대하게 파싱. 실패하면 None 반환."""
    match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
    if not match:
        return None
    json_text = match.group(1).strip()

    # 1차: 그대로 시도 (strict=False로 문자열 안의 raw 줄바꿈/탭 등은 허용)
    try:
        return json.loads(json_text, strict=False)
    except json.JSONDecodeError:
        pass

    # 2차: 실제 줄바꿈 문자를 공백으로 치환 후 재시도 (문자열 안팎 어디든 안전하게 무해함)
    try:
        cleaned = json_text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        return None


def call_gemini_with_retry(model, prompt, max_attempts=4):
    """429(RESOURCE_EXHAUSTED) 발생 시, 에러가 알려주는 retryDelay만큼 기다렸다가 재시도."""
    for attempt in range(1, max_attempts + 1):
        try:
            return genai_client.models.generate_content(model=model, contents=prompt)
        except Exception as e:
            msg = str(e)
            if "RESOURCE_EXHAUSTED" not in msg and "429" not in msg:
                raise
            wait_match = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)", msg)
            wait_seconds = int(wait_match.group(1)) + 2 if wait_match else 30 * attempt
            if attempt == max_attempts:
                raise
            print(f"  ⏳ Gemini 할당량 초과, {wait_seconds}초 대기 후 재시도 ({attempt}/{max_attempts})...")
            time.sleep(wait_seconds)


def strip_stray_images(html):
    """AI가 실수로 본문에 넣은 <img> 태그를 제거 (대표이미지와 중복 표시되는 것 방지)."""
    return re.sub(r"<img[^>]*>", "", html)


# ---------------------------------------------------------------------------
# 3. 이미지: 저작권/초상권 리스크 없는 타이포그래피 그래픽 카드 자동 생성
# ---------------------------------------------------------------------------

FONT_PATH = "Anton-Regular.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf"

KOREAN_FONT_PATH = "BlackHanSans-Regular.ttf"
KOREAN_FONT_URL = "https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf"

HANGUL_PATTERN = re.compile(r"[\uAC00-\uD7A3\u3131-\u318E]")


def contains_hangul(text):
    return bool(HANGUL_PATTERN.search(text or ""))


def ensure_font(path=FONT_PATH, url=FONT_URL):
    """폰트(OFL 라이선스, 재배포 자유)를 최초 1회만 다운로드해서 로컬에 캐싱."""
    if os.path.exists(path):
        return path
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception as e:
        print(f"  ⚠️ 폰트 다운로드 실패, 기본 폰트로 대체: {e}")
        return None


def pick_font_file(text):
    """텍스트에 한글이 포함되어 있으면 한글 지원 폰트로, 아니면 Anton으로."""
    if contains_hangul(text):
        return ensure_font(KOREAN_FONT_PATH, KOREAN_FONT_URL)
    return ensure_font(FONT_PATH, FONT_URL)


def wrap_text_to_width(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_typography_card(category_name, headline_text):
    """카테고리 + 핵심 문구만으로 사이트 톤에 맞는 그래픽 카드를 생성 (사진 없음)."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 900, 620
    BG = (18, 18, 31)          # --bg-base
    ACCENT_PINK = (255, 61, 119)
    ACCENT_LIME = (212, 255, 61)
    TEXT_MAIN = (243, 242, 255)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # 우측 상단 코너 액센트 (은은한 대각선 스트라이프)
    draw.polygon([(W, 0), (W, 260), (W - 260, 0)], fill=(*ACCENT_PINK, 60))
    draw.polygon([(0, H), (0, H - 180), (200, H)], fill=(*ACCENT_LIME, 45))

    font_file_label = pick_font_file(category_name)
    font_file_headline = pick_font_file(headline_text)
    font_file_watermark = FONT_PATH if os.path.exists(FONT_PATH) else ensure_font(FONT_PATH, FONT_URL)

    try:
        font_label = ImageFont.truetype(font_file_label, 34) if font_file_label else ImageFont.load_default()
        font_headline = ImageFont.truetype(font_file_headline, 74) if font_file_headline else ImageFont.load_default()
        font_watermark = ImageFont.truetype(font_file_watermark, 26) if font_file_watermark else ImageFont.load_default()
    except Exception:
        font_label = font_headline = font_watermark = ImageFont.load_default()

    margin = 60

    # 카테고리 라벨 (연두색, 대문자)
    draw.text((margin, margin), category_name.upper(), font=font_label, fill=ACCENT_LIME)

    # 핵심 헤드라인 (여러 줄로 감싸서 중앙 배치)
    max_text_width = W - margin * 2
    lines = wrap_text_to_width(draw, headline_text.upper(), font_headline, max_text_width)
    lines = lines[:4]  # 카드가 너무 길어지지 않도록 최대 4줄

    line_height = 84
    total_height = line_height * len(lines)
    y = (H - total_height) // 2 + 20
    for line in lines:
        draw.text((margin, y), line, font=font_headline, fill=TEXT_MAIN)
        y += line_height

    # 워터마크
    draw.text((margin, H - margin - 26), "MYKPOPNEWS.KR", font=font_watermark, fill=(*ACCENT_PINK, 200))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), "image/png"



def load_group_images():
    """group_images.json (upload_group_images.py가 생성)을 읽어온다."""
    if os.path.exists(config.GROUP_IMAGES_FILE):
        try:
            with open(config.GROUP_IMAGES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def pick_group_image_media_id(group_key, group_images):
    """해당 그룹에 미리 업로드해둔 이미지 중 하나의 미디어 ID를 고른다."""
    media_ids = group_images.get(group_key)
    if not media_ids:
        return None
    if config.GROUP_IMAGE_SELECTION == "sequential":
        state_file = "group_image_rotation.json"
        state = {}
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                state = {}
        idx = state.get(group_key, 0) % len(media_ids)
        state[group_key] = idx + 1
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return media_ids[idx]
    return random.choice(media_ids)


def wp_auth_header():
    token = base64.b64encode(f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def upload_media(image_bytes, filename, mime_type="image/png"):
    resp = requests.post(
        f"{config.WP_URL}/wp-json/wp/v2/media",
        headers={**wp_auth_header(), "Content-Disposition": f"attachment; filename={filename}", "Content-Type": mime_type},
        data=image_bytes,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def get_media_url(media_id):
    """미디어 ID로 실제 이미지 URL을 조회 (인스타그램 게시에 필요)."""
    if not media_id:
        return None
    try:
        resp = requests.get(f"{config.WP_URL}/wp-json/wp/v2/media/{media_id}", headers=wp_auth_header(), timeout=10)
        resp.raise_for_status()
        return resp.json().get("source_url")
    except Exception:
        return None


def get_or_create_category(name):
    resp = requests.get(f"{config.WP_URL}/wp-json/wp/v2/categories", headers=wp_auth_header(), params={"search": name}, timeout=10)
    resp.raise_for_status()
    results = resp.json()
    if results:
        return results[0]["id"]
    create = requests.post(f"{config.WP_URL}/wp-json/wp/v2/categories", headers=wp_auth_header(), json={"name": name}, timeout=10)
    create.raise_for_status()
    return create.json()["id"]


def is_already_posted_wp(title):
    """워드프레스에 이미 같은 제목의 글이 있는지 확인 (2차 방어선)."""
    try:
        resp = requests.get(
            f"{config.WP_URL}/wp-json/wp/v2/posts",
            headers=wp_auth_header(),
            params={"search": title, "per_page": 5},
            timeout=10,
        )
        resp.raise_for_status()
        clean_target = re.sub(r"[^a-zA-Z0-9가-힣]", "", title).lower()
        for post in resp.json():
            post_title = post.get("title", {}).get("rendered", "")
            clean_post = re.sub(r"[^a-zA-Z0-9가-힣]", "", post_title).lower()
            if clean_target and (clean_target in clean_post or clean_post in clean_target):
                return True
    except Exception:
        pass
    return False


def slugify_fallback(title, max_words=6):
    """AI가 slug를 안 주거나 비어있을 때, 제목에서 직접 짧은 슬러그를 생성."""
    ascii_only = re.sub(r"[^a-zA-Z0-9\s-]", "", title).strip().lower()
    words = ascii_only.split()[:max_words]
    slug = "-".join(words)
    return slug or None


def publish_post(title, body_html, category_id, media_id, source_url, source_name, slug=None, meta_description=None):
    meta = {"source_url": source_url, "source_name": source_name}
    if meta_description:
        meta["_yoast_wpseo_metadesc"] = meta_description[:160]  # Yoast 권장 길이 안전 마진

    payload = {
        "title": title,
        "content": body_html,
        "status": config.POST_STATUS,
        "categories": [category_id],
        "meta": meta,
    }
    if media_id:
        payload["featured_media"] = media_id

    final_slug = slug or slugify_fallback(title)
    if final_slug:
        payload["slug"] = final_slug

    resp = requests.post(f"{config.WP_URL}/wp-json/wp/v2/posts", headers=wp_auth_header(), json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 메인 루프
# ---------------------------------------------------------------------------

def run():
    posted_links = load_json_set(POSTED_LINKS_FILE)
    candidates = fetch_news_candidates()
    print(f"📋 검색된 후보 기사: 총 {len(candidates)}개")

    published = 0
    for index, item in enumerate(candidates, 1):
        if published >= config.MAX_POSTS_PER_RUN:
            print(f"🎯 이번 실행 최대 게시 개수({config.MAX_POSTS_PER_RUN}개) 도달")
            break

        if item["link"] in posted_links:
            continue
        if not item["title"] or is_likely_non_article(item["title"]):
            continue
        if not is_kpop_relevant(item["title"]):
            continue

        real_link = resolve_real_url(item["link"])
        if is_video_link(real_link):
            save_posted_link(item["link"])
            continue

        print(f"\n[기사 후보 {index}] {item['title']}")

        full_text = fetch_full_text(real_link)
        if len(full_text) < 50:
            print("  → 본문 확보 실패, 건너뜀")
            continue

        try:
            recent_titles = get_recent_titles_for_dedup()
            rewritten = rewrite_with_gemini(item["title"], full_text, "", recent_titles)
        except Exception as e:
            print(f"  → Gemini 재작성 실패: {e}")
            continue

        new_title = rewritten["title"]

        if is_similar_to_existing(new_title):
            print(f"  ⚠️ 유사한 기존 글 있음, 건너뜀: {new_title}")
            save_posted_link(item["link"])
            continue
        if is_already_posted_wp(new_title):
            print(f"  ⚠️ 워드프레스에 이미 존재, 건너뜀: {new_title}")
            save_posted_link(item["link"])
            continue

        category_id = get_or_create_category(rewritten.get("category") or config.DEFAULT_CATEGORY)

        media_id = None
        image_bytes = None
        detected_group = (
            detect_group(rewritten.get("card_label", ""))
            or detect_group(new_title)
            or detect_group(item["title"])
        )
        if getattr(config, "ENABLE_GROUP_IMAGES", False) and detected_group:
            group_images = load_group_images()
            media_id = pick_group_image_media_id(detected_group, group_images)
            if media_id:
                print(f"  🖼️ 그룹 사전 제작 이미지 사용: {detected_group}")

        if not media_id:
            try:
                card_label = rewritten.get("card_label") or new_title
                image_bytes, mime_type = generate_typography_card(
                    rewritten.get("category") or config.DEFAULT_CATEGORY,
                    card_label,
                )
                media_id = upload_media(image_bytes, "kpop-card.png", mime_type)
            except Exception as e:
                print(f"  ⚠️ 그래픽 카드 생성 실패(이미지 없이 발행): {e}")

        try:
            result = publish_post(
                new_title,
                rewritten["body_html"],
                category_id,
                media_id,
                real_link,
                "원문 기사",
                slug=rewritten.get("slug"),
                meta_description=rewritten.get("meta_description"),
            )
            print(f"  ✔ 발행 완료: {result.get('link')}")
            save_posted_link(item["link"])
            save_posted_title(new_title)
            published += 1

            try:
                post_to_twitter(new_title, result.get("link"), image_bytes)
                post_to_instagram(
                    f"{new_title}\n\n{rewritten.get('meta_description', '')}\n\n#{(detected_group or '').replace(' ', '')} #kpop",
                    get_media_url(media_id),
                )
            except Exception as e:
                print(f"  ⚠️ SNS 게시 중 오류(발행 자체는 완료됨): {e}")

            if published < config.MAX_POSTS_PER_RUN:
                base_interval = config.SPREAD_MINUTES / config.MAX_POSTS_PER_RUN
                wait_minutes = random.uniform(base_interval * 0.7, base_interval * 1.3)
                print(f"  ⏳ 다음 게시까지 약 {wait_minutes:.1f}분 대기")
                time.sleep(wait_minutes * 60)
        except Exception as e:
            print(f"  → 발행 실패: {e}")
            save_posted_link(item["link"])

    print(f"\n🏁 총 {published}건 발행 완료.")


if __name__ == "__main__":
    if getattr(config, "RUN_CONTINUOUSLY", False):
        while True:
            run()
            wait_minutes = random.randint(config.MIN_INTERVAL_MINUTES, config.MAX_INTERVAL_MINUTES)
            next_run = time.strftime("%H:%M:%S", time.localtime(time.time() + wait_minutes * 60))
            print(f"\n🕐 다음 실행까지 {wait_minutes}분 대기합니다. (예상 실행 시각: {next_run}) (Ctrl+C로 종료)")
            time.sleep(wait_minutes * 60)
    else:
        run()
