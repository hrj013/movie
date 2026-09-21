import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st


# ---------------------------------------------------------
# 1. 기본 설정
# ---------------------------------------------------------

# 웹페이지 제목과 화면 설정
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

# KOBIS 일일 박스오피스 API 주소
API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# 한국 시간대
KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------
# 2. 어제 날짜 계산
# ---------------------------------------------------------

def get_yesterday_kst():
    """한국 시간 기준으로 어제 날짜를 yyyymmdd 형태로 반환합니다."""

    # 서버가 한국 시간이 아니어도 한국 시간을 기준으로 계산합니다.
    now_kst = datetime.now(KST)
    yesterday = now_kst - timedelta(days=1)

    return yesterday.strftime("%Y%m%d")


def format_date(date_text):
    """yyyymmdd를 화면에 보기 좋은 yyyy.mm.dd 형태로 바꿉니다."""

    return (
        f"{date_text[:4]}.{date_text[4:6]}.{date_text[6:]}"
    )


# ---------------------------------------------------------
# 3. KOBIS API 호출
# ---------------------------------------------------------

def get_boxoffice_data(target_date):
    """
    KOBIS에서 특정 날짜의 일일 박스오피스를 가져옵니다.

    반환값:
        성공하면 영화 목록(list)
        실패하면 (None, 오류 메시지)
    """

    # Streamlit Secrets에서 인증키를 읽습니다.
    # 실제 인증키는 코드에 넣지 않습니다.
    try:
        kobis_key = st.secrets["KOBIS_KEY"]
    except (KeyError, FileNotFoundError):
        return None, (
            "KOBIS_KEY를 찾을 수 없습니다. "
            "Streamlit Cloud의 앱 설정 → Secrets에 "
            "KOBIS_KEY를 등록했는지 확인해 주세요."
        )

    # API에 전달할 요청값입니다.
    params = {
        "key": kobis_key,
        "targetDt": target_date,
    }

    try:
        # API 서버에 GET 요청을 보냅니다.
        response = requests.get(
            API_URL,
            params=params,
            timeout=10,
        )

        # HTTP 오류가 있으면 예외를 발생시킵니다.
        response.raise_for_status()

        # KOBIS가 보내준 JSON을 파이썬 자료형으로 변환합니다.
        data = response.json()

    except requests.exceptions.Timeout:
        return None, (
            "KOBIS API 응답 시간이 초과되었습니다. "
            "잠시 후 다시 실행해 주세요."
        )

    except requests.exceptions.RequestException as error:
        return None, (
            "KOBIS API에 접속하지 못했습니다. "
            "인터넷 연결이나 KOBIS API 상태를 확인해 주세요.\n\n"
            f"오류 내용: {error}"
        )

    except ValueError:
        return None, (
            "KOBIS API가 올바른 JSON 응답을 보내지 않았습니다. "
            "KOBIS API 상태를 확인해 주세요."
        )

    # -----------------------------------------------------
    # KOBIS는 인증키가 잘못되어도 HTTP 200을 반환하면서
    # faultInfo를 보내는 경우가 있으므로 반드시 확인합니다.
    # -----------------------------------------------------

    if "faultInfo" in data:
        fault_info = data.get("faultInfo", {})

        # KOBIS가 보내는 오류 정보를 최대한 안전하게 표시합니다.
        error_message = (
            fault_info.get("message")
            or fault_info.get("faultString")
            or fault_info.get("errorMessage")
            or "알 수 없는 KOBIS API 오류"
        )

        return None, (
            "KOBIS API에서 오류를 반환했습니다.\n\n"
            f"오류 내용: {error_message}\n\n"
            "인증키(KOBIS_KEY)가 올바른지, "
            "KOBIS API 사용 설정이 정상인지 확인해 주세요."
        )

    # 예상한 응답 구조가 있는지 확인합니다.
    boxoffice_result = data.get("boxOfficeResult")

    if not boxoffice_result:
        return None, (
            "KOBIS 응답에 boxOfficeResult가 없습니다. "
            "API 응답 형식이나 KOBIS 서버 상태를 확인해 주세요."
        )

    movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

    # 영화 목록이 비어 있으면 별도로 안내합니다.
    if not movie_list:
        return None, (
            f"{format_date(target_date)}의 영화 목록이 없습니다.\n\n"
            "조회 날짜가 정상인지, KOBIS에서 해당 날짜의 "
            "박스오피스 집계를 제공하고 있는지 확인해 주세요."
        )

    return movie_list, None


