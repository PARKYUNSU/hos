#!/usr/bin/env python3
"""
HOS FastAPI 애플리케이션 실행 스크립트
"""

import os
import sys
import uvicorn
from pathlib import Path

def main():
    # 환경 변수 설정
    os.environ.setdefault('PYTHONPATH', str(Path(__file__).parent))
    
    # 개발 모드 설정
    reload = os.getenv('RELOAD', 'true').lower() == 'true'
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '8000'))
    
    print(f"🚀 HOS FastAPI 서버 시작 중...")
    print(f"📍 주소: http://{host}:{port}")
    print(f"📚 API 문서: http://{host}:{port}/docs")
    print(f"🔧 관리자: http://{host}:{port}/admin")
    print(f"🔄 리로드: {'활성' if reload else '비활성'}")
    
    # FastAPI 앱 실행
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main()
