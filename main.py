import re
import time

import requests
import streamlit as st


# =========================================================
# 1. Streamlit 기본 설정
# =========================================================

st.set_page_config(
    page_title="이름으로 찾는 영화 추천",
    page_icon="🎬",
    layout="centered",
)


# =========================================================
# 2. KOBIS API 주소
# =========================================================

# KOBIS 영화목록 API
MOVIE_LIST_API = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "movie/searchMovieList.json"
)

# KOBIS 영화상세정보 API
MOVIE_INFO_API = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "movie/searchMovieInfo.json"
)


# =========================================================
# 3. 한글 한 글자를 초성으로 바꾸는 함수
# =========================================================

# 한글 초성 목록입니다.
CHOSUNG_LIST = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ",
    "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ",
    "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]


def get_chosung(text):
    """
    문자열에 들어 있는 한글의 초성을 뽑습니다.

    예:
        "기생충" -> "ㄱㅅㅊ"
        "범죄도시" -> "ㅂㅈㄷㅅ"

    한글이 아닌 문자는 그대로 유지합니다.
    """

    result = []

    for char in text:
        # 한글 음절의 유니코드 범위인지 확인합니다.
        code = ord(char)

        if 0xAC00 <= code <= 0xD7A3:
            # 한글 음절에서 초성 번호를 계산합니다.
            chosung_index = (code - 0xAC00) // 588
            result.append(CHOSUNG_LIST[chosung_index])

        else:
            # 공백이나 숫자, 영어 등은 그대로 넣습니다.
            result.append(char)

    return "".join(result)


# =========================================================
# 4. 검색하기 좋은 형태로 이름 정리
# =========================================================

def clean_name(name):
    """
    사용자가 입력한 이름에서 공백을 제거합니다.
    """

    return re.sub(r"\s+", "", name.strip())


# =========================================================
# 5. KOBIS API 공통 오류 확인
# =========================================================

def check_api_response(data):
    """
    KOBIS 응답에 faultInfo가 있는지 확인합니다.

    KOBIS는 인증키가 잘못되어도 HTTP 상태코드가 200일 수 있기 때문에
    HTTP 상태코드만 확인하면 안 됩니다.
    """

    if "faultInfo" in data:
        fault_info = data.get("faultInfo", {})

        message = (
            fault_info.get("message")
            or fault_info.get("faultString")
            or fault_info.get("errorMessage")
            or "알 수 없는 KOBIS API 오류"
        )

        return False, message

    return True, None


# =========================================================
# 6. KOBIS 영화목록 가져오기
# =========================================================

