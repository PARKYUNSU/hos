"""
FastAPI 테스트 앱 - 간단한 버전
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="HOS Test API")

@app.get("/")
async def root():
    return {"message": "HOS FastAPI 테스트 서버가 실행 중입니다!"}

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "FastAPI 서버가 정상적으로 작동하고 있습니다."
    }

@app.get("/test", response_class=HTMLResponse)
async def test_page():
    return """
    <html>
        <head><title>HOS Test</title></head>
        <body>
            <h1>🚀 HOS FastAPI 테스트 성공!</h1>
            <p>FastAPI 서버가 정상적으로 실행되고 있습니다.</p>
            <p><a href="/docs">API 문서 보기</a></p>
        </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
