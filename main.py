import re
from datetime import date, timedelta

import requests
import streamlit as st


# ============================================================
# 1. Streamlit 기본 설정
# ============================================================

st.set_page_config(
    page_title="이름으로 찾는 영화 추천",
    page_icon="🎬",
    layout="centered",
)


# ============================================================
# 2. KOBIS API 주소
# ============================================================

# KOBIS 영화목록 API
MOVIE_LIST_API = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "movie/searchMovieList.json"
)

# KOBIS 주간 박스오피스 API
WEEKLY_BOXOFFICE_API = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchWeeklyBoxOfficeList.json"
)


# ============================================================
# 3. 한글 초성 목록
# ============================================================

# 한글 음절을 초성으로 바꿀 때 사용하는 19개의 초성입니다.
CHOSUNG_LIST = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ",
    "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ",
    "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]


# ============================================================
# 4. 한글 문자열을 초성 문자열로 바꾸기
# ============================================================

def get_chosung(text):
    """
    한글 문자열의 초성을 뽑습니다.

    예:
        기생충 -> ㄱㅅㅊ
        범죄도시 -> ㅂㅈㄷㅅ
        겨울왕국 -> ㄱㅇㅇㄱ
    """

    result = []

    for char in text:
        code = ord(char)

        # 한글 완성형 음절인지 확인합니다.
        if 0xAC00 <= code <= 0xD7A3:
            # 한글 유니코드에서 초성 번호를 계산합니다.
            chosung_index = (code - 0xAC00) // 588
            result.append(CHOSUNG_LIST[chosung_index])
        else:
            # 영어, 숫자 등은 그대로 둡니다.
            result.append(char)

    return "".join(result)


# ============================================================
# 5. 이름 정리
# ============================================================

def clean_name(name):
    """
    이름 사이의 공백을 제거합니다.
    """

    return re.sub(r"\s+", "", name.strip())


# ============================================================
# 6. 숫자 변환 함수
# ============================================================

def to_int(value):
    """
    API에서 숫자가 문자열로 와도 안전하게 숫자로 바꿉니다.
    """

    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0


# ============================================================
# 7. KOBIS 오류 확인
# ============================================================

def check_kobis_error(data):
    """
    KOBIS의 faultInfo를 확인합니다.

    중요:
    KOBIS는 인증키가 틀려도 HTTP 200을 보낼 수 있기 때문에
    HTTP 상태 코드만 확인하면 안 됩니다.
    """

    if "faultInfo" not in data:
        return None

    fault_info = data.get("faultInfo", {})

    return (
        fault_info.get("message")
        or fault_info.get("faultString")
        or fault_info.get("errorMessage")
        or "KOBIS에서 알 수 없는 오류를 반환했습니다."
    )


# ============================================================
# 8. API 요청 공통 함수
# ============================================================

def request_json(url, params):
    """
    KOBIS API에 요청하고 JSON을 반환합니다.
    """

    try:
        response = requests.get(
            url,
            params=params,
            timeout=15,
        )

        response.raise_for_status()

    except requests.exceptions.Timeout:
        raise RuntimeError(
            "KOBIS API 응답 시간이 초과되었습니다."
        )

    except requests.exceptions.RequestException as error:
        raise RuntimeError(
            f"KOBIS API에 접속하지 못했습니다.\n\n{error}"
        )

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            "KOBIS API가 올바른 JSON 응답을 보내지 않았습니다."
        )

    error_message = check_kobis_error(data)

    if error_message:
        raise RuntimeError(
            f"KOBIS API 오류:\n{error_message}"
        )

    return data


# ============================================================
# 9. KOBIS 영화 목록 가져오기
# ============================================================

