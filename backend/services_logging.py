"""
사용자 증상 로깅 및 데이터 수집 시스템
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

class SymptomLogger:
    """사용자 증상과 응답을 로깅하는 클래스"""
    
    def __init__(self, db_path: str = "data/symptom_logs.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """데이터베이스 초기화"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 증상 로그 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symptom_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_input TEXT NOT NULL,
                advice_content TEXT,
                image_uploaded BOOLEAN DEFAULT FALSE,
                rag_results_count INTEGER DEFAULT 0,
                rag_confidence REAL DEFAULT 0.0,
                advice_generated BOOLEAN DEFAULT FALSE,
                advice_quality TEXT DEFAULT 'unknown',
                hospital_found BOOLEAN DEFAULT FALSE,
                pharmacy_found BOOLEAN DEFAULT FALSE,
                location_lat REAL,
                location_lon REAL,
                processing_time REAL,
                error_message TEXT,
                session_id TEXT
            )
        """)
        
        # 기존 테이블에 advice_content 컬럼 추가 (이미 존재하는 경우 무시)
        try:
            cursor.execute("ALTER TABLE symptom_logs ADD COLUMN advice_content TEXT")
        except sqlite3.OperationalError:
            # 컬럼이 이미 존재하는 경우 무시
            pass
        
        # 미처리 증상 분석 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unhandled_symptoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symptom_text TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                rag_confidence REAL DEFAULT 0.0,
                priority_score REAL DEFAULT 0.0,
                status TEXT DEFAULT 'pending',
                suggested_actions TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # 크롤링 작업 로그 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawling_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symptom_keywords TEXT NOT NULL,
                target_sites TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                started_at TEXT,
                completed_at TEXT,
                results_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def log_symptom(self, 
                    user_input: str,
                    advice_content: str = None,
                    image_uploaded: bool = False,
                    rag_results: List[Tuple[str, float]] = None,
                    advice_generated: bool = False,
                    advice_quality: str = "unknown",
                    hospital_found: bool = False,
                    pharmacy_found: bool = False,
                    location: Tuple[float, float] = None,
                    processing_time: float = 0.0,
                    error_message: str = None,
                    session_id: str = None) -> int:
        """증상 로그를 기록합니다."""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # RAG 결과 분석
        rag_count = len(rag_results) if rag_results else 0
        # rag_results가 softmax 확률(0~1)이라고 가정하고 최대값 사용, 범위 보정
        try:
            rag_confidence = max([float(score) for _, score in (rag_results or [])]) if rag_results else 0.0
            if rag_confidence < 0.0:
                rag_confidence = 0.0
            if rag_confidence > 1.0:
                rag_confidence = 1.0
        except Exception:
            rag_confidence = 0.0
        
        # 위치 정보
        lat, lon = location if location else (None, None)
        
        cursor.execute("""
            INSERT INTO symptom_logs (
                timestamp, user_input, advice_content, image_uploaded, rag_results_count,
                rag_confidence, advice_generated, advice_quality,
                hospital_found, pharmacy_found, location_lat, location_lon,
                processing_time, error_message, session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            user_input,
            advice_content,
            image_uploaded,
            rag_count,
            rag_confidence,
            advice_generated,
            advice_quality,
            hospital_found,
            pharmacy_found,
            lat,
            lon,
            processing_time,
            error_message,
            session_id
        ))
        
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 미처리 증상 분석
        self._analyze_unhandled_symptom(user_input, rag_confidence, advice_generated)
        
        return log_id
    
    def get_recent_logs(self, limit: int = 10) -> List[Dict]:
        """최근 로그를 조회합니다."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, timestamp, user_input, advice_content, image_uploaded, 
                   rag_results_count, rag_confidence, advice_generated, advice_quality,
                   hospital_found, pharmacy_found, location_lat, location_lon,
                   processing_time, error_message, session_id
            FROM symptom_logs 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        columns = [description[0] for description in cursor.description]
        logs = []
        
        for row in cursor.fetchall():
            log_dict = dict(zip(columns, row))
            # None 값들을 적절한 기본값으로 변환
            for key, value in log_dict.items():
                if value is None:
                    if key in ['advice_content', 'error_message', 'session_id']:
                        log_dict[key] = ''
                    elif key in ['image_uploaded', 'advice_generated', 'hospital_found', 'pharmacy_found']:
                        log_dict[key] = False
                    elif key in ['rag_results_count']:
                        log_dict[key] = 0
                    elif key in ['rag_confidence', 'processing_time']:
                        log_dict[key] = 0.0
                    elif key in ['location_lat', 'location_lon']:
                        log_dict[key] = None
            logs.append(log_dict)
        
        conn.close()
        return logs
    
    def _analyze_unhandled_symptom(self, user_input: str, rag_confidence: float, advice_generated: bool):
        """미처리 증상인지 분석하고 기록합니다."""
        
        # 응답 품질이 낮거나 조언이 생성되지 않은 경우
        if rag_confidence < 0.3 or not advice_generated:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 기존 기록 확인
            cursor.execute("""
                SELECT id, frequency FROM unhandled_symptoms 
                WHERE symptom_text = ?
            """, (user_input,))
            
            result = cursor.fetchone()
            now = datetime.now().isoformat()
            
            if result:
                # 기존 기록 업데이트
                symptom_id, frequency = result
                cursor.execute("""
                    UPDATE unhandled_symptoms 
                    SET frequency = frequency + 1, 
                        last_seen = ?,
                        rag_confidence = ?,
                        priority_score = priority_score + 1
                    WHERE id = ?
                """, (now, rag_confidence, symptom_id))
            else:
                # 새 기록 생성
                priority_score = 1.0 if rag_confidence < 0.1 else 0.5
                cursor.execute("""
                    INSERT INTO unhandled_symptoms (
                        symptom_text, frequency, first_seen, last_seen,
                        rag_confidence, priority_score, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_input, 1, now, now, rag_confidence, priority_score, now))
            
            conn.commit()
            conn.close()
    
    def get_unhandled_symptoms(self, limit: int = 10) -> List[Dict]:
        """미처리 증상 목록을 가져옵니다."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT symptom_text, frequency, rag_confidence, priority_score,
                   first_seen, last_seen, status
            FROM unhandled_symptoms 
            WHERE status = 'pending'
            ORDER BY priority_score DESC, frequency DESC
            LIMIT ?
        """, (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'symptom_text': row[0],
                'frequency': row[1],
                'rag_confidence': row[2],
                'priority_score': row[3],
                'first_seen': row[4],
                'last_seen': row[5],
                'status': row[6]
            })
        
        conn.close()
        return results
    
    def get_symptom_statistics(self) -> Dict:
        """증상 통계를 가져옵니다."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 전체 통계
        cursor.execute("SELECT COUNT(*) FROM symptom_logs")
        total_logs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM symptom_logs WHERE advice_generated = 1")
        successful_advice = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(rag_confidence) FROM symptom_logs WHERE rag_confidence > 0")
        avg_confidence = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT COUNT(*) FROM unhandled_symptoms WHERE status = 'pending'")
        unhandled_count = cursor.fetchone()[0]
        
        # 최근 24시간 통계
        yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        cursor.execute("SELECT COUNT(*) FROM symptom_logs WHERE timestamp > ?", (yesterday,))
        recent_logs = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_logs': total_logs,
            'successful_advice': successful_advice,
            'success_rate': successful_advice / total_logs if total_logs > 0 else 0.0,
            'avg_rag_confidence': avg_confidence,
            'unhandled_symptoms': unhandled_count,
            'recent_logs_24h': recent_logs
        }
    
    def create_crawling_job(self, symptom_keywords: List[str], target_sites: List[str]) -> int:
        """크롤링 작업을 생성합니다."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO crawling_jobs (
                symptom_keywords, target_sites, created_at
            ) VALUES (?, ?, ?)
        """, (
            json.dumps(symptom_keywords),
            json.dumps(target_sites),
            datetime.now().isoformat()
        ))
        
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return job_id
    
    def update_crawling_job(self, job_id: int, status: str, results_count: int = 0, error_message: str = None):
        """크롤링 작업 상태를 업데이트합니다."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        if status == 'started':
            cursor.execute("""
                UPDATE crawling_jobs 
                SET status = ?, started_at = ?
                WHERE id = ?
            """, (status, now, job_id))
        elif status in ['completed', 'failed']:
            cursor.execute("""
                UPDATE crawling_jobs 
                SET status = ?, completed_at = ?, results_count = ?, error_message = ?
                WHERE id = ?
            """, (status, now, results_count, error_message, job_id))
        
        conn.commit()
        conn.close()

# 전역 로거 인스턴스
symptom_logger = SymptomLogger()
