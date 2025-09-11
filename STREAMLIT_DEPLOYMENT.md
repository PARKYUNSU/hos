# Streamlit Cloud 배포 가이드

## 환경변수 설정 방법

### 1. Streamlit Cloud 대시보드 접속
- https://share.streamlit.io/ 에서 로그인
- 배포된 앱 선택

### 2. Settings → Secrets 설정
다음 환경변수들을 추가하세요:

```toml
[secrets]
# OpenAI API 키 (필수)
OPENAI_API_KEY = "sk-your-openai-api-key-here"

# 이미지 분석 임계값
IMG_RED_RATIO = "0.3"
IMG_BURN_RATIO = "0.2"

# API URL
TRIAGE_API_URL = "https://your-triage-api-url.com"

# MVP 테스트 설정
MVP_RANDOM_TOKYO = "true"
MVP_FIXED_SHINJUKU = "false"
MVP_FIXED_LAT = "35.6762"
MVP_FIXED_LON = "139.6503"

# 빠른 모드 (RAG/지오 검색 건너뛰기)
FAST_MODE = "false"
```

### 3. 앱 재시작
환경변수 설정 후 앱이 자동으로 재시작됩니다.

## 현재 기능

✅ **완료된 기능:**
- 벌레 물림/말벌 쏘임 응급처치 가이드
- 응급처치 기본 가이드
- RAG 시스템 통합
- OpenAI Vision API 이미지 분석
- 일본 의료 데이터 크롤링

## 테스트 방법

1. **벌레 물림 테스트:**
   - 증상: "벌레에 물렸어요"
   - 예상 결과: 상세한 응급처치 가이드 제공

2. **말벌 쏘임 테스트:**
   - 증상: "말벌에 쏘였어요"
   - 예상 결과: 알레르기 반응 주의사항 및 응급처치

3. **이미지 업로드 테스트:**
   - 상처나 화상 사진 업로드
   - 예상 결과: OpenAI Vision API로 이미지 분석

## 문제 해결

### OpenAI API 키 오류
- Streamlit Cloud Secrets에서 OPENAI_API_KEY 확인
- API 키가 유효한지 확인

### RAG 검색 결과 없음
- data/passages/jp/ 폴더에 파일들이 있는지 확인
- 벌레 물림 관련 키워드로 검색 테스트

### 이미지 분석 오류
- OpenAI Vision API 사용량 확인
- 이미지 파일 형식 확인 (JPG, PNG 지원)
