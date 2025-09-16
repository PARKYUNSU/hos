#!/usr/bin/env python3
"""
HOS FastAPI 테스트 스크립트
"""

import requests
import json
import time

def test_health():
    """헬스 체크 테스트"""
    print("🔍 헬스 체크 테스트...")
    try:
        response = requests.get("http://127.0.0.1:8000/api/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 헬스 체크 성공: {data}")
            return True
        else:
            print(f"❌ 헬스 체크 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 헬스 체크 오류: {e}")
        return False

def test_advice():
    """의료 조언 API 테스트"""
    print("\n🏥 의료 조언 API 테스트...")
    
    # 테스트 데이터
    test_cases = [
        {
            "symptom": "머리가 아파요",
            "location": {"lat": 35.6762, "lon": 139.6503}
        },
        {
            "symptom": "열이 나요",
            "location": {"lat": 35.6762, "lon": 139.6503}
        },
        {
            "symptom": "가슴이 답답해요",
            "location": {"lat": 35.6762, "lon": 139.6503}
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📝 테스트 케이스 {i}: {test_case['symptom']}")
        
        try:
            # Form data로 전송
            data = {
                'symptom': test_case['symptom'],
                'location': json.dumps(test_case['location'])
            }
            
            response = requests.post(
                "http://127.0.0.1:8000/api/advice",
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 조언 생성 성공!")
                print(f"   📊 RAG 신뢰도: {result['rag_confidence']:.1%}")
                print(f"   ⏱️ 처리 시간: {result['processing_time']:.2f}초")
                print(f"   💊 OTC 약품: {result['otc']}")
                print(f"   🔄 크롤링 필요: {result['needs_crawling']}")
                print(f"   📝 조언 내용: {result['advice'][:100]}...")
            else:
                print(f"❌ 조언 생성 실패: {response.status_code}")
                print(f"   오류: {response.text}")
                
        except Exception as e:
            print(f"❌ API 호출 오류: {e}")
        
        time.sleep(1)  # 1초 대기

def test_logs():
    """로그 조회 테스트"""
    print("\n📋 로그 조회 테스트...")
    try:
        response = requests.get("http://127.0.0.1:8000/api/logs?limit=5", timeout=10)
        if response.status_code == 200:
            logs = response.json()
            print(f"✅ 로그 조회 성공: {len(logs)}개 로그")
            for log in logs[:2]:  # 처음 2개만 표시
                print(f"   📅 {log['timestamp']}: {log['user_input'][:30]}...")
        else:
            print(f"❌ 로그 조회 실패: {response.status_code}")
    except Exception as e:
        print(f"❌ 로그 조회 오류: {e}")

def test_stats():
    """통계 조회 테스트"""
    print("\n📊 통계 조회 테스트...")
    try:
        response = requests.get("http://127.0.0.1:8000/api/stats", timeout=10)
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ 통계 조회 성공:")
            print(f"   📈 총 로그: {stats['total_logs']}개")
            print(f"   🎯 성공률: {stats['success_rate']:.1%}")
            print(f"   📚 RAG 문서: {stats['rag_passages_count']}개")
            print(f"   🤖 Playwright: {'활성' if stats['playwright_enabled'] else '비활성'}")
        else:
            print(f"❌ 통계 조회 실패: {response.status_code}")
    except Exception as e:
        print(f"❌ 통계 조회 오류: {e}")

def main():
    print("🚀 HOS FastAPI 테스트 시작")
    print("=" * 50)
    
    # 1. 헬스 체크
    if not test_health():
        print("❌ 서버가 실행되지 않았습니다. 서버를 먼저 시작해주세요.")
        return
    
    # 2. 의료 조언 테스트
    test_advice()
    
    # 3. 로그 조회 테스트
    test_logs()
    
    # 4. 통계 조회 테스트
    test_stats()
    
    print("\n" + "=" * 50)
    print("🎉 HOS FastAPI 테스트 완료!")

if __name__ == "__main__":
    main()
