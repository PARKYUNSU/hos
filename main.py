"""
HOS Emergency Medical Chatbot - FastAPI Application
일본 여행자를 위한 응급 의료 챗봇 API 서버
"""

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import requests
import requests
import asyncio
import json
import os
import sys
from datetime import datetime
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None  # Fallback: no tzinfo available
from dotenv import load_dotenv
from functools import lru_cache
import hashlib
import logging
import io
from PIL import Image
import numpy as np
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

# 백엔드 서비스 임포트
sys.path.append('backend')
# FAST_MODE에서는 무거운 RAG 초기화를 건너뛰어 메모리 사용을 줄임
FAST_MODE = os.getenv('FAST_MODE', '0').lower() in ('1', 'true', 'on', 'yes')
GLOBAL_RAG = None
symptom_logger = None
auto_crawl_unhandled_symptoms = None
try:
    from services_gen import generate_advice
    if not FAST_MODE:
        from services_rag import GLOBAL_RAG as _GLOBAL_RAG
        GLOBAL_RAG = _GLOBAL_RAG
    from services_logging import symptom_logger  # type: ignore
    from services_auto_crawler import auto_crawl_unhandled_symptoms  # type: ignore
    from services_playwright_crawler import is_playwright_enabled
    from otc_rules import load_rules, save_rules
except ImportError as e:
    print(f"백엔드 서비스 임포트 오류: {e}")
    # Playwright 의존성이 없거나 기타 임포트 실패 시에도 헬스 체크가 동작하도록 폴백 제공
    def is_playwright_enabled() -> bool:  # type: ignore
        return False

# 단순화된 설정 (임포트 성공 시 실제 함수 사용)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 환경변수 로드 (.env)
try:
    load_dotenv()
except Exception:
    pass

# FastAPI 앱 초기화
app = FastAPI(
    title="HOS Emergency Medical Chatbot",
    description="일본 여행자를 위한 응급 의료 챗봇 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Admin authentication (HTTP Basic) ---
security = HTTPBasic()

def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    user = os.getenv("ADMIN_USER", "")
    pw = os.getenv("ADMIN_PASS", "")
    ok = (
        bool(user)
        and bool(pw)
        and secrets.compare_digest(credentials.username, user)
        and secrets.compare_digest(credentials.password, pw)
    )
    if not ok:
        # 인증 실패 시 401과 함께 WWW-Authenticate 헤더 반환
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})

# WebSocket 연결 관리
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # 연결이 끊어진 경우 제거
                self.active_connections.remove(connection)

manager = ConnectionManager()

# 긴급 증상(119 즉시 연락) 선제 판단 함수
def is_emergency_symptom(text: str) -> bool:
    t = (text or "").lower()
    emergency_keywords = [
        # 호흡/의식
        "호흡곤란", "숨이", "숨쉬기 어렵", "의식 소실", "의식을 잃", "의식 변화",
        # 흉통/심혈관
        "가슴이 아파", "가슴 통증", "흉통", "가슴답답", "심근", "심장마비",
        # 뇌신경
        "반신 마비", "마비", "말이 어눌", "구음장애", "한쪽 팔", "한쪽 다리", "뇌졸중", "뇌출혈",
        # 출혈/외상/화상
        "대량 출혈", "지속적 출혈", "피가 멈추지", "피가 많이 나", "피가 콸콸",
        "동맥 출혈", "분수처럼 피", "지혈이 안", "압박해도 피",
        # 절단/절단상(손가락/발가락 등 포함)
        "절단", "절단상", "잘렸", "잘라", "끊어졌", "떨어져 나갔",
        "손가락이 절단", "발가락이 절단", "손가락이 잘렸", "발가락이 잘렸",
        "절단된 손가락", "절단된 발가락",
        # 화상 고위험
        "심한 화상", "광범위 화상",
        # 알레르기/아나필락시스
        "아나필락시", "전신 두드러기", "목이 붓", "입술 붓", "호흡이 쌕",
        # 경련/발작
        "경련", "발작", "전신 경련",
        # 영유아 고열 위험
        "영유아", "아기", "생후", "고열 39", "고열 40",
    ]
    return any(k in t for k in emergency_keywords)

