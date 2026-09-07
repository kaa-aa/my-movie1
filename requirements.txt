from datetime import datetime, timedelta
import zoneinfo
import pandas as pd
import requests
import streamlit as st

# 페이지 기본 설정 (타이틀, 레이아웃)
st.set_page_config(page_title="어제 박스오피스", layout="wide")


# 1시간 동안 API 응답 결과를 메모리에 기억하는 캐시 함수
@st.cache_data(ttl=3600)
def fetch_daily_box_office(api_key: str, target_date: str):
    """KOBIS API를 호출하여 dailyBoxOfficeList 데이터를 반환합니다."""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        # 네트워크 응답 실패 시 예외 발생
        response.raise_for_status()
        data = response.json()
        return data, None
    except Exception as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


def main():
    st.title("🎬 어제 일별 박스오피스")

    # Streamlit Secrets에서 API 키 불러오기
    if "KOBIS_KEY" not in st.secrets:
        st.error("🔑 Secrets 설정이 필요합니다.")
        st.info(
            "Streamlit Cloud의 App Settings > Secrets 메뉴 또는 "
            "`.streamlit/secrets.toml` 파일에 `KOBIS_KEY = '발급받은키'`를 등록해 주세요."
        )
        return

    api_key = st.secrets["KOBIS_KEY"]

    # 한국 시간(Asia/Seoul) 기준으로 오늘 날짜를 구하고, '어제' 날짜 계산
    tz_seoul = zoneinfo.ZoneInfo("Asia/Seoul")
    now_seoul = datetime.now(tz_seoul)
    yesterday_seoul = now_seoul - timedelta(days=1)
    target_dt = yesterday_seoul.strftime("%Y%m%d")
    display_date = yesterday_seoul.strftime("%Y년 %m월 %d일")

    st.subheader(f"📅 기준일: {display_date} ({target_dt})")

    # API 데이터 가져오기
    data, error_msg = fetch_daily_box_office(api_key, target_dt)

    # 1. 네트워크 통신 에러 처리
    if error_msg:
        st.error(error_msg)
        st.info("💡 인터넷 연결 상태를 확인하거나 잠시 후 다시 시도해 주세요.")
        return

    # 2. API 인증키 오류(faultInfo) 처리
    if "faultInfo" in data:
        st.error("❌ API 응답 오류가 발생했습니다.")
        fault_msg = data["faultInfo"].get("message", "알 수 없는 오류")
        st.warning(f"오류 메시지: {fault_msg}")
        st.info(
            "💡 Secrets에 등록된 `KOBIS_KEY` 인증키가 올바른지, "
            "KOBIS 오픈API 웹사이트에서 키가 활성화되었는지 확인해 주세요."
        )
        return

    # 3. 데이터 목록 존재 여부 확인
    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])

    if not daily_list:
        st.warning("⚠️ 해당 날짜의 박스오피스 데이터가 비어 있습니다.")
        st.info(
            "💡 아직 집계가 완료되지 않았거나 KOBIS 서비스 점검 중일 수 있습니다. 잠시 후 다시 조회해 주세요."
        )
        return

    # 데이터프레임 변환 및 숫자형 데이터 정형화
    df = pd.DataFrame(daily_list)

    # 문자열로 들어온 숫자 데이터들을 정수형(int)으로 변환
    numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # 1위 영화 하이라이트 (지표 카드 3개 표시)
    top_1 = df.iloc[0]
    st.markdown(f"### 🥇 1위: **{top_1['movieNm']}**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="어제 관객수", value=f"{top_1['audiCnt']:,} 명"
        )
    with col2:
        st.metric(
            label="누적 관객수", value=f"{top_1['audiAcc']:,} 명"
        )
    with col3:
        st.metric(
            label="스크린수", value=f"{top_1['scrnCnt']:,} 개"
        )

    st.divider()

    # 관객수 상위 5편 막대그래프 시각화
    st.subheader("📊 관객수 상위 5개 영화")
    top_5_df = df.head(5).copy()
    # Streamlit 기본 막대그래프 사용 (x축: 영화명, y축: 관객수)
    st.bar_chart(data=top_5_df, x="movieNm", y="audiCnt", color="#FF4B4B")

    st.divider()

    # 전체 박스오피스 순위표 정리 및 출력
    st.subheader("📋 전체 순위표")

    # 화면에 보여줄 컬럼선택 및 이름 변경
    display_df = df[
        ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
    ].copy()
    display_df.columns = [
        "순위",
        "영화명",
        "개봉일",
        "관객수",
        "누적관객",
        "스크린수",
    ]

    # 표 화면 출력 (천 단위 쉼표 포맷 지정)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "관객수": st.column_config.NumberColumn(format="%d명"),
            "누적관객": st.column_config.NumberColumn(format="%d명"),
            "스크린수": st.column_config.NumberColumn(format="%d개"),
        },
    )


if __name__ == "__main__":
    main()
