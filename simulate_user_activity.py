#!/usr/bin/env python3
"""
사용자 활동 시뮬레이션 스크립트
관리자 대시보드 데모를 위한 테스트 데이터 생성
"""

import sys
import os
import time
import random
from datetime import datetime, timedelta

# 백엔드 서비스 임포트
sys.path.append('backend')
from services_logging import symptom_logger

def simulate_user_symptoms():
    """다양한 사용자 증상을 시뮬레이션합니다."""
    
    # 시뮬레이션할 증상들
    symptoms_data = [
        {
            "symptoms": "모기에 물렸어요. 가려워요.",
            "image_uploaded": False,
            "location": "Tokyo",
            "expected_quality": "good"
        },
        {
            "symptoms": "벌레에 물린 것 같아요. 부어요.",
            "image_uploaded": True,
            "location": "Osaka", 
            "expected_quality": "good"
        },
        {
            "symptoms": "말벌에 쏘였어요. 아파요.",
            "image_uploaded": False,
            "location": "Kyoto",
            "expected_quality": "good"
        },
        {
            "symptoms": "복통이 심해요. 토할 것 같아요.",
            "image_uploaded": False,
            "location": "Tokyo",
            "expected_quality": "good"
        },
        {
            "symptoms": "열이 39도까지 올라갔어요.",
            "image_uploaded": False,
            "location": "Yokohama",
            "expected_quality": "good"
        },
        {
            "symptoms": "눈이 부어서 잘 안 보여요.",
            "image_uploaded": True,
            "location": "Tokyo",
            "expected_quality": "poor"  # 새로운 증상 - 기본 조언만 나올 것
        },
        {
            "symptoms": "귀에서 소리가 안 들려요.",
            "image_uploaded": False,
            "location": "Sapporo",
            "expected_quality": "failed"  # 처리되지 않은 증상
        },
        {
            "symptoms": "손가락이 마비된 것 같아요.",
            "image_uploaded": False,
            "location": "Fukuoka",
            "expected_quality": "failed"  # 처리되지 않은 증상
        }
    ]
    
    print("🎭 사용자 활동 시뮬레이션 시작...")
    print("=" * 50)
    
    for i, data in enumerate(symptoms_data, 1):
        print(f"\n👤 사용자 {i}: {data['symptoms']}")
        
        # RAG 결과 시뮬레이션
        if data['expected_quality'] == 'good':
            rag_results = [
                ("벌레 물림 상세 응급처치 가이드", 0.85),
                ("일본 응급처치 매뉴얼", 0.72)
            ]
            rag_confidence = 0.85
        elif data['expected_quality'] == 'poor':
            rag_results = [
                ("기본 응급처치 가이드", 0.45)
            ]
            rag_confidence = 0.45
        else:  # failed
            rag_results = []
            rag_confidence = 0.0
        
        # 로그 기록
        try:
            log_id = symptom_logger.log_symptom(
                user_input=data['symptoms'],
                image_uploaded=data['image_uploaded'],
                rag_results=rag_results,
                advice_generated=True,
                advice_quality=data['expected_quality'],
                hospital_found=random.choice([True, False]),
                pharmacy_found=True,
                location=(35.6762 + random.uniform(-0.1, 0.1), 139.6503 + random.uniform(-0.1, 0.1)),
                processing_time=random.uniform(1.5, 4.2),
                session_id=f"demo_session_{i}_{datetime.now().strftime('%H%M%S')}"
            )
            print(f"   ✅ 로그 기록 완료 (ID: {log_id})")
            
            if data['expected_quality'] == 'failed':
                print(f"   ⚠️  처리되지 않은 증상 감지 - 자동 크롤링 트리거")
            
        except Exception as e:
            print(f"   ❌ 로그 기록 실패: {e}")
        
        # 시뮬레이션 간격
        time.sleep(2)
    
    print("\n" + "=" * 50)
    print("🎉 사용자 활동 시뮬레이션 완료!")
    print("이제 관리자 대시보드에서 결과를 확인하세요.")

def show_dashboard_instructions():
    """대시보드 사용법을 안내합니다."""
    print("\n" + "=" * 60)
    print("📊 관리자 대시보드 사용법")
    print("=" * 60)
    print("1. 웹 브라우저에서 다음 URL들을 열어주세요:")
    print("   👤 사용자 앱: http://localhost:8501")
    print("   🏥 관리자 대시보드: http://localhost:8502")
    print()
    print("2. 관리자 대시보드에서 확인할 수 있는 정보:")
    print("   📈 대시보드: 전체 통계 및 차트")
    print("   📝 증상 로그: 사용자 입력 내역")
    print("   ⚠️  미처리 증상: 처리되지 않은 증상들")
    print("   🔄 자동 크롤링: 크롤링 작업 상태")
    print("   📊 RAG 관리: 지식베이스 관리")
    print()
    print("3. 주요 기능:")
    print("   - 실시간 사용자 활동 모니터링")
    print("   - 미처리 증상 자동 감지")
    print("   - 수동 크롤링 트리거")
    print("   - RAG 시스템 업데이트")
    print("=" * 60)

if __name__ == "__main__":
    simulate_user_symptoms()
    show_dashboard_instructions()
