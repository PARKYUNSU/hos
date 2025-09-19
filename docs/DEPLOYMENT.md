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

## FastAPI + Nginx + systemd (EC2) 배포 요약

### 1) 시스템 준비
```bash
sudo apt update && sudo apt install -y nginx
# (옵션) swap 구성 권장
```

### 2) Miniconda/Conda 환경
```bash
curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o miniconda.sh
bash miniconda.sh -b -p "$HOME/miniconda"
source "$HOME/miniconda/etc/profile.d/conda.sh"
conda create -y -n hos python=3.11
conda activate hos
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
pip install -r requirements.txt
python -m playwright install chromium --with-deps || true
```

### 3) 환경 변수(.env)
```env
OPENAI_API_KEY=sk-...
ADMIN_USER=admin
ADMIN_PASS=<your-secure-password>
FAST_MODE=0
USE_PLAYWRIGHT_CRAWLING=1
PW_HEADLESS=1
PW_WAIT_UNTIL=networkidle
DISABLE_POI=1
POI_TIMEOUT_SEC=6
RAG_TFIDF_MAX_FEATURES=4000
RAG_MAX_PASSAGES=200
RAG_USE_RAG_DATA=0
OPENAI_MAX_TOKENS=900
OPENAI_TIMEOUT_SECONDS=15
MVP_RANDOM_TOKYO=true
MVP_FIXED_SHINJUKU=true
```

### 4) systemd 서비스
`/etc/systemd/system/hos.service`
```ini
[Unit]
Description=HOS FastAPI (uvicorn)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/hos
EnvironmentFile=/home/ubuntu/hos/.env
ExecStart=/home/ubuntu/miniconda/envs/hos/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable hos --now
```

### 5) Nginx 리버스 프록시
`/etc/nginx/sites-available/hos`
```nginx
server {
    listen 80;
    server_name _;
    client_max_body_size 10M;

    location /static/ {
        alias /var/www/hos/static/;
        access_log off;
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
    }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
```
```bash
sudo ln -sf /etc/nginx/sites-available/hos /etc/nginx/sites-enabled/hos
sudo mkdir -p /var/www/hos/static
sudo rsync -a /home/ubuntu/hos/static/ /var/www/hos/static/
sudo nginx -t && sudo systemctl reload nginx
```

### 6) 헬스 체크
```bash
curl -sS http://127.0.0.1:8000/api/health
curl -sS http://<EC2-PUBLIC-DNS>/api/health
```

### 7) 운영 팁
- 관리자 대시보드는 HTTP Basic으로 보호됩니다 (`ADMIN_USER`/`ADMIN_PASS`).
- 모든 로그/대시보드 시간은 KST(Asia/Seoul) 기준으로 표기됩니다.
- 413 업로드 제한은 `client_max_body_size`로 조정합니다(예: 10M).

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