# 다중 증상 분리 유틸
def split_symptoms(text: str) -> List[str]:
    if not text:
        return []
    candidates = []
    tmp = text
    # 구분자 기준 분리 (쉼표/마침표/연결어)
    for sep in ["\n", ",", "·", "∙", "/", " 그리고 ", " 및 ", " 와 함께 ", " 하고 ", ".", ";", "、"]:
        tmp = tmp.replace(sep, "|")
    for part in tmp.split("|"):
        s = part.strip()
        if len(s) >= 2:
            candidates.append(s)
    # 중복 제거, 상위 3개까지만 사용
    seen = set()
    unique = []
    for s in candidates:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique[:3]

# Pydantic 모델들
class SymptomRequest(BaseModel):
    symptom: str
    location: Optional[Dict[str, float]] = None  # {"lat": 35.6762, "lon": 139.6503}

class AdviceResponse(BaseModel):
    advice: str
    otc: List[str]
    rag_confidence: float
    processing_time: float
    is_default_advice: bool
    needs_crawling: bool
    references: List[str] = []
    nearby_hospitals: List[Dict[str, Any]] = []
    nearby_pharmacies: List[Dict[str, Any]] = []

class LogEntry(BaseModel):
    id: int
    timestamp: str
    user_input: str
    advice_content: str
    rag_confidence: float
    processing_time: float
    advice_quality: str
    image_uploaded: bool

# 의존성 주입
def get_openai_client():
    """OpenAI 클라이언트 의존성"""
    try:
        from openai import OpenAI
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        return OpenAI(api_key=api_key)
    except ImportError:
        raise HTTPException(status_code=500, detail="OpenAI library not installed")

# API 엔드포인트들
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """메인 페이지"""
    # 테스트 모드 설정 확인
    test_mode = os.getenv('MVP_RANDOM_TOKYO', 'false').lower() == 'true'
    fixed_shinjuku = os.getenv('MVP_FIXED_SHINJUKU', 'false').lower() == 'true'
    fixed_lat = os.getenv('MVP_FIXED_LAT', '35.6762')
    fixed_lon = os.getenv('MVP_FIXED_LON', '139.6503')
    
    return templates.TemplateResponse("index.html", {
        "request": {},
        "test_mode": test_mode,
        "fixed_shinjuku": fixed_shinjuku,
        "fixed_lat": fixed_lat,
        "fixed_lon": fixed_lon
    })

@app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def admin_dashboard():
    """관리자 대시보드"""
    return templates.TemplateResponse("admin.html", {"request": {}})

