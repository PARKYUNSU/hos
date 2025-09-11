#!/usr/bin/env python3
"""
자동 크롤링 스케줄러
정기적으로 미처리 증상을 크롤링하고 RAG 데이터를 업데이트합니다.
"""

import time
import schedule
import logging
from datetime import datetime
import sys
import os

# 백엔드 서비스 임포트
sys.path.append('backend')
from services_logging import symptom_logger
from services_auto_crawler import auto_crawler
from services_rag_updater import rag_updater

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/scheduler.log'),
        logging.StreamHandler()
    ]
)

def run_auto_crawling():
    """자동 크롤링 작업을 실행합니다."""
    logging.info("자동 크롤링 작업 시작")
    
    try:
        # 미처리 증상 처리
        result = auto_crawler.process_unhandled_symptoms(limit=5)
        
        logging.info(f"크롤링 완료 - 처리: {result['processed']}, 성공: {result['successful']}, 실패: {result['failed']}")
        
        # 결과 상세 로깅
        for item in result['results']:
            if item['status'] == 'success':
                logging.info(f"✅ {item['symptom']}: {item['results_count']}개 결과")
            else:
                logging.error(f"❌ {item['symptom']}: {item['error']}")
        
        return result
        
    except Exception as e:
        logging.error(f"자동 크롤링 중 오류 발생: {e}")
        return None

def run_rag_update():
    """RAG 시스템 업데이트를 실행합니다."""
    logging.info("RAG 시스템 업데이트 시작")
    
    try:
        result = rag_updater.update_rag_system()
        
        if result['success']:
            logging.info(f"RAG 업데이트 완료: {result['new_files']}개 새 파일, 총 {result['total_files']}개 파일")
        else:
            logging.error(f"RAG 업데이트 실패: {result['error']}")
        
        return result
        
    except Exception as e:
        logging.error(f"RAG 업데이트 중 오류 발생: {e}")
        return None

def run_system_cleanup():
    """시스템 정리 작업을 실행합니다."""
    logging.info("시스템 정리 작업 시작")
    
    try:
        # 오래된 백업 정리
        rag_updater.cleanup_old_backups(keep_days=7)
        logging.info("오래된 백업 정리 완료")
        
        # 통계 로깅
        stats = symptom_logger.get_symptom_statistics()
        rag_stats = rag_updater.get_rag_statistics()
        
        logging.info(f"시스템 통계 - 총 로그: {stats['total_logs']}, 성공률: {stats['success_rate']:.1%}, "
                    f"미처리: {stats['unhandled_symptoms']}, RAG 파일: {rag_stats['total_files']}")
        
    except Exception as e:
        logging.error(f"시스템 정리 중 오류 발생: {e}")

def run_health_check():
    """시스템 상태를 확인합니다."""
    logging.info("시스템 상태 확인")
    
    try:
        # 데이터베이스 연결 확인
        stats = symptom_logger.get_symptom_statistics()
        logging.info(f"데이터베이스 연결 정상 - 총 로그: {stats['total_logs']}")
        
        # RAG 시스템 확인
        rag_stats = rag_updater.get_rag_statistics()
        logging.info(f"RAG 시스템 정상 - 총 파일: {rag_stats['total_files']}")
        
        # 미처리 증상 확인
        unhandled = symptom_logger.get_unhandled_symptoms(1)
        if unhandled:
            logging.warning(f"미처리 증상 {len(unhandled)}개 발견")
        else:
            logging.info("미처리 증상 없음")
        
        return True
        
    except Exception as e:
        logging.error(f"시스템 상태 확인 중 오류 발생: {e}")
        return False

def main():
    """메인 스케줄러 함수"""
    logging.info("HOS 자동 크롤링 스케줄러 시작")
    
    # 로그 디렉토리 생성
    os.makedirs('logs', exist_ok=True)
    
    # 스케줄 설정
    # 매 시간마다 미처리 증상 크롤링
    schedule.every().hour.do(run_auto_crawling)
    
    # 매 6시간마다 RAG 시스템 업데이트
    schedule.every(6).hours.do(run_rag_update)
    
    # 매일 자정에 시스템 정리
    schedule.every().day.at("00:00").do(run_system_cleanup)
    
    # 매 30분마다 시스템 상태 확인
    schedule.every(30).minutes.do(run_health_check)
    
    # 초기 상태 확인
    if not run_health_check():
        logging.error("초기 시스템 상태 확인 실패")
        return
    
    logging.info("스케줄러 설정 완료")
    logging.info("- 매 시간: 미처리 증상 크롤링")
    logging.info("- 매 6시간: RAG 시스템 업데이트")
    logging.info("- 매일 자정: 시스템 정리")
    logging.info("- 매 30분: 시스템 상태 확인")
    
    # 스케줄러 실행
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크
    except KeyboardInterrupt:
        logging.info("스케줄러 종료")
    except Exception as e:
        logging.error(f"스케줄러 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
