import json
import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# 페이지 설정
st.set_page_config(page_title="전국 고령화 단계구분도 (2026년)", layout="wide")


# 데이터 로드 (캐싱을 통해 속도 optimiized)
@st.cache_data
def load_data():
    # 1. 인구 데이터 불러오기 (압축 Zip CSV)
    pop_url = "https://raw.githubusercontent.com/yewonrl/contents//main/population_ts_yearly_gender.zip"
    df = pd.read_csv(pop_url, compression="zip")

    # 코드를 문자열로 변환하고 8자리(앞의 0 보장) 지정
    df["코드"] = df["코드"].astype(str).str.zfill(8)

    # 2026년 데이터 필터링
    df_2026 = df[df["연도"] == 2026].copy()

    # 시군구 코드 추출 (앞 5자리)
    df_2026["sigungu_code"] = df_2026["코드"].str[:5]

    # '계_'로 시작하는 컬럼만 추출 (전체 인구용)
    total_cols = [col for col in df_2026.columns if col.startswith("계_")]

    # 65세 이상 컬럼 추출 ('계_65세' ~ '계_100세 이상')
    over65_cols = []
    for col in total_cols:
        age_str = col.replace("계_", "").replace("세", "").replace(" 이상", "")
        if age_str.isdigit() and int(age_str) >= 65:
            over65_cols.append(col)

    # 행별 총인구 및 65세 이상 인구 계산
    df_2026["총인구"] = df_2026[total_cols].sum(axis=1)
    df_2026["고령인구"] = df_2026[over65_cols].sum(axis=1)

    # 시군구(앞 5자리) 단위 집계
    grouped = (
        df_2026.groupby("sigungu_code")[["총인구", "고령인구"]]
        .sum()
        .reset_index()
    )

    # 고령화율(%) 계산
    grouped["고령화율"] = np.where(
        grouped["총인구"] > 0,
        (grouped["고령인구"] / grouped["총인구"]) * 100,
        0,
    )
    grouped["고령화율"] = grouped["고령화율"].round(2)

    # 2. GeoJSON 데이터 불러오기 (requests)
    geojson_url = "https://raw.githubusercontent.com/first2022-cyber/contents//main/sigungu_kr.geojson"
    res = requests.get(geojson_url)
    geojson_data = res.json()

    # GeoJSON의 '코드' 속성을 문자열 5자리로 정렬
    for feature in geojson_data["features"]:
        feature["properties"]["코드"] = str(
            feature["properties"]["코드"]
        ).zfill(5)

    # 마우스 오버 시 표시할 시군구 및 시도 이름 매핑
    geo_properties = [f["properties"] for f in geojson_data["features"]]
    geo_df = pd.DataFrame(geo_properties)
    geo_df["코드"] = geo_df["코드"].astype(str).str.zfill(5)

    # 결합
    final_df = pd.merge(
        grouped,
        geo_df[["코드", "시도", "시군구"]],
        left_on="sigungu_code",
        right_on="코드",
        how="inner",
    )

    return final_df, geojson_data


# UI 구성
st.title("🗺️ 2026년 전국 시군구별 고령화 단계구분도")
st.markdown("전국 시군구별 65세 이상 고령인구 비율(%) 시각화 지도입니다.")

with st.spinner("데이터를 로딩하고 지도를 생성 중입니다..."):
    df_map, geojson_kr = load_data()

# Plotly Choropleth 생성
fig = px.choropleth_mapbox(
    df_map,
    geojson=geojson_kr,
    locations="sigungu_code",
    featureidkey="properties.코드",
    color="고령화율",
    color_continuous_scale="Reds",
    range_color=(df_map["고령화율"].min(), df_map["고령화율"].max()),
    mapbox_style="white-bg",  # 배경 타일 지도를 없애고 경계만 표시
    center={"lat": 35.9, "lon": 127.8},
    zoom=6.2,
    hover_name="시군구",
    hover_data={
        "sigungu_code": False,
        "시도": True,
        "고령화율": ":.2f%",
        "총인구": ":,명",
        "고령인구": ":,명",
    },
    labels={"고령화율": "고령화율(%)", "총인구": "총인구", "고령인구": "65세 이상 인구"},
)

# 지역 경계선 및 레이아웃 설정
fig.update_traces(marker_line_width=0.8, marker_line_color="gray")
fig.update_layout(
    margin={"r": 0, "t": 20, "l": 0, "b": 0},
    height=750,
)

# 스트림릿 출력
st.plotly_chart(fig, use_container_width=True)
