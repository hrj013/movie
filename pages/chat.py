import streamlit as st
from openai import OpenAI

# Streamlit 페이지 기본 설정 (제목 지정)
st.title("💬 예주와의 대화")

# 비밀 금고(st.secrets)에서 API 키 불러오기
api_key = st.secrets.get("GEMINI_API_KEY")

# API 키가 설정되지 않은 경우 처리
if not api_key:
    st.info("API 키를 찾을 수 없어. .streamlit/secrets.toml 파일에 GEMINI_API_KEY를 설정해 줘.")
    st.stop()

# OpenAI 클라이언트 초기화 (Gemini 호환 API 주소 연결)
client = OpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

# AI 페르소나(성격) 설정 - 화면에는 표시되지 않고 AI 내부 동작 시에만 전달됨
SYSTEM_PROMPT = {
    "role": "system",
    "content": "너는 예주야. 나보다 한 살 어리지만 많이 성숙하고 반말 써. 약간 시니컬하고 쿨해 한국인이야. 근데 예주는 한 번 대답할 때 미사여구를 한 두 개만 붙여. 그리고 생각보다는 착한데 남한테 그렇게 관심이 많지는 않아. mbti는 estj야. 못말린다니까 같은 말은 안해. 오글거리는 말도 안해. 현실적이야. 숙제 물어보면 숙제 알려주기 전에 왜 아직도 몰라 이런 식으로 말해."
}

# 세션 상태(st.session_state)에 대화 기록 리스트가 없으면 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [SYSTEM_PROMPT]

# 화면에 이전 대화 목록 출력 (시스템 프롬프트는 노출하지 않음)
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# 채팅 입력창 구현
if user_input := st.chat_input("예주에게 할 말을 입력해..."):
    # 1. 사용자가 입력한 메시지를 화면 말풍선으로 표시
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. 대화 기억을 위해 사용자 메시지를 기록에 추가
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 3. AI 답변 생성을 위한 말풍선 및 실시간 스트리밍 출력 준비
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            # Gemini API 호출 (요청된 모델명 및 스트리밍 옵션 적용)
            response = client.chat.completions.create(
                model="gemini-3.5-flash-lite",
                messages=st.session_state.messages,
                stream=True
            )

            # 답변 텍스트 조각을 한 글자씩 받아와 실시간 출력
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + "▌")
            
            # 완성된 커서 없는 최종 답변 출력
            message_placeholder.markdown(full_response)

            # 4. 연속된 대화를 기억하도록 AI의 답변도 기록에 저장
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception:
            # API 요청 실패 시 빨간 에러창 대신 한국어 안내 한 줄 표시
            message_placeholder.markdown("네트워크 연결이 불안정하거나 예주가 잠시 응답할 수 없는 상태야. 나중에 다시 시도해 줘.")
