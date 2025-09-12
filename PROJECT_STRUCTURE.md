# 프로젝트 구조 (HOS - Hospital On Site)

## 📁 핵심 애플리케이션
```
hos/
├── ui/                          # 사용자 인터페이스
│   ├── app.py                   # 메인 Streamlit 앱 (로컬용)
│   ├── app_deploy.py            # 배포용 Streamlit 앱
│   └── app_original.py          # 원본 백업
├── backend/                     # 백엔드 서비스
│   ├── main.py                  # FastAPI 서버 (별도 실행용)
│   ├── services_advanced_rag.py # 고도화된 RAG 시스템
│   ├── services_gen.py          # LLM 생성 서비스
│   ├── services_auto_crawler.py # 자동 크롤링 서비스
│   ├── services_logging.py      # 로깅 서비스
│   └── ...                      # 기타 서비스들
└── admin_dashboard.py           # 관리자 대시보드
```

## 📁 데이터 및 설정
```
data/
├── passages/jp/                 # 일본 의료 문서 (RAG 데이터)
├── cache/embeddings/            # 임베딩 캐시
├── symptom_logs.db              # 사용자 증상 로그
└── radar/                       # RAD-AR 의약품 데이터
```

## 📁 정적 파일
```
static/
└── otc/                         # OTC 약물 이미지
    ├── *.svg                    # 기본 SVG 이미지
    └── jp/                      # 일본 약물 이미지
```

## 📁 실험 및 테스트
```
experiments/                     # 실험 파일들
├── test_100_symptoms.py         # 100가지 증상 테스트
├── rag_llm_analyzer.py          # RAG-LLM 차이 분석
├── integrate_new_rules.py       # 규칙 통합 스크립트
└── test_results_*.json          # 테스트 결과
```

## 📁 스크립트 및 유틸리티
```
scripts/                         # 실행 스크립트들
├── run_admin.py                 # 관리자 대시보드 실행
├── scheduler.py                 # 스케줄러
├── setup_env.py                 # 환경 설정
└── simulate_user_activity.py    # 사용자 활동 시뮬레이션
```

## 📁 문서
```
docs/                            # 프로젝트 문서
├── DEPLOYMENT.md                # 배포 가이드
├── future_intelligent_system.md # 미래 시스템 로드맵
└── STREAMLIT_DEPLOYMENT.md      # Streamlit 배포 가이드
```

## 📁 데이터 수집
```
ingest/                          # 데이터 수집 도구
├── ingest.py                    # 메인 수집 스크립트
├── otc_image_crawler.py         # OTC 이미지 크롤러
└── seeds_jp.yml                 # 일본 시드 데이터
```

## 📁 설정 파일
```
├── requirements.txt             # 전체 의존성
├── requirements_minimal.txt     # 최소 의존성 (배포용)
├── requirements_admin.txt       # 관리자 도구 의존성
├── .streamlit/                  # Streamlit 설정
│   ├── config.toml
│   └── secrets.toml
└── .gitignore                   # Git 무시 파일
```

## 🚀 실행 방법

### 로컬 개발
```bash
# 메인 앱 실행
streamlit run ui/app.py

# 관리자 대시보드
python admin_dashboard.py

# 백엔드 서버 (별도)
python backend/main.py
```

### 배포
```bash
# Streamlit Cloud 배포용
streamlit run ui/app_deploy.py
```

## 🔧 주요 기능

1. **RAG + LLM 하이브리드 시스템**: 의료 문서 검색 + AI 조언 생성
2. **자동 학습**: 사용자 피드백 기반 지속적 개선
3. **다국어 지원**: 한국어, 영어, 일본어
4. **이미지 분석**: VLM을 통한 증상 이미지 분석
5. **자동 크롤링**: 실패한 쿼리 자동 데이터 수집
6. **관리자 대시보드**: 시스템 모니터링 및 관리

## 📊 데이터 흐름

```
사용자 입력 → RAG 검색 → LLM 생성 → 규칙 적용 → 통합 조언
     ↓
로깅 → 자동 학습 → 시스템 개선
```