@app.post("/api/advice", response_model=AdviceResponse)
async def get_advice(
    symptom: str = Form(...),
    image: Optional[UploadFile] = File(None),
    location: Optional[str] = Form(None),
    client = Depends(get_openai_client)
):
    """증상에 대한 의료 조언 제공"""
    start_time = datetime.now()
    
    try:
        # 위치 정보 파싱
        lat, lon = None, None
        if location:
            try:
                loc_data = json.loads(location)
                lat, lon = loc_data.get('lat'), loc_data.get('lon')
            except:
                pass
        # 위치 미지정 시 테스트 모드 기본값 적용
        if (not lat or not lon):
            try:
                test_mode = os.getenv('MVP_RANDOM_TOKYO', 'false').lower() == 'true'
                fixed_shinjuku = os.getenv('MVP_FIXED_SHINJUKU', 'false').lower() == 'true'
                if fixed_shinjuku:
                    lat, lon = 35.6909, 139.7006
                elif test_mode:
                    # 도쿄 중심 근처 랜덤 좌표
                    import random
                    center_lat, center_lon = 35.6762, 139.6503
                    delta = 0.05
                    lat = center_lat + (random.random() - 0.5) * delta
                    lon = center_lon + (random.random() - 0.5) * delta
            except Exception:
                pass
        
        # 이미지 처리
        image_bytes = None
        if image:
            image_bytes = await image.read()
            # 이미지 기반 응급 차단 로직 (과다 출혈/화상 의심)
            try:
                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                small = img.resize((224, 224))
                hsv = small.convert("HSV")
                arr = np.array(hsv)
                h = arr[:, :, 0].astype(np.float32)
                s = arr[:, :, 1].astype(np.float32)
                v = arr[:, :, 2].astype(np.float32)
                red_thr = float(os.getenv("IMG_RED_RATIO", "0.25"))
                burn_thr = float(os.getenv("IMG_BURN_RATIO", "0.30"))
                red_mask = ((h < 10) | (h > 245)) & (s > 100) & (v > 60)
                red_ratio = float(red_mask.mean())
                orange_mask = (h >= 10) & (h <= 50) & (s > 120) & (v > 120)
                orange_ratio = float(orange_mask.mean())
                if red_ratio > red_thr or orange_ratio > burn_thr:
                    advice_text = (
                        "이미지에서 응급 위험(과다 출혈/심한 화상)이 의심됩니다. \n"
                        "지금 즉시 119(일본)로 연락하시고, 가능한 경우 주변의 도움을 요청하세요."
                    )
                    return AdviceResponse(
                        advice=advice_text,
                        otc=[],
                        rag_confidence=0.0,
                        processing_time=(datetime.now() - start_time).total_seconds(),
                        is_default_advice=True,
                        needs_crawling=False,
                    )
            except Exception:
                pass
        
        # 다중 증상 분리 및 119 즉시 연락 판단(선제)
        symptom_list = split_symptoms(symptom)
        if any(is_emergency_symptom(s) for s in ([symptom] + symptom_list)):
            advice_text = (
                "현재 증상은 응급 위험 소견에 해당할 수 있습니다. \n"
                "지금 즉시 119(일본)로 연락하시고, 가능한 경우 주변의 도움을 요청하세요. \n"
                "의식 변화·호흡곤란·갑작스런 흉통·반신마비·지속적 출혈·광범위 화상·아나필락시스 등이 의심되면 지체하지 마세요."
            )
            return AdviceResponse(
                advice=advice_text,
                otc=[],
                rag_confidence=0.0,
                processing_time=(datetime.now() - start_time).total_seconds(),
                is_default_advice=True,
                needs_crawling=False,
            )

        # RAG 검색(다중 증상 late merge)
        rag_passages = []
        rag_confidence = 0.0
        merged_hits = []  # (passage, raw_score)
        if GLOBAL_RAG:
            try:
                queries = symptom_list or [symptom]
                for q in queries:
                    hits = GLOBAL_RAG.search(q, top_k=3)
                    merged_hits.extend(hits)
                # 상위 근거 추출 (raw score 기준 정렬)
                merged_hits = sorted(merged_hits, key=lambda x: x[1], reverse=True)[:3]
                rag_passages = [p for p, _ in merged_hits]
                # softmax 정규화로 0~1 신뢰도 계산
                try:
                    import math
                    raw_scores = [float(s) for _, s in merged_hits]
                    if raw_scores:
                        max_s = max(raw_scores)
                        exps = [math.exp(s - max_s) for s in raw_scores]
                        denom = sum(exps) or 1.0
                        probs = [e / denom for e in exps]
                        # 최상위 문서 확률을 신뢰도로 사용 (softmax top-1)
                        rag_confidence = float(probs[0]) if probs else 0.0
                        # 로깅 일관성을 위해 정규화 점수를 함께 유지
                        merged_hits = [(rag_passages[i], probs[i]) for i in range(len(rag_passages))]
                    else:
                        rag_confidence = 0.0
                except Exception:
                    # 실패 시 이전 방식의 상한 없는 점수 최대값을 1.0으로 클램프
                    try:
                        rag_confidence = max([s for _, s in merged_hits]) if merged_hits else 0.0
                        if rag_confidence > 1.0:
                            rag_confidence = 1.0
                    except Exception:
                        rag_confidence = 0.0
                # 안전 클램프 (0~1)
                try:
                    if rag_confidence < 0.0:
                        rag_confidence = 0.0
                    if rag_confidence > 1.0:
                        rag_confidence = 1.0
                except Exception:
                    rag_confidence = 0.0
            except Exception as e:
                logger.error(f"RAG search error: {e}")
        
        # LLM 조언 생성
        # LLM에는 원문 전체 증상 문자열 전달(종합 조언)
        advice_result = generate_advice(
            symptoms=symptom,
            findings="",  # 이미지 분석 결과는 별도로 처리
            passages=rag_passages,
            image_bytes=image_bytes,
            client=client
        )
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # 크롤링 필요성 판단 (정규화된 신뢰도 기준)
        needs_crawling = rag_confidence < 0.6

        # 참고문헌 스니펫 구성
        references: List[str] = []
        for p in rag_passages[:3]:
            snippet = (p or "").strip().replace("\n", " ")
            if snippet:
                references.append(snippet[:180] + ("..." if len(snippet) > 180 else ""))

        # 주변 병원/약국 검색 (위치가 제공된 경우)
        nearby_hospitals: List[Dict[str, Any]] = []
        nearby_pharmacies: List[Dict[str, Any]] = []
        try:
            # 환경변수로 POI 조회 비활성화 옵션 제공 (지연 시 단기 성능 대응)
            disable_poi = (os.getenv("DISABLE_POI", "0").lower() in ("1", "true", "on", "yes"))
            if lat and lon and not disable_poi:
                # Overpass API로 간단 검색
                def search_pois(amenity: str) -> List[Dict[str, Any]]:
                    # Overpass에서 충분한 후보를 받아온 뒤, 거리 계산해 가까운 순 5개만 반환
                    poi_timeout = int(os.getenv("POI_TIMEOUT_SEC", "6"))
                    radius_m = int(os.getenv("POI_RADIUS_M", "1500"))
                    query = f"""
                    [out:json][timeout:{poi_timeout}];
                    (
                      node["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
                      way["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
                      relation["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
                    );
                    out center 50;
                    """
                    r = requests.post(
                        "https://overpass-api.de/api/interpreter",
                        data={"data": query},
                        timeout=poi_timeout,
                    )
                    r.raise_for_status()
                    js = r.json()
                    res: List[Dict[str, Any]] = []

                    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
                        from math import radians, sin, cos, asin, sqrt
                        R = 6371.0
                        dlat = radians(lat2 - lat1)
                        dlon = radians(lon2 - lon1)
                        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
                        c = 2 * asin(sqrt(a))
                        return R * c

                    seen = set()
                    for el in js.get("elements", []):
                        tags = el.get("tags", {}) or {}
                        name = tags.get("name") or amenity
                        if el.get("type") == "node":
                            clat, clon = el.get("lat"), el.get("lon")
                        else:
                            center = el.get("center") or {}
                            clat, clon = center.get("lat"), center.get("lon")
                        if clat is None or clon is None:
                            continue
                        # 중복 제거 (좌표 반올림 + 이름 기준)
                        key = (name, round(float(clat), 5), round(float(clon), 5))
                        if key in seen:
                            continue
                        seen.add(key)
                        dist_km = haversine(float(lat), float(lon), float(clat), float(clon))
                        res.append({"name": name, "lat": clat, "lon": clon, "distance": dist_km})

                    res.sort(key=lambda x: (x.get("distance", 1e9), x.get("name", "")))
                    return res[:5]
                nearby_hospitals = search_pois("hospital")
                nearby_pharmacies = search_pois("pharmacy")
        except Exception as e:
            logger.error(f"POI search error: {e}")
        
        # 로그 저장
        try:
            symptom_logger.log_symptom(
                user_input=symptom,
                advice_content=advice_result['advice'],
                # merged_hits는 (passage, prob) 형식으로 softmax 정규화됨
                rag_results=merged_hits if GLOBAL_RAG else [],
                processing_time=processing_time,
                advice_quality='good' if rag_confidence > 0.7 else 'poor',
                image_uploaded=bool(image_bytes),
                location=(lat, lon) if lat and lon else None
            )
        except Exception as e:
            logger.error(f"Logging error: {e}")
        
        # 크롤링 트리거 (백그라운드)
        if needs_crawling:
            try:
                if auto_crawl_unhandled_symptoms:
                    auto_crawl_unhandled_symptoms()
            except Exception as e:
                logger.error(f"Crawling error: {e}")
        
        result = AdviceResponse(
            advice=advice_result['advice'],
            otc=advice_result.get('otc', []),
            rag_confidence=rag_confidence,
            processing_time=processing_time,
            is_default_advice=advice_result.get('is_default_advice', False),
            needs_crawling=needs_crawling,
            references=references,
            nearby_hospitals=nearby_hospitals,
            nearby_pharmacies=nearby_pharmacies
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Advice generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs", response_model=List[LogEntry], dependencies=[Depends(require_admin)])
async def get_logs(limit: int = 50):
    """증상 로그 조회"""
    try:
        logs = symptom_logger.get_recent_logs(limit=limit)
        # 출력은 한국시간(Asia/Seoul) 기준으로 변환
        tz_kst = ZoneInfo("Asia/Seoul") if ZoneInfo else None
        tz_utc = ZoneInfo("UTC") if ZoneInfo else None
        return [
            LogEntry(
                id=log['id'],
                timestamp=(
                    (
                        # timezone-aware 변환
                        datetime.fromisoformat(
                            log['timestamp'].replace('Z', '+00:00')
                        )
                        if ('timestamp' in log and isinstance(log['timestamp'], str)) else datetime.now()
                    )
                    .replace(tzinfo=(tz_utc if tz_utc else None))
                    .astimezone(tz_kst)  # type: ignore[arg-type]
                    .isoformat()
                    if tz_kst else log.get('timestamp', '')
                ),
                user_input=log['user_input'],
                advice_content=log.get('advice_content', ''),
                rag_confidence=float(log['rag_confidence']) if log['rag_confidence'] else 0.0,
                processing_time=float(log['processing_time']) if log['processing_time'] else 0.0,
                advice_quality=log['advice_quality'],
                image_uploaded=bool(log['image_uploaded'])
            )
            for log in logs
        ]
    except Exception as e:
        logger.error(f"Log retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats", dependencies=[Depends(require_admin)])
async def get_stats():
    """시스템 통계"""
    try:
        logs = symptom_logger.get_recent_logs(limit=1000)
        total_logs = len(logs)
        
        # 성공률 계산
        successful_logs = sum(1 for log in logs if log['advice_quality'] in ['good', 'excellent'])
        success_rate = successful_logs / total_logs if total_logs > 0 else 0
        
        # RAG 신뢰도 분포
        confidence_ranges = {'0-0.2': 0, '0.2-0.4': 0, '0.4-0.6': 0, '0.6-0.8': 0, '0.8-1.0': 0}
        for log in logs:
            try:
                confidence = float(log['rag_confidence']) if log['rag_confidence'] else 0.0
                # 0..1 범위로 클램프
                if confidence < 0.0:
                    confidence = 0.0
                elif confidence > 1.0:
                    confidence = 1.0
                if 0.0 <= confidence < 0.2:
                    confidence_ranges['0-0.2'] += 1
                elif 0.2 <= confidence < 0.4:
                    confidence_ranges['0.2-0.4'] += 1
                elif 0.4 <= confidence < 0.6:
                    confidence_ranges['0.4-0.6'] += 1
                elif 0.6 <= confidence < 0.8:
                    confidence_ranges['0.6-0.8'] += 1
                elif 0.8 <= confidence <= 1.0:
                    confidence_ranges['0.8-1.0'] += 1
            except:
                continue
        
        return {
            "total_logs": total_logs,
            "success_rate": success_rate,
            "confidence_distribution": confidence_ranges,
            "playwright_enabled": is_playwright_enabled(),
            "rag_passages_count": len(GLOBAL_RAG.passages) if GLOBAL_RAG else 0
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/otc_rules")
async def get_otc_rules():
    try:
        return load_rules()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RulesUpdate(BaseModel):
    rules: Dict[str, Any]


@app.post("/api/otc_rules")
async def update_otc_rules(payload: RulesUpdate):
    try:
        save_rules(payload.rules)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """실시간 로그 WebSocket"""
    await manager.connect(websocket)
    try:
        while True:
            # 클라이언트로부터 메시지 수신 (ping/pong)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def trigger_crawling(symptom: str):
    """백그라운드 크롤링 실행"""
    try:
        logger.info(f"Triggering crawling for symptom: {symptom}")
        result = auto_crawl_unhandled_symptoms()
        logger.info(f"Crawling completed: {result}")
        
        # WebSocket으로 결과 브로드캐스트
        await manager.broadcast(json.dumps({
            "type": "crawling_completed",
            "symptom": symptom,
            "result": result
        }))
    except Exception as e:
        logger.error(f"Crawling error: {e}")
        await manager.broadcast(json.dumps({
            "type": "crawling_error",
            "symptom": symptom,
            "error": str(e)
        }))

@app.get("/api/health")
async def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "timestamp": (
            datetime.now(ZoneInfo("Asia/Seoul")).isoformat() if ZoneInfo else datetime.now().isoformat()
        ),
        "rag_loaded": GLOBAL_RAG is not None,
        "playwright_enabled": is_playwright_enabled(),
        "use_playwright_env": os.getenv("USE_PLAYWRIGHT_CRAWLING"),
        "pw_headless": os.getenv("PW_HEADLESS"),
        "pw_wait_until": os.getenv("PW_WAIT_UNTIL")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