@st.cache_data(ttl=60 * 60)
def get_all_movies(api_key):
    """
    KOBIS 영화목록 API를 여러 페이지 조회해서
    영화 목록을 가져옵니다.

    너무 오래 걸리지 않도록 최대 20페이지까지만 조회합니다.
    """

    all_movies = []

    # 한 번에 가져올 영화 수입니다.
    items_per_page = 100

    for page in range(1, 21):
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
            data = response.json()

        except requests.exceptions.Timeout:
            raise RuntimeError(
                "KOBIS 영화목록 API의 응답 시간이 초과되었습니다."
            )

        except requests.exceptions.RequestException as error:
            raise RuntimeError(
                f"KOBIS 영화목록 API에 접속하지 못했습니다.\n\n{error}"
            )

        except ValueError:
            raise RuntimeError(
                "KOBIS가 올바른 JSON 데이터를 반환하지 않았습니다."
            )

        # 인증키 오류 등 KOBIS 자체 오류를 확인합니다.
        ok, error_message = check_api_response(data)

        if not ok:
            raise RuntimeError(
                f"KOBIS API 오류가 발생했습니다.\n\n{error_message}"
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

        # 마지막 페이지라면 더 조회할 필요가 없습니다.
        total_count = int(result.get("totCnt", 0))

        if len(all_movies) >= total_count:
            break

        # API에 너무 빠르게 요청하지 않도록 아주 짧게 기다립니다.
        time.sleep(0.05)

    if not all_movies:
        raise RuntimeError(
            "KOBIS에서 영화 목록을 가져오지 못했습니다."
        )

    return all_movies


# =========================================================
# 7. 영화 상세정보 가져오기
# =========================================================

@st.cache_data(ttl=60 * 60)
def get_movie_info(api_key, movie_code):
    """
    영화 코드로 KOBIS 영화 상세정보를 조회합니다.
    """

    params = {
        "key": api_key,
        "movieCd": movie_code,
    }

    try:
        response = requests.get(
            MOVIE_INFO_API,
            params=params,
            timeout=15,
        )

        response.raise_for_status()
        data = response.json()

    except requests.exceptions.RequestException:
        return None

    except ValueError:
        return None

    ok, _ = check_api_response(data)

    if not ok:
        return None

    result = data.get("movieInfoResult", {})
    return result.get("movieInfo")


# =========================================================
# 8. 추천 대상 영화 찾기
# =========================================================

def find_matching_movies(movies, input_chosung):
    """
    영화 제목의 초성에 사용자의 초성이 연속으로 들어가는
    영화를 찾습니다.

    예:
        사용자 초성: ㄱㅁㅅ

        영화 제목 초성: ㄱㅁㅅㅇㅅ
        -> 매칭

        영화 제목 초성: ㅁㄱㅅ
        -> 매칭하지 않음
    """

    matched = []

    for movie in movies:
        movie_name = movie.get("movieNm", "").strip()

        if not movie_name:
            continue

        movie_chosung = get_chosung(movie_name)

        if input_chosung in movie_chosung:
            matched.append(
                {
                    "movieCd": movie.get("movieCd"),
                    "movieNm": movie_name,
                    "openDt": movie.get("openDt", ""),
                    "movieChosung": movie_chosung,
                }
            )

    return matched


# =========================================================
# 9. 영화 정보에 들어 있는 누적관객수 숫자로 변환
# =========================================================

def get_audi_acc(movie_info):
    """
    KOBIS 영화 상세정보의 누적관객수를 가져옵니다.

    값이 없으면 0으로 처리합니다.
    """

    try:
        return int(movie_info.get("audiAcc", 0))
    except (TypeError, ValueError):
        return 0


# =========================================================
# 10. 화면 제목
# =========================================================

st.title("🎬 이름으로 찾는 영화 추천")

st.write(
    "이름을 입력하면 이름의 초성과 같은 초성이 들어간 영화 중 "
    "누적 관객수가 가장 많은 영화를 찾아드립니다."
)


# =========================================================
# 11. 이름 입력
# =========================================================

name = st.text_input(
    "이름을 입력하세요",
    placeholder="예: 홍길동",
)

# 입력하지 않았다면 여기까지만 보여줍니다.
if not name:
    st.info("이름을 입력하면 영화 추천을 시작합니다. 😊")
    st.stop()


# =========================================================
# 12. 이름 → 초성 변환
# =========================================================

cleaned_name = clean_name(name)

if not cleaned_name:
    st.warning("이름을 한 글자 이상 입력해 주세요.")
    st.stop()

input_chosung = get_chosung(cleaned_name)

st.write(
    f"입력한 이름: **{cleaned_name}**  \n"
    f"이름의 초성: **{input_chosung}**"
)


# =========================================================
# 13. KOBIS 인증키 가져오기
# =========================================================

# 인증키를 코드에 직접 적지 않고
# Streamlit Secrets에서 가져옵니다.
try:
    api_key = st.secrets["KOBIS_KEY"]

except (KeyError, FileNotFoundError):
    st.error("KOBIS 인증키를 찾을 수 없습니다.")

    st.warning(
        "Streamlit Cloud에서 다음을 확인해 주세요.\n\n"
        "1. 앱의 Settings를 엽니다.\n"
        "2. Secrets 메뉴로 이동합니다.\n"
        "3. `KOBIS_KEY`를 등록합니다.\n"
        "4. 저장 후 앱을 다시 실행합니다."
    )

    st.stop()


# =========================================================
# 14. 영화 목록 가져오기
# =========================================================

with st.spinner("KOBIS에서 영화 목록을 가져오는 중입니다..."):
    try:
        movies = get_all_movies(api_key)

    except RuntimeError as error:
        st.error("영화 목록을 가져오지 못했습니다.")

        st.warning(
            "다음 항목을 확인해 주세요.\n\n"
            "- KOBIS_KEY가 정확한지\n"
            "- KOBIS API 사용이 가능한 인증키인지\n"
            "- KOBIS 서버가 정상인지\n"
            "- 인터넷 연결이 정상인지"
        )

        st.code(str(error))

        st.stop()


# =========================================================
# 15. 초성이 들어가는 영화 찾기
# =========================================================

matched_movies = find_matching_movies(
    movies,
    input_chosung,
)

if not matched_movies:
    st.warning(
        f"초성 **{input_chosung}**이 제목에 연속으로 들어가는 "
        "영화를 찾지 못했습니다."
    )

    st.info(
        "다른 이름을 입력해 보세요. "
        "한글 이름을 입력할수록 초성 검색 결과가 달라집니다."
    )

    st.stop()


st.success(
    f"초성이 일치하는 영화 {len(matched_movies)}편을 찾았습니다."
)


# =========================================================
# 16. 후보 영화들의 누적관객수 조회
# =========================================================

movie_results = []

progress_text = st.empty()
progress_bar = st.progress(0)

total = len(matched_movies)

for index, movie in enumerate(matched_movies):

    progress_text.write(
        f"영화 정보를 확인하는 중... "
        f"{index + 1} / {total}"
    )

    movie_info = get_movie_info(
        api_key,
        movie["movieCd"],
    )

    # 상세정보를 가져오지 못한 영화는 제외합니다.
    if not movie_info:
        progress_bar.progress((index + 1) / total)
        continue

    audi_acc = get_audi_acc(movie_info)

    movie_results.append(
        {
            "movieCd": movie["movieCd"],
            "movieNm": movie["movieNm"],
            "movieChosung": movie["movieChosung"],
            "openDt": movie["openDt"],
            "audiAcc": audi_acc,
            "movieInfo": movie_info,
        }
    )

    progress_bar.progress((index + 1) / total)


progress_text.empty()
progress_bar.empty()


# =========================================================
# 17. 누적관객수가 가장 많은 영화 선택
# =========================================================

if not movie_results:
    st.error(
        "초성이 일치하는 영화는 찾았지만 "
        "누적 관객수 정보를 가져오지 못했습니다."
    )

    st.warning(
        "KOBIS 영화 상세정보 API가 정상적으로 응답하는지 "
        "확인해 주세요."
    )

    st.stop()


movie_results.sort(
    key=lambda movie: movie["audiAcc"],
    reverse=True,
)

recommended = movie_results[0]


# =========================================================
# 18. 추천 영화 표시
# =========================================================

st.divider()

st.subheader("🍿 당신에게 추천하는 영화")

st.markdown(
    f"# 🎬 {recommended['movieNm']}"
)

st.write(
    f"**영화 제목의 초성:** {recommended['movieChosung']}"
)


# 추천 영화의 주요 정보를 카드 형태로 보여줍니다.
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "누적 관객수",
        f"{recommended['audiAcc']:,}명",
    )

with col2:
    open_date = recommended["openDt"] or "정보 없음"

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
        "초성 일치",
        input_chosung,
    )


# =========================================================
# 19. 추천 이유
# =========================================================

st.info(
    f"**{cleaned_name}**의 초성은 **{input_chosung}**이고, "
    f"이 초성이 영화 제목에 들어가는 후보 가운데 "
    f"**{recommended['movieNm']}**의 누적 관객수가 가장 많습니다."
)


# =========================================================
# 20. 매칭된 영화 목록도 보여주기
# =========================================================

with st.expander("🔎 초성이 일치한 영화 전체 보기"):

    display_movies = []

    for movie in movie_results:
        display_movies.append(
            {
                "영화명": movie["movieNm"],
                "제목 초성": movie["movieChosung"],
                "개봉일": movie["openDt"] or "-",
                "누적관객수": f"{movie['audiAcc']:,}",
            }
        )

    st.dataframe(
        display_movies,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# 21. 데이터 출처
# =========================================================

st.caption(
    "영화 정보 및 관객수 출처: "
    "영화진흥위원회 영화관입장권통합전산망(KOBIS) Open API"
)

