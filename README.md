# 🏥 HOS - 일본 응급 의료 챗봇

일본 여행자를 위한 AI 기반 응급 의료 조언 시스템입니다.

## ✨ 주요 기능

### 🤖 AI 기반 진단
- **Vision AI**: 상처/화상 이미지 분석
- **RAG 시스템**: 일본 의료 데이터 기반 조언
- **규칙 기반 시스템**: 기본 응급처치 가이드

### 📍 위치 기반 서비스
- **병원 검색**: 근처 응급실 찾기
- **약국 검색**: OTC 의약품 구매처 안내
- **지도 연동**: Google Maps 링크 제공

### 💊 의약품 정보
- **OTC 추천**: 증상별 적합한 의약품
- **일본어 문장**: 약국에서 사용할 수 있는 표현
- **브랜드 매핑**: 실제 구매 가능한 제품명

### 🔍 자동 데이터 확장
- **증상 로깅**: 사용자 입력 자동 기록
- **미처리 증상 분석**: 처리되지 않은 증상 우선순위 결정
- **자동 크롤링**: 일본 의료 사이트에서 데이터 수집
- **RAG 업데이트**: 새로운 데이터 자동 통합

## 🚀 설치 및 실행 (FastAPI)

### 1) 저장소 클론
```bash
git clone https://github.com/PARKYUNSU/hos.git
cd hos
```

### 2) 의존성 설치
```bash
pip install -r requirements.txt
# (옵션) Playwright 브라우저 설치
python -m playwright install chromium --with-deps
```

### 3) 환경변수 설정 (.env)
```env
OPENAI_API_KEY=sk-...
USE_PLAYWRIGHT_CRAWLING=1
PW_HEADLESS=1
PW_WAIT_UNTIL=networkidle
# 응급 이미지 탐지 임계값
IMG_RED_RATIO=0.25
IMG_BURN_RATIO=0.30
# 테스트 모드(위치)
MVP_RANDOM_TOKYO=false
MVP_FIXED_SHINJUKU=false
MVP_FIXED_LAT=35.6762
MVP_FIXED_LON=139.6503
# RAG 자동 재색인
AUTO_REINDEX_ON_CRAWL=0
REINDEX_DEBOUNCE_SEC=120
```

### 4) 앱 실행
```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 5) 확인
- 메인: http://127.0.0.1:8000/
- 관리자: http://127.0.0.1:8000/admin
- 헬스: http://127.0.0.1:8000/api/health

## 📊 관리자 대시보드

### 기능
- **증상 로그 모니터링**: 사용자 입력 및 응답 품질 분석
- **미처리 증상 관리**: 처리되지 않은 증상 우선순위 설정
- **크롤링 관리**: 자동/수동 데이터 수집
- **RAG 데이터 관리**: 지식베이스 업데이트 및 통계
- **시스템 설정**: 환경변수 및 데이터베이스 관리

### 접속
- 관리자: `http://localhost:8000/admin` (HTTP Basic, `.env`의 `ADMIN_USER`/`ADMIN_PASS`)
- 시간대: 모든 로그/대시보드 표시는 KST(Asia/Seoul)

## 🔄 자동화 시스템

### 스케줄러 기능
- **매 시간**: 미처리 증상 자동 크롤링
- **매 6시간**: RAG 시스템 자동 업데이트
- **매일 자정**: 시스템 정리 및 백업
- **매 30분**: 시스템 상태 확인

### 데이터 수집
- **MHLW (厚生労働省)**: 일본 정부 의료 정보
- **JMA (日本医師会)**: 일본 의사회 응급처치 가이드
- **JRC (日本赤十字社)**: 일본 적십자사 응급처치 매뉴얼

## 📁 프로젝트 구조 (요약)

```
hos/
├── backend/
│   ├── services_gen.py
│   ├── services_rag.py
│   ├── services_logging.py
│   ├── services_auto_crawler.py
│   ├── services_playwright_crawler.py
│   ├── services_pdf_processor.py
│   └── otc_rules.py
├── data/
│   ├── rag_data/               # RAG 문서(PDF/TXT)
│   └── symptom_logs.db         # SQLite 로그
├── static/
│   ├── js/app.js
│   ├── js/admin.js
│   └── css/*
├── templates/
│   ├── index.html              # 메인 UI
│   └── admin.html              # 관리자 UI
├── main.py                     # FastAPI 앱
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🌐 배포

### Docker Compose (권장)
```bash
# 서버에서
docker compose build
docker compose up -d
curl -sS http://127.0.0.1:8000/api/health
```

### Nginx 리버스 프록시 (예시)
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300;
    }

    location /admin {
        auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd_admin;
        proxy_pass http://127.0.0.1:8000/admin;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 🔧 개발

### 로컬 개발
```bash
# 메인 앱
streamlit run ui/app.py --server.port 8501

# 관리자 대시보드
python run_admin.py

# 스케줄러 (백그라운드)
nohup python scheduler.py &
```

### 테스트
```bash
# 환경변수 테스트
python test_env.py

# 관리자 대시보드 테스트
python setup_env.py
```

## 📈 모니터링

### 로그 파일
- `logs/scheduler.log`: 스케줄러 실행 로그
- `data/symptom_logs.db`: 증상 로그 데이터베이스

### 통계 확인
- 관리자 대시보드에서 실시간 통계 확인
- 증상 처리 성공률 모니터링
- RAG 데이터 품질 분석

## 🚀 향후 고도화 계획

현재 프로젝트는 핵심 기능 구현이 완료되었으며, 더욱 정교한 의료 지원 서비스로 발전시키기 위해 다음과 같은 추가 기술 도입을 계획하고 있습니다:

### AI 모델 고도화
- **다중 LLM 통합**: 다양한 대규모 언어 모델의 장점을 결합한 앙상블 시스템
- **의료 전문 모델**: 의료 도메인에 특화된 파인튜닝된 모델 활용
- **멀티모달 융합**: 텍스트, 이미지, 음성을 통합한 종합적 증상 분석

### 실시간 데이터 연동
- **의료 기관 API**: 일본 주요 병원 및 약국의 실시간 데이터 연동
- **의약품 데이터베이스**: 정부 승인 의약품 정보 실시간 업데이트
- **응급실 현황**: 실시간 병상 및 대기시간 정보 제공

### 개인화 및 학습
- **사용자 프로필**: 개인 의료 이력 기반 맞춤형 조언
- **연속 학습**: 사용자 피드백을 통한 모델 성능 지속 개선
- **예측 분석**: 증상 패턴 분석을 통한 예방적 의료 조언

## 🤝 기여

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 라이선스

MIT License

## 🆘 지원

문제가 발생하면 GitHub Issues에 문의해주세요.

---

**주의**: 이 시스템은 의료 조언을 제공하지만, 실제 의료진의 진단을 대체할 수 없습니다. 응급상황에서는 즉시 119에 연락하세요.