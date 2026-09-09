from datetime import datetime, timedelta
import zoneinfo
import pandas as pd
import requests
import streamlit as st

# 스트림릿 페이지 기본 설정 (타이틀 지정 및 넓은 화면 레이아웃 적용)
st.set_page_config(page_title="어제 박스오피스", layout="wide")


# 동일한 날짜 요청 시 API를 다시 부르지 않고 1시간(3600초) 동안 결과를 기억하는 캐시 함수
@st.cache_data(ttl=3600)
def fetch_daily_box_office(api_key: str, target_date: str):
    """KOBIS 오픈 API를 호출하여 dailyBoxOfficeList 데이터를 가져옵니다."""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        # 네트워크 응답 코드가 200 OK가 아니면 예외를 발생시킵니다.
        response.raise_for_status()
        data = response.json()
        return data, None
    except Exception as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


def main():
    st.title("🎬 어제 일별 박스오피스")

    # 1. 비밀 금고(st.secrets)에서 KOBIS_KEY 가져오기
    if "KOBIS_KEY" not in st.secrets:
        st.error("🔑 Secrets(비밀 금고) 설정이 필요합니다.")
        st.info(
            "Streamlit Cloud의 [App Settings] > [Secrets] 메뉴 또는 "
            "로컬 환경의 `.streamlit/secrets.toml` 파일에 `KOBIS_KEY = '발급받은키'`를 등록해 주세요."
        )
        return

    api_key = st.secrets["KOBIS_KEY"]

    # 2. 배포 서버 시계(UTC 등)와 관계없이 한국 시간(Asia/Seoul) 기준 '어제' 날짜 계산
    tz_seoul = zoneinfo.ZoneInfo("Asia/Seoul")
    now_seoul = datetime.now(tz_seoul)
    yesterday_seoul = now_seoul - timedelta(days=1)
    
    target_dt = yesterday_seoul.strftime("%Y%m%d")  # API 요청용 (예: YYYYMMDD 여덟 자리)
    display_date = yesterday_seoul.strftime("%Y년 %m월 %d일")  # 화면 표시용

    st.subheader(f"📅 기준일: {display_date} ({target_dt})")

    # 3. KOBIS API 데이터 조회 (캐싱 적용)
    data, error_msg = fetch_daily_box_office(api_key, target_dt)

    # 예외 처리 1: 네트워크 요청 자체가 실패했을 때
    if error_msg:
        st.error(error_msg)
        st.info("💡 인터넷 연결 상태를 확인하거나 잠시 후 다시 시도해 주세요.")
        return

    # 예외 처리 2: API 인증키 오류 등으로 faultInfo 상자가 들어왔을 때
    if "faultInfo" in data:
        st.error("❌ API 응답 오류가 발생했습니다.")
        fault_msg = data["faultInfo"].get("message", "알 수 없는 오류")
        st.warning(f"오류 메시지: {fault_msg}")
        st.info(
            "💡 Secrets에 등록된 `KOBIS_KEY` 인증키가 올바른지, "
            "KOBIS 오픈 API 웹사이트에서 키가 정상 활성화되어 있는지 확인해 주세요."
        )
        return

    # 예외 처리 3: 응답은 정상이나 영화 목록이 비어서 왔을 때
    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])

    if not daily_list:
        st.warning("⚠️ 해당 날짜의 박스오피스 데이터가 비어 있습니다.")
        st.info(
            "💡 아직 해당 날짜의 집계가 완료되지 않았거나 KOBIS 서비스 점검 중일 수 있습니다. 잠시 후 다시 조회해 주세요."
        )
        return

    # 4. 데이터프레임 변환 및 문자열 숫자를 정수형(int)으로 변경
    df = pd.DataFrame(daily_list)

    # API에서 문자열로 전달되는 수치형 데이터 변환
    numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # 관객수 및 순위 기준 정렬 (1위~10위)
    df = df.sort_values(by="rank", ascending=True).reset_index(drop=True)

    # 5. 1위 영화 하이라이트 지표 카드 3개 크게 출력
    top_1 = df.iloc[0]
    st.markdown(f"### 🥇 1위 영화: **{top_1['movieNm']}**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="어제 관객수", value=f"{top_1['audiCnt']:,} 명")
    with col2:
        st.metric(label="누적 관객수", value=f"{top_1['audiAcc']:,} 명")
    with col3:
        st.metric(label="스크린수", value=f"{top_1['scrnCnt']:,} 개")

    st.divider()

    # 6. 관객수 상위 5편 막대그래프 시각화 (관객수/순위 순서대로 정렬 유지)
    st.subheader("📊 관객수 상위 5개 영화 (1위 ~ 5위 순)")
    top_5_df = df.head(5).copy()

    # 순위와 영화명을 결합한 항목명 생성 (예: "1위 영화명")
    top_5_df["rank_movie"] = top_5_df["rank"].astype(str) + "위 " + top_5_df["movieNm"]

    # 스트림릿 그래프가 알파벳/가나다순으로 자동 재정렬되는 것을 방지하기 위해 범주형 순서 고정
    top_5_df["rank_movie"] = pd.Categorical(
        top_5_df["rank_movie"], categories=top_5_df["rank_movie"], ordered=True
    )

    # 막대그래프 출력 (x축: 순위+영화명, y축: 어제 관객수)
    st.bar_chart(data=top_5_df, x="rank_movie", y="audiCnt", color="#FF4B4B")

    st.divider()

    # 7. 전체 순위표 출력
    st.subheader("📋 전체 순위표")

    # 요구 조건 항목만 선택 및 한글 컬럼명 설정
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

    # 숫자에 단위 및 천 단위 쉼표 서식을 적용하여 테이블 표시
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
