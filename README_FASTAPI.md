# HOS Emergency Medical Chatbot - FastAPI Version

일본 여행자를 위한 응급 의료 챗봇의 FastAPI 버전입니다. Streamlit의 제약사항을 해결하고 더 나은 배포 환경과 실시간 모니터링을 제공합니다.

## 🚀 주요 기능

### 사용자 기능
- **증상 입력**: 텍스트로 증상 설명
- **이미지 업로드**: 증상 사진 첨부 가능
- **위치 정보**: GPS 좌표 입력으로 지역별 의료 정보 제공
- **실시간 조언**: RAG + LLM 기반 의료 조언
- **OTC 약품 추천**: 일본 약국에서 구매 가능한 약품 정보

### 관리자 기능
- **실시간 로그 모니터링**: WebSocket 기반 실시간 로그 스트리밍
- **대시보드**: 시스템 현황, 통계, 성능 지표
- **로그 관리**: 증상 로그 조회, 필터링, 검색
- **RAG 관리**: 문서 업로드, 성능 분석, 재색인
- **환경 설정**: 실시간 환경 변수 변경

## 🏗️ 아키텍처

```
FastAPI Application
├── main.py                 # FastAPI 메인 애플리케이션
├── templates/              # HTML 템플릿
│   ├── index.html         # 사용자 인터페이스
│   └── admin.html         # 관리자 대시보드
├── static/                # 정적 파일
│   ├── css/               # 스타일시트
│   └── js/                # JavaScript
├── backend/               # 백엔드 서비스
│   ├── services_gen.py    # LLM 조언 생성
│   ├── services_rag.py    # RAG 시스템
│   ├── services_logging.py # 로깅 시스템
│   └── services_auto_crawler.py # 자동 크롤링
└── data/                  # 데이터 저장소
    ├── rag_data/          # RAG 문서
    └── symptom_logs.db    # SQLite 데이터베이스
```

## 📦 설치 및 실행

### 1. 환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd hos

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# Playwright 브라우저 설치
playwright install chromium
```

### 2. 환경 변수 설정

```bash
# 환경 변수 파일 복사
cp env.example .env

# .env 파일 편집
nano .env
```

필수 환경 변수:
- `OPENAI_API_KEY`: OpenAI API 키
- `AUTO_REINDEX_ON_CRAWL`: 자동 재색인 활성화 (1/0)
- `USE_PLAYWRIGHT_CRAWLING`: Playwright 크롤링 활성화 (1/0)

### 3. 실행

#### 개발 모드
```bash
python run_fastapi.py
```

#### 프로덕션 모드
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### Docker 실행
```bash
# Docker 이미지 빌드
docker build -t hos-app .

# Docker 컨테이너 실행
docker run -p 8000:8000 --env-file .env hos-app

# Docker Compose 실행
docker-compose up -d
```

## 🌐 접속 URL

- **메인 페이지**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs
- **관리자 대시보드**: http://localhost:8000/admin
- **헬스 체크**: http://localhost:8000/api/health

## 🔧 API 엔드포인트

### 사용자 API
- `POST /api/advice`: 의료 조언 요청
- `GET /api/health`: 헬스 체크

### 관리자 API
- `GET /api/logs`: 증상 로그 조회
- `GET /api/stats`: 시스템 통계
- `WebSocket /ws/logs`: 실시간 로그 스트리밍

## 📊 모니터링

### 실시간 모니터링
- WebSocket을 통한 실시간 로그 스트리밍
- 자동 크롤링 상태 모니터링
- RAG 성능 실시간 추적

### 대시보드 지표
- 총 로그 수
- 성공률
- RAG 신뢰도 분포
- 처리 시간 통계
- Playwright 상태

## 🚀 배포

### Docker 배포
```bash
# 프로덕션 이미지 빌드
docker build -t hos-app:prod .

# 컨테이너 실행
docker run -d \
  --name hos-app \
  -p 8000:8000 \
  --env-file .env \
  --restart unless-stopped \
  hos-app:prod
```

### Kubernetes 배포
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hos-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hos-app
  template:
    metadata:
      labels:
        app: hos-app
    spec:
      containers:
      - name: hos-app
        image: hos-app:prod
        ports:
        - containerPort: 8000
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: hos-secrets
              key: openai-api-key
```

### AWS/GCP/Azure 배포
- **AWS**: ECS, EKS, Lambda
- **GCP**: Cloud Run, GKE
- **Azure**: Container Instances, AKS

## 🔒 보안

### API 보안
- CORS 설정
- 요청 크기 제한
- 파일 업로드 검증
- SQL 인젝션 방지

### 환경 변수 보안
- 민감한 정보는 환경 변수로 관리
- Docker Secrets 사용
- Kubernetes Secrets 활용

## 📈 성능 최적화

### 캐싱
- RAG 검색 결과 캐싱
- API 응답 캐싱
- 정적 파일 캐싱

### 비동기 처리
- FastAPI 비동기 엔드포인트
- 백그라운드 크롤링
- WebSocket 실시간 통신

### 확장성
- 수평적 확장 (로드 밸런싱)
- 데이터베이스 분리
- 마이크로서비스 아키텍처

## 🐛 문제 해결

### 일반적인 문제
1. **Playwright 설치 오류**
   ```bash
   playwright install chromium
   playwright install-deps chromium
   ```

2. **포트 충돌**
   ```bash
   # 다른 포트 사용
   uvicorn main:app --port 8001
   ```

3. **메모리 부족**
   ```bash
   # Docker 메모리 제한 설정
   docker run -m 2g hos-app
   ```

### 로그 확인
```bash
# 애플리케이션 로그
docker logs hos-app

# 실시간 로그
docker logs -f hos-app
```

## 🤝 기여

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 라이선스

MIT License

## 📞 지원

- 이메일: hos-emergency-bot@example.com
- 이슈 트래커: GitHub Issues
- 문서: /docs 엔드포인트
