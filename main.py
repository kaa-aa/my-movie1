from datetime import datetime, timedelta
import zoneinfo
import pandas as pd
import requests
import streamlit as st

# 페이지 기본 설정 (타이틀 지정 및 넓은 화면 레이아웃)
st.set_page_config(page_title="일별 박스오피스", layout="wide")


# 동일한 날짜 요청 시 1시간(3600초) 동안 결과를 기억하는 캐시 함수
@st.cache_data(ttl=3600)
def fetch_daily_box_office(api_key: str, target_date: str):
    """KOBIS 오픈 API를 호출하여 dailyBoxOfficeList 데이터를 가져옵니다."""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data, None
    except Exception as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


def main():
    st.title("🎬 일별 박스오피스 조회")

    # 1. Streamlit Secrets(비밀 금고)에서 KOBIS_KEY 가져오기
    if "KOBIS_KEY" not in st.secrets:
        st.error("🔑 Secrets(비밀 금고) 설정이 필요합니다.")
        st.info(
            "Streamlit Cloud의 App Settings > Secrets 메뉴 또는 "
            "로컬 환경의 `.streamlit/secrets.toml` 파일에 `KOBIS_KEY = '발급받은키'`를 등록해 주세요."
        )
        return

    api_key = st.secrets["KOBIS_KEY"]

    # 2. 한국 시간(Asia/Seoul) 기준 '어제' 날짜 계산 (선택 가능한 최대 날짜)
    tz_seoul = zoneinfo.ZoneInfo("Asia/Seoul")
    now_seoul = datetime.now(tz_seoul)
    yesterday_seoul = (now_seoul - timedelta(days=1)).date()

    # 사이드바에서 날짜를 선택할 수 있는 달력(date_input) 추가
    # min_value: KOBIS 제공 시작일 근처인 2004년 1월 1일로 설정
    selected_date = st.sidebar.date_input(
        "📅 조회할 날짜를 선택하세요",
        value=yesterday_seoul,
        max_value=yesterday_seoul,
        min_value=datetime(2004, 1, 1).date(),
    )

    target_dt = selected_date.strftime("%Y%m%d")  # API 요청용 (예: 20260908)
    display_date = selected_date.strftime("%Y년 %m월 %d일")  # 화면 표시용

    st.subheader(f"📅 조회 기준일: {display_date} ({target_dt})")

    # 3. KOBIS API 데이터 조회 (캐싱 적용)
    data, error_msg = fetch_daily_box_office(api_key, target_dt)

    # 예외 처리 1: 네트워크 요청 자체가 실패했을 때
    if error_msg:
        st.error(error_msg)
        st.info("💡 인터넷 연결 상태를 확인하거나 잠시 후 다시 시도해 주세요.")
        return

    # 예외 처리 2: API 인증키 오류 등으로 faultInfo 상자가 왔을 때
    if "faultInfo" in data:
        st.error("❌ API 응답 오류가 발생했습니다.")
        fault_msg = data["faultInfo"].get("message", "알 수 없는 오류")
        st.warning(f"오류 메시지: {fault_msg}")
        st.info(
            "💡 Secrets에 등록된 `KOBIS_KEY` 인증키가 올바른지, "
            "KOBIS 오픈 API 웹사이트에서 키가 정상 활성화되어 있는지 확인해 주세요."
        )
        return

    # 예외 처리 3: 선택한 날짜의 영화 목록이 비어 있을 때
    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])

    if not daily_list:
        st.warning("⚠️ 그날은 아직 집계 전입니다.")
        st.info("💡 집계가 아직 진행 중이거나 데이터가 존재하지 않는 날짜입니다. 다른 날짜를 선택해 주세요.")
        return

    # 4. 데이터프레임 변환 및 숫자형 변환
    df = pd.DataFrame(daily_list)

    # 문자열 숫자를 정수형(int)으로 변환
    numeric_columns = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # 순위 기준 정렬 (1위 ~ 10위)
    df = df.sort_values(by="rank", ascending=True).reset_index(drop=True)

    # 5. 요구조건 가공 처리
    # (1) 누적관객 100만 명 이상 영화명에 트로피(🏆) 표기
    def format_movie_name(row):
        movie_nm = row["movieNm"]
        if row["audiAcc"] >= 1000000:
            return f"🏆 {movie_nm}"
        return movie_nm

    df["display_movieNm"] = df.apply(format_movie_name, axis=1)

    # (2) 전날 대비 순위 증감(rankInten) 화살표 가공
    def format_rank_change(change):
        if change > 0:
            return f"🔺 {change}"  # 오른 영화 (빨간 위 화살표)
        elif change < 0:
            return f"🔹 {abs(change)}"  # 내린 영화 (파란 아래 화살표)
        else:
            return "-"  # 변동 없음

    df["rank_change"] = df["rankInten"].apply(format_rank_change)

    # 6. 1위 영화 하이라이트 (지표 카드 3개 표시)
    top_1 = df.iloc[0]
    st.markdown(f"### 🥇 1위 영화: **{top_1['display_movieNm']}**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="당일 관객수", value=f"{top_1['audiCnt']:,} 명")
    with col2:
        st.metric(label="누적 관객수", value=f"{top_1['audiAcc']:,} 명")
    with col3:
        st.metric(label="스크린수", value=f"{top_1['scrnCnt']:,} 개")

    st.divider()

    # 7. 관객수 상위 5편 막대그래프 시각화 (순위 순서대로 정렬 유지)
    st.subheader("📊 관객수 상위 5개 영화")
    top_5_df = df.head(5).copy()

    # 순위와 영화명 결합 (예: "1위 🏆 영화명")
    top_5_df["rank_movie"] = top_5_df["rank"].astype(str) + "위 " + top_5_df["display_movieNm"]

    # 가나다순 자동 정렬 방지를 위해 범주형 순서 고정
    top_5_df["rank_movie"] = pd.Categorical(
        top_5_df["rank_movie"], categories=top_5_df["rank_movie"], ordered=True
    )

    st.bar_chart(data=top_5_df, x="rank_movie", y="audiCnt", color="#FF4B4B")

    st.divider()

    # 8. 전체 박스오피스 순위표 출력
    st.subheader("📋 전체 순위표")

    display_df = df[
        ["rank", "rank_change", "display_movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
    ].copy()

    display_df.columns = [
        "순위",
        "순위변동",
        "영화명",
        "개봉일",
        "관객수",
        "누적관객",
        "스크린수",
    ]

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