@st.cache_data(ttl=60 * 60 * 24)
def get_all_movies(api_key):
    """
    KOBIS 영화목록을 여러 페이지에 걸쳐 가져옵니다.

    영화목록 자체는 자주 바뀌지 않으므로 하루 동안 캐시합니다.
    """

    all_movies = []

    # 한 번에 100편씩 요청합니다.
    items_per_page = 100

    # 너무 많은 요청을 막기 위해 최대 50페이지까지 조회합니다.
    max_pages = 50

    for page in range(1, max_pages + 1):

        params = {
            "key": api_key,
            "curPage": page,
            "itemPerPage": items_per_page,
        }

        data = request_json(
            MOVIE_LIST_API,
            params,
        )

        result = data.get("movieListResult")

        if not result:
            raise RuntimeError(
                "KOBIS 응답에 movieListResult가 없습니다."
            )

        movies = result.get("movieList", [])

        if not movies:
            break

        all_movies.extend(movies)

        total_count = to_int(
            result.get("totCnt", 0)
        )

        # 전체 영화를 다 가져왔다면 종료합니다.
        if len(all_movies) >= total_count:
            break

    if not all_movies:
        raise RuntimeError(
            "KOBIS에서 영화 목록을 하나도 가져오지 못했습니다."
        )

    return all_movies


# ============================================================
# 10. 입력한 이름과 초성이 맞는 영화 찾기
# ============================================================

def find_matching_movies(movies, input_chosung):
    """
    영화 제목의 초성에
    사용자의 초성이 연속으로 포함되는 영화를 찾습니다.

    예:
        입력 초성: ㄱㅁㅅ

        제목 초성: ㄱㅁㅅㅇ
        -> 일치

        제목 초성: ㅁㄱㅅ
        -> 불일치
    """

    matched = []

    for movie in movies:

        movie_name = (
            movie.get("movieNm") or ""
        ).strip()

        if not movie_name:
            continue

        movie_chosung = get_chosung(
            movie_name
        )

        if input_chosung in movie_chosung:

            matched.append(
                {
                    "movieCd": movie.get("movieCd"),
                    "movieNm": movie_name,
                    "openDt": movie.get("openDt") or "",
                    "movieChosung": movie_chosung,
                }
            )

    return matched


# ============================================================
# 11. 날짜를 주간 박스오피스 조회용으로 변환
# ============================================================

def get_sunday_on_or_before(target_date):
    """
    해당 날짜가 포함된 주의 일요일을 구합니다.

    KOBIS 주간 박스오피스의 weekGb=0은 주간 조회이며,
    weekEndDt를 일요일 날짜로 넣습니다.
    """

    # Python weekday:
    # 월=0 ... 일=6
    days_since_sunday = (
        target_date.weekday() + 1
    ) % 7

    return target_date - timedelta(
        days=days_since_sunday
    )


# ============================================================
# 12. 특정 주의 박스오피스 가져오기
# ============================================================

@st.cache_data(ttl=60 * 60 * 24)
def get_weekly_boxoffice(
    api_key,
    week_end_date,
):
    """
    특정 주의 KOBIS 주간 박스오피스를 가져옵니다.

    반환값은 movieCd를 키로 하는 딕셔너리입니다.
    """

    params = {
        "key": api_key,
        "weekGb": "0",
        "targetDt": week_end_date.strftime("%Y%m%d"),
    }

    data = request_json(
        WEEKLY_BOXOFFICE_API,
        params,
    )

    result = data.get(
        "boxOfficeResult",
        {},
    )

    movie_list = result.get(
        "weeklyBoxOfficeList",
        [],
    )

    return {
        movie.get("movieCd"): movie
        for movie in movie_list
        if movie.get("movieCd")
    }


# ============================================================
# 13. 영화의 누적 관객수 찾기
# ============================================================

