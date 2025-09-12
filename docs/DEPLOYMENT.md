# 🚀 HOS 배포 가이드

## Streamlit Cloud 배포

### 1. 기본 배포 (권장)
```bash
# 메인 앱만 배포
streamlit run ui/app_deploy.py
```

### 2. 환경변수 설정
Streamlit Cloud 대시보드에서 다음 환경변수를 설정하세요:

```toml
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
```

### 3. 배포 파일 선택
- **메인 앱**: `ui/app_deploy.py` (로깅 기능 제외, 안정적)
- **전체 앱**: `ui/app.py` (모든 기능 포함, 복잡함)

### 4. 의존성 파일
- **기본**: `requirements.txt` (모든 기능)
- **최소**: `requirements_minimal.txt` (핵심 기능만)

## 로컬 개발

### 1. 메인 앱
```bash
streamlit run ui/app.py --server.port 8501
```

### 2. 관리자 대시보드
```bash
python run_admin.py
# http://localhost:8502
```

### 3. 자동화 스케줄러
```bash
python scheduler.py
```

## 문제 해결

### 1. 의존성 오류
- `requirements_minimal.txt` 사용
- Python 3.11 이하 사용 고려

### 2. 메모리 부족
- `FAST_MODE=true` 설정
- 불필요한 기능 비활성화

### 3. API 키 오류
- Streamlit Cloud Secrets 확인
- 로컬 `.env` 파일 확인

## 성능 최적화

### 1. 배포용 설정
- 로깅 기능 비활성화
- 관리자 기능 제거
- 최소 의존성 사용

### 2. 캐싱
- RAG 데이터 캐싱
- 지오 검색 결과 캐싱
- 이미지 분석 결과 캐싱

### 3. 타임아웃 설정
- API 호출 타임아웃
- 이미지 처리 타임아웃
- 지오 검색 타임아웃
