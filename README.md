# 해외 응급 환자 챗봇(일본)

## 구성
- FastAPI 백엔드: `backend/main.py` (/chat: 이미지+증상+위치)
- Streamlit UI: `ui/app.py` (이미지 업로드/증상/위치 폼)
- RAG: `backend/services_rag.py` (일본어 형태소+BM25+TF-IDF)
- 지오: `backend/services_geo.py` (Nominatim+Overpass)
- 생성: `backend/services_gen.py` (OpenAI 선택적 연동)

## 준비
Conda 환경 `hos` 활성화 후 의존성 설치:

```bash
pip install -r requirements.txt
```

필수/선택 환경변수:
```bash
export TRIAGE_API_URL="http://localhost:8000"   # UI->API 엔드포인트
export OPENAI_API_KEY=sk-...                     # 선택: 없으면 규칙 기반 응답
export CONTACT_EMAIL="you@example.com"          # Nominatim User-Agent 식별자 권장
```

## 실행
두 개의 터미널에서 각각 실행합니다.

백엔드(API):
```bash
uvicorn backend.main:app --reload --port 8000
```

프론트엔드(UI):
```bash
streamlit run ui/app.py --server.port 8501
```

## API 예시
```bash
curl -s -F "symptoms=열과 기침" -F "location=Shibuya" http://127.0.0.1:8000/chat
curl -s -F "image=@sample.jpg" -F "symptoms=이마 출혈" -F "location=Shinjuku" http://127.0.0.1:8000/chat
```

## 주의
- 본 서비스는 의료적 조언 보조용이며 진단/치료를 대체하지 않습니다. 응급 시 일본 119에 즉시 연락하세요.
- 챗봇은 특정 키워드/패턴으로 위급 신호를 감지하면 응답을 중단하고 119 연결 버튼만 제공합니다. (예: 심한 가슴 통증, 대량 출혈, 의식 소실, 호흡곤란 등)


