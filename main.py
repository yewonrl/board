import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go


# --------------------------------------------------
# 1. 페이지 설정
# --------------------------------------------------
st.set_page_config(
    page_title="동네별 인구 피라미드",
    page_icon="🏘️",
    layout="wide",
)

# 따뜻한 색감의 화면 스타일
st.markdown(
    """
    <style>
    .stApp {
        background-color: #FFF9F2;
    }
    h1, h2, h3 {
        color: #6B4032;
    }
    div[data-testid="stMetric"] {
        background-color: #FFF0E2;
        border: 1px solid #F1D7C3;
        padding: 14px;
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# 2. 데이터 불러오기
# --------------------------------------------------
DATA_URL = (
    "https://raw.githubusercontent.com/yewonrl/borad/"
    "main/population_ts_yearly_gender.zip"
)


@st.cache_data(show_spinner="전국 인구 데이터를 불러오는 중입니다...")
def load_data():
    # ZIP 압축 파일을 pandas가 직접 풀어서 읽습니다.
    df = pd.read_csv(
        DATA_URL,
        compression="zip",
        encoding="utf-8-sig",
    )

    # 열 이름 양쪽의 불필요한 공백 제거
    df.columns = df.columns.astype(str).str.strip()

    # 연도는 숫자로 변환합니다.
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")

    # 연도가 없는 행은 제외하고 최신 연도만 선택합니다.
    df = df.dropna(subset=["연도"]).copy()
    df["연도"] = df["연도"].astype(int)

    latest_year = int(df["연도"].max())
    df = df[df["연도"] == latest_year].copy()

    # 지역 이름의 공백을 정리합니다.
    for col in ["시도", "시군구", "동"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    # 나이 라벨을 0세부터 100세 이상까지 순서대로 만듭니다.
    ages = [f"{age}세" for age in range(101)]
    ages[-1] = "100세 이상"

    # 인구 열은 숫자로 변환합니다.
    # 쉼표가 포함된 문자열도 처리할 수 있도록 합니다.
    population_cols = []
    for age in ages:
        population_cols.extend([f"남_{age}", f"여_{age}"])

    for col in population_cols:
        if col not in df.columns:
            # 데이터에 열이 없으면 오류 메시지를 표시할 수 있도록
            # 누락된 열은 0으로 채웁니다.
            df[col] = 0
        else:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "", regex=False),
                errors="coerce",
            ).fillna(0)

    return df, latest_year, ages


# --------------------------------------------------
# 3. 제목과 데이터 준비
# --------------------------------------------------
st.title("🏘️ 동네별 인구 피라미드")
st.caption(
    "우리 동네의 연령별 남녀 인구를 한눈에 살펴보세요."
)

try:
    df, latest_year, ages = load_data()
except Exception as e:
    st.error(
        "인구 데이터를 불러오지 못했습니다. "
        "데이터 주소와 인터넷 연결을 확인해 주세요."
    )
    st.exception(e)
    st.stop()

st.success(f"📅 분석 기준 연도: {latest_year}년")

if df.empty:
    st.warning("최신 연도에 해당하는 데이터가 없습니다.")
    st.stop()


# --------------------------------------------------
# 4. 시도 → 시군구 → 동 선택
# --------------------------------------------------
st.subheader("📍 지역 선택")

# 첫 번째 드롭다운: 시도
sido_list = sorted(df["시도"].unique().tolist())

if not sido_list:
    st.warning("선택할 수 있는 시도 데이터가 없습니다.")
    st.stop()

selected_sido = st.selectbox(
    "① 시도",
    options=sido_list,
    key="selected_sido",
)

# 선택한 시도에 해당하는 시군구만 표시합니다.
sido_df = df[df["시도"] == selected_sido]

sigungu_list = sorted(s
