import re

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
# 2. KOBIS 영화목록 API 주소
# ============================================================

# 영화목록 API에서 영화 이름과 개봉일을 가져옵니다.
MOVIE_LIST_API = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "movie/searchMovieList.json"
)


# ============================================================
# 3. 한글 초성 목록
# ============================================================

CHOSUNG_LIST = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ",
    "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ",
    "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]


# ============================================================
# 4. 한글을 초성으로 변환하는 함수
# ============================================================

def get_chosung(text):
    """
    한글 문자를 초성으로 변환합니다.

    예:
        홍길동 -> ㅎㄱㄷ
        기생충 -> ㄱㅅㅊ
        범죄도시 -> ㅂㅈㄷㅅ
    """

    result = []

    for char in text:

        code = ord(char)

        # 한글 완성형 문자인지 확인합니다.
        if 0xAC00 <= code <= 0xD7A3:

            # 한글 유니코드에서 초성 번호를 계산합니다.
            chosung_index = (
                code - 0xAC00
            ) // 588

            result.append(
                CHOSUNG_LIST[chosung_index]
            )

        else:
            # 영어, 숫자, 특수문자 등은 그대로 둡니다.
            result.append(char)

    return "".join(result)


# ============================================================
# 5. 이름 정리
# ============================================================

def clean_name(name):
    """
    이름에 들어간 공백을 제거합니다.
    """

    return re.sub(
        r"\s+",
        "",
        name.strip(),
    )


# ============================================================
# 6. KOBIS API 오류 확인
# ============================================================

def get_kobis_error(data):
    """
    KOBIS 응답에 faultInfo가 있는지 확인합니다.

    인증키가 잘못되어도 HTTP 상태코드가 200일 수 있으므로
    응답 안의 faultInfo도 확인합니다.
    """

    if "faultInfo" not in data:
        return None

    fault_info = data.get(
        "faultInfo",
        {},
    )

    return (
        fault_info.get("message")
        or fault_info.get("faultString")
        or fault_info.get("errorMessage")
        or "KOBIS에서 알 수 없는 오류가 발생했습니다."
    )


# ============================================================
# 7. KOBIS 영화목록 가져오기
# ============================================================

@st.cache_data(ttl=60 * 60 * 24)
def get_all_movies(api_key):
    """
    KOBIS 영화목록을 여러 페이지에 걸쳐 가져옵니다.

    영화목록은 자주 바뀌지 않으므로 하루 동안 캐시합니다.
    """

    all_movies = []

    # 한 번의 요청에서 최대 100편을 가져옵니다.
    items_per_page = 100

    # 지나치게 많은 API 요청을 방지합니다.
    max_pages = 50

    for page in range(
        1,
        max_pages + 1,
    ):

        params = {
            "key": api_key,
            "curPage": page,
            "itemPerPage": items_per_page,
        }

        try:

            response = requests.get(
                MOVIE_LIST_API,
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
                "KOBIS API에 접속하지 못했습니다.\n\n"
                f"{error}"
            )

        try:

            data = response.json()

        except ValueError:

            raise RuntimeError(
                "KOBIS API가 올바른 JSON 응답을 보내지 않았습니다."
            )

        # KOBIS 자체 오류를 확인합니다.
        error_message = get_kobis_error(
            data
        )

        if error_message:

            raise RuntimeError(
                f"KOBIS API 오류:\n{error_message}"
            )

        result = data.get(
            "movieListResult"
        )

        if not result:

            raise RuntimeError(
                "KOBIS 응답에 movieListResult가 없습니다."
            )

        movies = result.get(
            "movieList",
            [],
        )

        if not movies:
            break

        all_movies.extend(
            movies
        )

        # 전체 영화 수를 확인합니다.
        total_count = int(
            result.get(
                "totCnt",
                0,
            )
        )

        # 전체 영화 목록을 가져왔다면 종료합니다.
        if len(all_movies) >= total_count:
            break

    if not all_movies:

        raise RuntimeError(
            "KOBIS에서 영화 목록을 가져오지 못했습니다."
        )

    return all_movies


# ============================================================
# 8. 초성이 일치하는 영화 찾기
# ============================================================

def find_matching_movies(
    movies,
    input_chosung,
):
    """
    사용자의 이름 초성이 영화 제목의 초성에
    연속으로 들어가는 영화를 찾습니다.
    """

    matched_movies = []

    for movie in movies:

        movie_name = (
            movie.get("movieNm")
            or ""
        ).strip()

        if not movie_name:
            continue

        movie_chosung = get_chosung(
            movie_name
        )

        # 이름 초성이 영화 제목 초성에 들어있는지 확인합니다.
        if input_chosung in movie_chosung:

            matched_movies.append(
                {
                    "movieCd": movie.get(
                        "movieCd"
                    ),
                    "movieNm": movie_name,
                    "openDt": movie.get(
                        "openDt"
                    )
                    or "",
                    "movieChosung": movie_chosung,
                }
            )

    return matched_movies


# ============================================================
# 9. 개봉 연도 가져오기
# ============================================================

def get_release_year(open_date):
    """
    KOBIS의 개봉일(YYYYMMDD)에서 연도만 가져옵니다.

    예:
        20190726 -> 2019
    """

    if (
        open_date
        and len(open_date) >= 4
        and open_date[:4].isdigit()
    ):
        return int(
            open_date[:4]
        )

    return None


