#!/usr/bin/env python3
"""
관리자 대시보드 실행 스크립트
"""

import subprocess
import sys
import os

def main():
    """관리자 대시보드를 실행합니다."""
    print("🏥 HOS 관리자 대시보드 시작")
    print("=" * 50)
    
    # 필요한 디렉토리 생성
    os.makedirs('logs', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    # Streamlit 앱 실행
    try:
        subprocess.run([
            sys.executable, '-m', 'streamlit', 'run', 'admin_dashboard.py',
            '--server.port', '8502',
            '--server.address', '0.0.0.0'
        ])
    except KeyboardInterrupt:
        print("\n관리자 대시보드 종료")
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    main()