@st.cache_data(ttl=60 * 60 * 24)
def get_movie_audience(
    api_key,
    movie_code,
    open_date,
):
    """
    영화가 개봉한 시점부터 주간 박스오피스를 확인해서
    KOBIS가 제공하는 실제 audiAcc(누적관객수)를 찾습니다.

    영화가 개봉한 주부터 최대 12주까지 확인합니다.

    이렇게 하는 이유:
    영화 상세정보 API에 없는 audiAcc를
    실제 박스오피스 API에서 가져오기 위해서입니다.
    """

    if not open_date or len(open_date) != 8:
        return None

    try:
        release_date = date(
            int(open_date[:4]),
            int(open_date[4:6]),
            int(open_date[6:8]),
        )
    except ValueError:
        return None

    # 개봉 주의 일요일을 구합니다.
    first_week = get_sunday_on_or_before(
        release_date
    )

    best_audience = None
    found_any = False

    # 영화의 초기 상영 기간을 넉넉하게 확인합니다.
    # 대부분의 영화는 이 기간 안에 주간 박스오피스에 등장합니다.
    for week_number in range(12):

        week_end = (
            first_week
            + timedelta(days=7 * week_number)
        )

        # 너무 미래의 날짜는 조회하지 않습니다.
        if week_end > date.today():
            break

        weekly_movies = get_weekly_boxoffice(
            api_key,
            week_end,
        )

        movie = weekly_movies.get(
            movie_code
        )

        if not movie:
            continue

        found_any = True

        # ★ 실제 KOBIS 박스오피스의 누적관객수
        audi_acc = to_int(
            movie.get("audiAcc")
        )

        if best_audience is None:
            best_audience = audi_acc
        else:
            best_audience = max(
                best_audience,
                audi_acc,
            )

    if not found_any:
        return None

    return best_audience


# ============================================================
# 14. 화면 시작
# ============================================================

st.title("🎬 이름으로 찾는 영화 추천")

st.write(
    "이름을 입력하면 이름의 초성이 들어가는 영화 중 "
    "KOBIS 누적 관객수를 기준으로 영화를 찾아드립니다."
)

st.caption(
    "예: 홍길동 → ㅎㄱㄷ → 영화 제목의 초성에 ㅎㄱㄷ가 "
    "연속으로 들어가는 영화 검색"
)


# ============================================================
# 15. 이름 입력
# ============================================================

name = st.text_input(
    "이름을 입력하세요",
    placeholder="예: 홍길동",
)


if not name:
    st.info(
        "이름을 입력하면 영화 추천을 시작합니다. 😊"
    )
    st.stop()


cleaned_name = clean_name(name)

if not cleaned_name:
    st.warning(
        "이름을 한 글자 이상 입력해 주세요."
    )
    st.stop()


# ============================================================
# 16. 이름을 초성으로 변환
# ============================================================

input_chosung = get_chosung(
    cleaned_name
)

st.write(
    f"입력한 이름: **{cleaned_name}**"
)

st.write(
    f"이름의 초성: **{input_chosung}**"
)


# ============================================================
# 17. KOBIS 인증키 가져오기
# ============================================================

# 인증키는 절대로 코드에 직접 넣지 않습니다.
# Streamlit Cloud의 Secrets에서 가져옵니다.
try:
    api_key = st.secrets["KOBIS_KEY"]

except (KeyError, FileNotFoundError):

    st.error(
        "KOBIS_KEY를 찾을 수 없습니다."
    )

    st.warning(
        """
        Streamlit Cloud에서 다음을 확인해 주세요.

        1. 앱의 Settings로 이동
        2. Secrets 메뉴 열기
        3. KOBIS_KEY 등록
        4. 저장 후 앱 다시 실행
        """
    )

    st.stop()


# ============================================================
# 18. 전체 영화 목록 가져오기
# ============================================================

with st.spinner(
    "KOBIS에서 영화 목록을 가져오는 중입니다..."
):

    try:
        movies = get_all_movies(
            api_key
        )

    except RuntimeError as error:

        st.error(
            "영화 목록을 가져오지 못했습니다."
        )

        st.warning(
            """
            다음 항목을 확인해 주세요.

            - KOBIS_KEY가 정확한지
            - 인증키가 정상적으로 발급되었는지
            - KOBIS API 서버가 정상인지
            - 인터넷 연결이 정상인지
            """
        )

        st.code(str(error))

        st.stop()


# ============================================================
# 19. 초성이 일치하는 영화 찾기
# ============================================================

matched_movies = find_matching_movies(
    movies,
    input_chosung,
)


if not matched_movies:

    st.warning(
        f"초성 **{input_chosung}**이 제목에 들어가는 "
        "영화를 찾지 못했습니다."
    )

    st.info(
        "다른 이름을 입력해 보세요."
    )

    st.stop()


st.success(
    f"초성이 일치하는 영화 "
    f"**{len(matched_movies)}편**을 찾았습니다."
)


# ============================================================
# 20. 후보 영화의 실제 누적관객수 확인
# ============================================================

st.subheader(
    "📊 후보 영화의 관객수 확인 중"
)