# ============================================================
# 10. 앱 제목
# ============================================================

st.title(
    "🎬 이름으로 찾는 영화 추천"
)

st.write(
    "이름을 입력하면 이름의 초성이 들어가는 "
    "영화를 찾아 개봉 연도와 함께 보여드립니다."
)

st.caption(
    "예: 홍길동 → ㅎㄱㄷ → 영화 제목 초성에 ㅎㄱㄷ가 "
    "들어가는 영화 검색"
)


# ============================================================
# 11. 이름 입력
# ============================================================

name = st.text_input(
    "이름을 입력하세요",
    placeholder="예: 홍길동",
)


# 아직 이름을 입력하지 않은 경우
if not name:

    st.info(
        "이름을 입력하면 영화 추천을 시작합니다. 😊"
    )

    st.stop()


# 입력한 이름에서 공백 제거
cleaned_name = clean_name(
    name
)


if not cleaned_name:

    st.warning(
        "이름을 한 글자 이상 입력해 주세요."
    )

    st.stop()


# ============================================================
# 12. 이름 → 초성
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
# 13. KOBIS 인증키 가져오기
# ============================================================

# 인증키를 코드에 직접 적지 않습니다.
# Streamlit Cloud의 Secrets에서 읽습니다.
try:

    api_key = st.secrets[
        "KOBIS_KEY"
    ]

except (
    KeyError,
    FileNotFoundError,
):

    st.error(
        "KOBIS_KEY를 찾을 수 없습니다."
    )

    st.warning(
        """
        Streamlit Cloud에서 다음을 확인해 주세요.

        1. 앱의 Settings를 엽니다.
        2. Secrets 메뉴로 이동합니다.
        3. KOBIS_KEY를 등록합니다.
        4. 저장한 뒤 앱을 다시 실행합니다.
        """
    )

    st.stop()


# ============================================================
# 14. 영화 목록 가져오기
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
            - KOBIS 인증키가 정상적으로 발급되었는지
            - KOBIS API 서버가 정상인지
            - 인터넷 연결이 정상인지
            """
        )

        st.code(
            str(error)
        )

        st.stop()


# ============================================================
# 15. 이름 초성이 들어가는 영화 찾기
# ============================================================

matched_movies = find_matching_movies(
    movies,
    input_chosung,
)


# ============================================================
# 16. 매칭되는 영화가 없는 경우
# ============================================================

if not matched_movies:

    st.warning(
        f"초성 **{input_chosung}**이 영화 제목에 "
        "들어가는 영화를 찾지 못했습니다."
    )

    st.info(
        "다른 이름을 입력해 보세요."
    )

    st.stop()


# ============================================================
# 17. 개봉 연도가 있는 영화만 남기기
# ============================================================

movies_with_year = []

for movie in matched_movies:

    release_year = get_release_year(
        movie["openDt"]
    )

    # 개봉 연도가 확인되는 영화만 사용합니다.
    if release_year is not None:

        movie["releaseYear"] = (
            release_year
        )

        movies_with_year.append(
            movie
        )


# 개봉 연도가 있는 영화가 하나도 없는 경우
if not movies_with_year:

    st.warning(
        "초성이 일치하는 영화는 찾았지만 "
        "개봉 연도 정보를 확인할 수 있는 영화가 없습니다."
    )

    st.info(
        "KOBIS 영화목록 API의 개봉일 정보를 확인해 주세요."
    )

    st.stop()


# ============================================================
# 18. 최신 개봉 영화부터 정렬
# ============================================================

movies_with_year.sort(
    key=lambda movie: (
        movie["releaseYear"],
        movie["movieNm"],
    ),
    reverse=True,
)


# ============================================================
# 19. 추천 영화
# ============================================================

recommended = movies_with_year[0]


st.divider()

st.subheader(
    "🍿 추천 영화"
)

st.markdown(
    f"# 🎬 {recommended['movieNm']}"
)


# ============================================================
# 20. 추천 영화 정보
# ============================================================

col1, col2 = st.columns(2)


with col1:

    st.metric(
        "개봉 연도",
        f"{recommended['releaseYear']}년",
    )


with col2:

    st.metric(
        "이름 초성",
        input_chosung,
    )


st.info(
    f"""
    **{cleaned_name}**의 초성은 **{input_chosung}**입니다.

    영화 제목의 초성이 일치하는 영화 중
    **개봉 연도가 가장 최근인 영화**를 추천했습니다.
    """
)


# ============================================================
# 21. 일치하는 영화 전체 목록
# ============================================================

st.subheader(
    "🎞️ 초성이 일치하는 영화"
)

display_movies = []

for movie in movies_with_year:

    display_movies.append(
        {
            "영화명": movie["movieNm"],
            "제목 초성": movie[
                "movieChosung"
            ],
            "개봉 연도": (
                f"{movie['releaseYear']}년"
            ),
        }
    )


st.dataframe(
    display_movies,
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# 22. 데이터 출처
# ============================================================

st.caption(
    "영화명 및 개봉일 출처: "
    "영화진흥위원회 영화관입장권통합전산망(KOBIS) Open API"
)
