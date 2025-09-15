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
import asyncio
import json
import os
import sys
from datetime import datetime
import logging

# 백엔드 서비스 임포트
sys.path.append('backend')
from services_gen import generate_advice
from services_rag import GLOBAL_RAG
from services_logging import symptom_logger
from services_auto_crawler import auto_crawl_unhandled_symptoms
from services_playwright_crawler import is_playwright_enabled

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    return templates.TemplateResponse("index.html", {"request": {}})

@app.get("/admin", response_class=HTMLResponse)
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
        
        # 이미지 처리
        image_bytes = None
        if image:
            image_bytes = await image.read()
        
        # RAG 검색
        rag_passages = []
        rag_confidence = 0.0
        if GLOBAL_RAG:
            try:
                hits = GLOBAL_RAG.search(symptom, top_k=3)
                rag_passages = [passage for passage, _ in hits]
                rag_confidence = max([score for _, score in hits]) if hits else 0.0
            except Exception as e:
                logger.error(f"RAG search error: {e}")
        
        # LLM 조언 생성
        advice_result = generate_advice(
            symptom=symptom,
            rag_passages=rag_passages,
            image_bytes=image_bytes,
            client=client
        )
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # 크롤링 필요성 판단
        needs_crawling = rag_confidence < 0.7
        
        # 로그 저장
        try:
            symptom_logger.log_symptom(
                user_input=symptom,
                advice_content=advice_result['advice'],
                rag_confidence=rag_confidence,
                processing_time=processing_time,
                advice_quality='good' if rag_confidence > 0.7 else 'poor',
                image_uploaded=bool(image_bytes),
                lat=lat,
                lon=lon
            )
        except Exception as e:
            logger.error(f"Logging error: {e}")
        
        # 크롤링 트리거 (백그라운드)
        if needs_crawling:
            asyncio.create_task(trigger_crawling(symptom))
        
        return AdviceResponse(
            advice=advice_result['advice'],
            otc=advice_result.get('otc', []),
            rag_confidence=rag_confidence,
            processing_time=processing_time,
            is_default_advice=advice_result.get('is_default_advice', False),
            needs_crawling=needs_crawling
        )
        
    except Exception as e:
        logger.error(f"Advice generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs", response_model=List[LogEntry])
async def get_logs(limit: int = 50):
    """증상 로그 조회"""
    try:
        logs = symptom_logger.get_recent_logs(limit=limit)
        return [
            LogEntry(
                id=log['id'],
                timestamp=log['timestamp'],
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

@app.get("/api/stats")
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
            "rag_passages_count": len(GLOBAL_RAG._all_passages) if GLOBAL_RAG else 0
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
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
        "timestamp": datetime.now().isoformat(),
        "rag_loaded": GLOBAL_RAG is not None,
        "playwright_enabled": is_playwright_enabled()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