# ---------------------------------------------------------
# 4. 화면 제목
# ---------------------------------------------------------

st.title("🎬 어제의 박스오피스")

target_date = get_yesterday_kst()

st.caption(
    f"한국 시간 기준 조회일: {format_date(target_date)}"
)


# ---------------------------------------------------------
# 5. API에서 데이터 가져오기
# ---------------------------------------------------------

movies, error_message = get_boxoffice_data(target_date)


# 요청 실패 / 오류 / 빈 목록 처리
if error_message:
    st.error("박스오피스 데이터를 가져오지 못했습니다.")

    st.warning(
        "다음 항목을 확인해 주세요:\n\n"
        "1. Streamlit Cloud Secrets에 `KOBIS_KEY`가 등록되어 있는지\n"
        "2. KOBIS 인증키가 정확한지\n"
        "3. KOBIS API 서버가 정상적으로 응답하는지\n"
        "4. 조회 날짜에 박스오피스 집계 데이터가 존재하는지"
    )

    st.info(error_message)

    # 오류가 난 상태에서는 아래 화면을 그리지 않습니다.
    st.stop()


# ---------------------------------------------------------
# 6. 숫자 데이터를 숫자로 변환
# ---------------------------------------------------------

# KOBIS API의 숫자 값은 문자열로 오기 때문에
# 그래프와 숫자 표시를 위해 정수로 변환합니다.
for movie in movies:
    movie["rank"] = int(movie.get("rank", 0))
    movie["audiCnt"] = int(movie.get("audiCnt", 0))
    movie["audiAcc"] = int(movie.get("audiAcc", 0))
    movie["scrnCnt"] = int(movie.get("scrnCnt", 0))


# ---------------------------------------------------------
# 7. 1위 영화 표시
# ---------------------------------------------------------

first_movie = movies[0]

st.subheader(f"🏆 1위 — {first_movie['movieNm']}")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="어제 관객수",
        value=f"{first_movie['audiCnt']:,}명",
    )

with col2:
    st.metric(
        label="누적 관객수",
        value=f"{first_movie['audiAcc']:,}명",
    )

with col3:
    st.metric(
        label="스크린수",
        value=f"{first_movie['scrnCnt']:,}개",
    )


# ---------------------------------------------------------
# 8. 관객수 상위 5편 막대그래프
# ---------------------------------------------------------

st.subheader("📊 관객수 상위 5편")

top5 = movies[:5]

# Streamlit의 기본 막대그래프가 이해하기 쉽도록
# 영화명을 인덱스로 사용합니다.
chart_data = {
    movie["movieNm"]: movie["audiCnt"]
    for movie in top5
}

st.bar_chart(
    chart_data,
    horizontal=True,
    x_label="관객수",
    y_label="영화",
)


# ---------------------------------------------------------
# 9. 전체 박스오피스 표
# ---------------------------------------------------------

st.subheader("🎞️ 전체 순위")

# 화면에 보여줄 컬럼만 골라서 새로운 표를 만듭니다.
table_data = []

for movie in movies:
    table_data.append(
        {
            "순위": movie["rank"],
            "영화명": movie["movieNm"],
            "개봉일": movie.get("openDt", "-") or "-",
            "관객수": f"{movie['audiCnt']:,}",
            "누적관객": f"{movie['audiAcc']:,}",
            "스크린수": f"{movie['scrnCnt']:,}",
        }
    )


# Streamlit dataframe을 사용해 표를 보여줍니다.
st.dataframe(
    table_data,
    use_container_width=True,
    hide_index=True,
    column_config={
        "순위": st.column_config.NumberColumn(
            "순위",
            width="small",
        ),
        "영화명": st.column_config.TextColumn(
            "영화명",
            width="large",
        ),
        "개봉일": st.column_config.TextColumn(
            "개봉일",
            width="medium",
        ),
        "관객수": st.column_config.TextColumn(
            "관객수",
            width="medium",
        ),
        "누적관객": st.column_config.TextColumn(
            "누적관객",
            width="medium",
        ),
        "스크린수": st.column_config.TextColumn(
            "스크린수",
            width="medium",
        ),
    },
)


# ---------------------------------------------------------
# 10. 데이터 출처 안내
# ---------------------------------------------------------

st.caption(
    "데이터 출처: 영화진흥위원회 영화관입장권통합전산망(KOBIS) "
    "일일 박스오피스 API"
)

