import re

import requests
import streamlit as st


# ============================================================
# 1. Streamlit 기본 설정
# ============================================================

st.set_page_config(
    page_title="이름으로 찾는 영화",
    page_icon="🎬",
)


# ============================================================
# 2. KOBIS 영화목록 API
# ============================================================

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
# 4. 한글을 초성으로 바꾸는 함수
# ============================================================

def get_chosung(text):
    """
    한글 문자를 초성으로 바꿉니다.

    예:
        홍길동 -> ㅎㄱㄷ
        기생충 -> ㄱㅅㅊ
    """

    result = []

    for char in text:

        code = ord(char)

        # 한글 완성형 문자인지 확인합니다.
        if 0xAC00 <= code <= 0xD7A3:

            chosung_index = (
                code - 0xAC00
            ) // 588

            result.append(
                CHOSUNG_LIST[chosung_index]
            )

        else:
            # 한글이 아닌 문자는 그대로 둡니다.
            result.append(char)

    return "".join(result)


# ============================================================
# 5. 이름에서 공백 제거
# ============================================================

def clean_name(name):
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
    KOBIS는 인증키가 잘못되어도 HTTP 200을 반환할 수 있습니다.
    따라서 응답 안의 faultInfo를 확인합니다.
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
        or "KOBIS API 오류가 발생했습니다."
    )


# ============================================================
# 7. KOBIS 영화목록 가져오기
# ============================================================

@st.cache_data(ttl=60 * 60 * 24)
def get_all_movies(api_key):
    """
    KOBIS 영화목록을 여러 페이지에 걸쳐 가져옵니다.
    """

    all_movies = []

    # 한 번에 100개씩 가져옵니다.
    items_per_page = 100

    # 너무 많은 API 요청을 방지합니다.
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
                f"KOBIS API에 접속하지 못했습니다.\n\n{error}"
            )

        try:

            data = response.json()

        except ValueError:

            raise RuntimeError(
                "KOBIS API가 올바른 JSON을 반환하지 않았습니다."
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
                "KOBIS 응답에 영화 목록이 없습니다."
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
    영화 제목의 초성에
    입력한 이름의 초성이 연속으로 들어가는지 확인합니다.
    """

    matched = []

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

        # 입력한 초성이 영화 제목 초성에 들어가면 추가합니다.
        if input_chosung in movie_chosung:

            matched.append(
                movie_name
            )

    # 같은 영화가 여러 번 들어오는 경우를 제거합니다.
    return list(
        dict.fromkeys(matched)
    )


# ============================================================
# 9. 제목
# ============================================================

st.title(
    "🎬 이름으로 찾는 영화"
)

st.write(
    "이름을 입력하면 그 이름의 초성이 들어가는 "
    "영화 제목을 찾아드립니다."
)


# ============================================================
# 10. 이름 입력
# ============================================================

name = st.text_input(
    "이름을 입력하세요",
    placeholder="예: 홍길동",
)


if not name:

    st.info(
        "이름을 입력해 주세요. 😊"
    )

    st.stop()


# 이름에서 공백 제거
cleaned_name = clean_name(
    name
)


if not cleaned_name:

    st.warning(
        "이름을 한 글자 이상 입력해 주세요."
    )

    st.stop()


# ============================================================
# 11. 이름 → 초성
# ============================================================

input_chosung = get_chosung(
    cleaned_name
)


st.write(
    f"이름의 초성: **{input_chosung}**"
)


# ============================================================
# 12. KOBIS 인증키
# ============================================================

# 인증키는 코드에 직접 넣지 않습니다.
# Streamlit Cloud의 Secrets에서 가져옵니다.
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
        Streamlit Cloud에서 다음을 확인하세요.

        1. 앱의 Settings를 엽니다.
        2. Secrets 메뉴로 이동합니다.
        3. KOBIS_KEY를 등록합니다.
        4. 저장 후 앱을 다시 실행합니다.
        """
    )

    st.stop()


# ============================================================
# 13. 영화 목록 가져오기
# ============================================================

with st.spinner(
    "영화 목록을 불러오는 중..."
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
            다음을 확인해 주세요.

            - KOBIS_KEY가 정확한지
            - KOBIS 인증키가 정상인지
            - KOBIS 서버가 정상인지
            - 인터넷 연결이 정상인지
            """
        )

        st.code(
            str(error)
        )

        st.stop()


# ============================================================
# 14. 초성이 들어가는 영화 찾기
# ============================================================

matched_movies = find_matching_movies(
    movies,
    input_chosung,
)


# ============================================================
# 15. 결과 표시
# ============================================================

if not matched_movies:

    st.warning(
        f"**{input_chosung}**이 들어가는 "
        "영화 제목을 찾지 못했습니다."
    )

else:

    st.success(
        f"{len(matched_movies)}개의 영화를 찾았습니다."
    )

    st.subheader(
        "🎞️ 영화 목록"
    )

    # 영화 제목만 깔끔하게 보여줍니다.
    for movie_name in matched_movies:

        st.write(
            f"🎬 **{movie_name}**"
        )


# ============================================================
# 16. 데이터 출처
# ============================================================

st.caption(
    "영화명 데이터: "
    "영화진흥위원회 영화관입장권통합전산망(KOBIS) Open API"
)