st.write(
    "KOBIS 주간 박스오피스에서 실제 누적관객수를 "
    "확인하고 있습니다. 처음 검색할 때는 조금 걸릴 수 있습니다."
)

progress_bar = st.progress(0)
progress_text = st.empty()

audience_movies = []

total = len(matched_movies)

for index, movie in enumerate(
    matched_movies
):

    progress_text.write(
        f"{index + 1} / {total} "
        f"— {movie['movieNm']}"
    )

    try:
        audi_acc = get_movie_audience(
            api_key=api_key,
            movie_code=movie["movieCd"],
            open_date=movie["openDt"],
        )

    except RuntimeError:
        # 한 영화의 데이터를 가져오지 못했다고
        # 전체 프로그램을 종료하지 않습니다.
        audi_acc = None

    if audi_acc is not None:

        audience_movies.append(
            {
                "movieCd": movie["movieCd"],
                "movieNm": movie["movieNm"],
                "openDt": movie["openDt"],
                "movieChosung": movie["movieChosung"],
                "audiAcc": audi_acc,
            }
        )

    progress_bar.progress(
        (index + 1) / total
    )


progress_text.empty()
progress_bar.empty()


# ============================================================
# 21. 관객수 데이터를 찾지 못한 경우
# ============================================================

if not audience_movies:

    st.error(
        "초성이 일치하는 영화는 찾았지만 "
        "관객수 데이터를 확인하지 못했습니다."
    )

    st.warning(
        """
        다음 항목을 확인해 주세요.

        - KOBIS API 인증키가 정상인지
        - KOBIS 주간 박스오피스 API가 정상인지
        - 해당 영화가 KOBIS 박스오피스 데이터에 존재하는지
        - API 요청 횟수 제한에 걸리지 않았는지
        """
    )

    st.stop()


# ============================================================
# 22. 누적관객수가 가장 많은 영화 선택
# ============================================================

audience_movies.sort(
    key=lambda movie: movie["audiAcc"],
    reverse=True,
)

recommended = audience_movies[0]


# ============================================================
# 23. 추천 영화 표시
# ============================================================

st.divider()

st.subheader(
    "🍿 추천 영화"
)

st.markdown(
    f"## 🎬 {recommended['movieNm']}"
)


# ============================================================
# 24. 추천 영화 정보 카드
# ============================================================

col1, col2, col3 = st.columns(3)


with col1:
    st.metric(
        "누적 관객수",
        f"{recommended['audiAcc']:,}명",
    )


with col2:

    open_date = (
        recommended["openDt"]
        or "정보 없음"
    )

    if len(open_date) == 8:
        open_date = (
            f"{open_date[:4]}."
            f"{open_date[4:6]}."
            f"{open_date[6:]}"
        )

    st.metric(
        "개봉일",
        open_date,
    )


with col3:
    st.metric(
        "입력 초성",
        input_chosung,
    )


# ============================================================
# 25. 추천 이유
# ============================================================

st.info(
    f"""
    **{cleaned_name}**의 초성은 **{input_chosung}**입니다.

    초성이 영화 제목에 들어가는 후보 중에서
    KOBIS 박스오피스의 **누적 관객수가 가장 높은 영화**를
    추천했습니다.
    """
)


# ============================================================
# 26. 후보 영화 전체 보기
# ============================================================

with st.expander(
    "🔎 초성이 일치한 영화 전체 보기"
):

    display_movies = []

    for movie in audience_movies:

        open_date = (
            movie["openDt"]
            or "-"
        )

        if len(open_date) == 8:
            open_date = (
                f"{open_date[:4]}."
                f"{open_date[4:6]}."
                f"{open_date[6:]}"
            )

        display_movies.append(
            {
                "영화명": movie["movieNm"],
                "제목 초성": movie["movieChosung"],
                "개봉일": open_date,
                "누적관객수": (
                    f"{movie['audiAcc']:,}명"
                ),
            }
        )

    st.dataframe(
        display_movies,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# 27. 데이터 출처
# ============================================================

st.caption(
    "영화 및 관객수 데이터: "
    "영화진흥위원회 영화관입장권통합전산망(KOBIS) Open API"
)
