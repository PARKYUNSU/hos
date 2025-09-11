#!/usr/bin/env python3
"""
환경변수 테스트 스크립트
"""

import os
import sys

def test_environment():
    """환경변수 설정을 테스트합니다."""
    print("🔧 환경변수 설정 테스트")
    print("=" * 50)
    
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
    
    all_set = True
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {description} - 설정됨")
        else:
            print(f"❌ {var}: {description} - 설정되지 않음")
            all_set = False
    
    print("=" * 50)
    if all_set:
        print("🎉 모든 환경변수가 설정되어 있습니다!")
        return True
    else:
        print("⚠️ 일부 환경변수가 설정되지 않았습니다.")
        print("\nStreamlit Cloud에서 다음을 설정하세요:")
        print("Settings → Secrets → 다음 내용 추가:")
        print()
        print("[secrets]")
        print('OPENAI_API_KEY = "sk-your-openai-api-key-here"')
        print('IMG_RED_RATIO = "0.3"')
        print('IMG_BURN_RATIO = "0.2"')
        print('TRIAGE_API_URL = "https://your-triage-api-url.com"')
        print('MVP_RANDOM_TOKYO = "true"')
        print('MVP_FIXED_SHINJUKU = "false"')
        print('MVP_FIXED_LAT = "35.6762"')
        print('MVP_FIXED_LON = "139.6503"')
        print('FAST_MODE = "false"')
        return False

if __name__ == "__main__":
    success = test_environment()
    sys.exit(0 if success else 1)
