#!/usr/bin/env python3
"""
Streamlit Cloud 환경변수 설정 도우미 스크립트
"""

import os
import streamlit as st

def check_environment_variables():
    """환경변수 설정 상태를 확인합니다."""
    st.title("🔧 환경변수 설정 확인")
    
    required_vars = {
        "OPENAI_API_KEY": "OpenAI API 키",
        "IMG_RED_RATIO": "이미지 빨간색 임계값",
        "IMG_BURN_RATIO": "이미지 화상 임계값", 
        "TRIAGE_API_URL": "응급분류 API URL",
        "MVP_RANDOM_TOKYO": "MVP 랜덤 도쿄 모드",
        "MVP_FIXED_SHINJUKU": "MVP 고정 신주쿠 모드",
        "MVP_FIXED_LAT": "고정 위도",
        "MVP_FIXED_LON": "고정 경도",
        "FAST_MODE": "빠른 모드"
    }
    
    st.subheader("현재 환경변수 상태:")
    
    all_set = True
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            st.success(f"✅ {var}: {description} - 설정됨")
        else:
            st.error(f"❌ {var}: {description} - 설정되지 않음")
            all_set = False
    
    if all_set:
        st.success("🎉 모든 환경변수가 설정되어 있습니다!")
    else:
        st.warning("⚠️ 일부 환경변수가 설정되지 않았습니다.")
        st.info("Streamlit Cloud에서 Settings → Secrets에서 환경변수를 설정하세요.")
    
    # Streamlit Cloud Secrets 설정 가이드
    st.subheader("Streamlit Cloud Secrets 설정 방법:")
    st.code("""
[secrets]
OPENAI_API_KEY = "sk-your-openai-api-key-here"
IMG_RED_RATIO = "0.3"
IMG_BURN_RATIO = "0.2"
TRIAGE_API_URL = "https://your-triage-api-url.com"
MVP_RANDOM_TOKYO = "true"
MVP_FIXED_SHINJUKU = "false"
MVP_FIXED_LAT = "35.6762"
MVP_FIXED_LON = "139.6503"
FAST_MODE = "false"
    """, language="toml")

if __name__ == "__main__":
    check_environment_variables()
