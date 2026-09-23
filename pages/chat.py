import os
import streamlit as st
from openai import OpenAI

# 페이지 제목 설정
st.title("🦖 아기 공룡과의 대화")
st.write("지구에 막 떨어진 9살 공룡 친구와 이야기를 나눠보세요!")

# Streamlit secrets 또는 환경 변수에서 API 키 불러오기
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

# API 키가 설정되지 않은 경우 처리
if not api_key:
    st.error("API 키를 찾을 수 없습니다. .streamlit/secrets.toml 파일에 GEMINI_API_KEY를 설정해 주세요.")
    st.stop()

# OpenAI 클라이언트 초기화 (Gemini 호환 API 엔드포인트 사용)
client = OpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

# AI 시스템 프롬프트 (공룡 페르소나 설정)
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "너는 갑자기 지구에 떨어진 9살 공룡이야. "
        "어려운 말은 공룡 울음소리로 바꿔 주고, 반드시 순수 한국어로만 답해."
    )
}

# 세션 상태에 대화 기록 보관용 리스트가 없으면 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [SYSTEM_PROMPT]

# 화면에 이전 대화 내용 표시 (시스템 프롬프트는 제외)
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# 사용자 입력창
if user_input := st.chat_input("공룡에게 말을 건네보세요..."):
    # 1. 사용자 메시지를 화면에 표시
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. 대화 기록에 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 3. AI 답변 생성 및 실시간 스트리밍 출력
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            # Gemini API 호출 (실시간 스트리밍 설정)
            response = client.chat.completions.create(
                model="gemini-3.5-flash-lite",
                messages=st.session_state.messages,
                stream=True
            )

            # 답변 글자가 실시간으로 나오는 과정 처리
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + "▌")
            
            # 최종 완성된 답변 표시
            message_placeholder.markdown(full_response)

            # 4. 대화 기록에 AI 답변 추가 (이전 대화 기억용)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception:
            # 요청 실패 시 빨간 에러 화면 대신 깔끔한 한국어 안내 출력
            message_placeholder.markdown("공룡이 지금 으르렁거리며 딴청을 피우고 있어요. 잠시 후 다시 시도해 주세요!")
