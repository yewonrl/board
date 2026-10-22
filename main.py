
import json
import re
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# --------------------------------------------------
# 기본 설정
# --------------------------------------------------
st.set_page_config(
    page_title="전국 고령화 단계구분도",
    page_icon="🗺️",
    layout="wide",
)

POPULATION_URL = (
    "https://raw.githubusercontent.com/yewonrl/borad//main/"
    "population_ts_yearly_gender.zip"
)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/yewonrl/board//main/"
    "sigungu_kr.geojson"
)

st.title("전국 시군구 고령화 단계구분도")
st.caption("2026년 6월 기준 · 65세 이상 인구 비율 · 시군구 코드 기준")


# --------------------------------------------------
# 데이터 다운로드 및 로딩
# --------------------------------------------------
@st.cache_data(show_spinner="인구 데이터와 행정구역 경계를 불러오는 중...")
def load_data():
    # 압축 CSV 읽기
    pop_response = requests.get(POPULATION_URL, timeout=120)
    pop_response.raise_for_status()

    population = pd.read_csv(
        BytesIO(pop_response.content),
        compression="zip",
        dtype={"코드": "string"},
        low_memory=False,
    )

    # GeoJSON 읽기
    geo_response = requests.get(GEOJSON_URL, timeout=120)
    geo_response.raise_for_status()
    geojson = geo_response.json()

    # 코드 형식을 문자열로 통일하고 앞자리 0 보존
    population["코드"] = (
        population["코드"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(10)
    )

    # 2026년 데이터만 사용
    population["연도"] = pd.to_numeric(
        population["연도"], errors="coerce"
    )
    population = population.loc[
        population["연도"].eq(2026)
    ].copy()

    if population.empty:
        raise ValueError("인구 데이터에서 2026년 자료를 찾을 수 없습니다.")

    # 계_로 시작하는 열만 사용. 남_ / 여_ 열은 합산하지 않음.
    total_cols = [
        c for c in population.columns
        if c.startswith("계_")
    ]

    # 계_65세 ~ 계_99세 및 계_100세 이상
    elderly_cols = [
        c for c in total_cols
        if (
            re.fullmatch(r"계_(?:[6-9]\d|100)세", c)
            and int(c.split("_")[1][:-1]) >= 65
        ) or c == "계_100세 이상"
    ]

    if not total_cols:
        raise ValueError("'계_'로 시작하는 인구 열이 없습니다.")

    if not elderly_cols:
        raise ValueError("65세 이상 인구 열을 찾을 수 없습니다.")

    # 문자열 숫자도 안전하게 숫자로 변환
    for col in set(total_cols):
        population[col] = pd.to_numeric(
            population[col], errors="coerce"
        ).fillna(0)

    population["전체인구"] = population[total_cols].sum(axis=1)
    population["65세이상인구"] = population[elderly_cols].sum(axis=1)

    # 동 코드 앞 5자리로 시군구 집계
    population["시군구코드"] = population["코드"].str[:5]

    grouped = (
        population.groupby("시군구코드", as_index=False)
        .agg(
            전체인구=("전체인구", "sum"),
            **{"65세이상인구": ("65세이상인구", "sum")},
        )
    )

    grouped["고령화율"] = np.where(
        grouped["전체인구"] > 0,
        grouped["65세이상인구"] / grouped["전체인구"] * 100,
        np.nan,
    )

    # GeoJSON의 코드도 문자열로 정규화
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        code = str(props.get("코드", "")).strip()
        code = re.sub(r"\.0$", "", code)
        props["코드"] = code.zfill(5)

    # GeoJSON의 코드가 지도 결합 키
    rate_by_code = grouped.set_index("시군구코드")["고령화율"].to_dict()

    for feature in geojson["features"]:
        props = feature["properties"]
        props["고령화율"] = rate_by_code.get(props["코드"])

    # 지도와 표에 사용할 시군구 자료
    properties = pd.DataFrame([
        {
            "코드": f["properties"]["코드"],
            "시군구": f["properties"].get("시군구", ""),
            "시도": f["properties"].get("시도", ""),
            "고령화율": f["properties"].get("고령화율"),
        }
        for f in geojson["features"]
    ])

    result = properties.merge(
        grouped.rename(columns={"시군구코드": "코드"}),
        on="코드",
        how="left",
        suffixes=("", "_집계"),
    )

    return geojson, result


try:
    geojson, result = load_data()
except Exception as exc:
    st.error(f"데이터를 불러오거나 처리하지 못했습니다: {exc}")
    st.info(
        "원본 URL, CSV 열 이름, GeoJSON의 features/properties 구조를 "
        "확인해 주세요."
    )
    st.stop()


# --------------------------------------------------
# 요약 지표
# --------------------------------------------------
valid = result.dropna(subset=["고령화율"]).copy()

if valid.empty:
    st.error(
        "GeoJSON과 인구 데이터의 코드가 일치하지 않습니다. "
        "두 파일의 코드 형식과 2026년 자료를 확인해 주세요."
    )
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("매칭된 시군구", f"{len(valid):,}곳")
c2.metric("평균 고령화율", f"{valid['고령화율'].mean():.2f}%")
top = valid.loc[valid["고령화율"].idxmax()]
c3.metric("고령화율 최고", f"{top['시군구']} · {top['고령화율']:.2f}%")


# --------------------------------------------------
# 단계구분도
# --------------------------------------------------
st.subheader("시군구별 65세 이상 인구 비율")

fig = px.choropleth(
    valid,
    geojson=geojson,
    locations="코드",
    featureidkey="properties.코드",
    color="고령화율",
    color_continuous_scale="YlOrRd",
    range_color=(0, max(1, float(valid["고령화율"].max()))),
    hover_name="시군구",
    hover_data={
        "코드": False,
        "고령화율": ":.2f",
    },
    labels={"고령화율": "고령화율 (%)"},
)

# 타일 배경 없이 GeoJSON 경계만 표시
fig.update_geos(
    visible=False,
    fitbounds="locations",
    showcountries=False,
    showcoastlines=False,
    showland=False,
    showframe=False,
    bgcolor="rgba(0,0,0,0)",
)

fig.update_traces(
    marker_line_color="white",
    marker_line_width=0.45,
    hovertemplate=(
        "<b>%{hovertext}</b><br>"
        "고령화율: %{z:.2f}%"
        "<extra></extra>"
    ),
)

fig.update_layout(
    height=760,
    margin=dict(l=0, r=0, t=20, b=0),
    coloraxis_colorbar=dict(
        title="고령화율 (%)",
        ticksuffix="%",
    ),
)

st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------
# 데이터 표
# --------------------------------------------------
st.subheader("시군구별 고령화율 데이터")

search = st.text_input("시군구 검색", placeholder="예: 수원, 강남, 제주")
table = valid[
    ["코드", "시도", "시군구", "전체인구", "65세이상인구", "고령화율"]
].copy()

if search.strip():
    mask = (
        table["시도"].astype(str).str.contains(search, case=False, na=False)
        | table["시군구"].astype(str).str.contains(search, case=False, na=False)
        | table["코드"].astype(str).str.contains(search, case=False, na=False)
    )
    table = table.loc[mask]

table = table.sort_values("고령화율", ascending=False)
table["고령화율"] = table["고령화율"].round(2)

st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "전체인구": st.column_config.NumberColumn(format="%d"),
        "65세이상인구": st.column_config.NumberColumn(format="%d"),
        "고령화율": st.column_config.NumberColumn(format="%.2f%%"),
    },
)

st.download_button(
    "집계 결과 CSV 다운로드",
    data=table.to_csv(index=False).encode("utf-8-sig"),
    file_name="sigungu_aging_rate_2026.csv",
    mime="text/csv",
)
