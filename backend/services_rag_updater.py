"""
RAG 데이터 자동 업데이트 시스템
새로 크롤링된 데이터를 RAG 시스템에 자동으로 통합합니다.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from .services_rag import HybridRAG, load_disk_passages
from .services_logging import symptom_logger

class RAGUpdater:
    """RAG 데이터 업데이트 클래스"""
    
    def __init__(self, passages_dir: str = "data/passages/jp"):
        self.passages_dir = Path(passages_dir)
        self.passages_dir.mkdir(parents=True, exist_ok=True)
        
        # 백업 디렉토리
        self.backup_dir = Path("data/passages_backup")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 메타데이터 파일
        self.metadata_file = self.passages_dir / "metadata.json"
        
    def load_metadata(self) -> Dict:
        """메타데이터를 로드합니다."""
        if self.metadata_file.exists():
            import json
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'last_update': None,
            'total_files': 0,
            'file_hashes': {},
            'version': 1
        }
    
    def save_metadata(self, metadata: Dict):
        """메타데이터를 저장합니다."""
        import json
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def get_file_hash(self, filepath: Path) -> str:
        """파일의 해시를 계산합니다."""
        import hashlib
        
        with open(filepath, 'rb') as f:
            content = f.read()
            return hashlib.md5(content).hexdigest()
    
    def scan_new_files(self) -> List[Path]:
        """새로 추가된 파일들을 스캔합니다."""
        metadata = self.load_metadata()
        new_files = []
        
        # 모든 텍스트 파일 스캔
        for filepath in self.passages_dir.glob("*.txt"):
            if filepath.name == "metadata.json":
                continue
                
            file_hash = self.get_file_hash(filepath)
            
            # 새 파일이거나 변경된 파일
            if (filepath.name not in metadata['file_hashes'] or 
                metadata['file_hashes'][filepath.name] != file_hash):
                new_files.append(filepath)
                metadata['file_hashes'][filepath.name] = file_hash
        
        return new_files
    
    def backup_current_data(self) -> str:
        """현재 데이터를 백업합니다."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}"
        
        if self.passages_dir.exists():
            shutil.copytree(self.passages_dir, backup_path)
        
        return str(backup_path)
    
    def update_rag_system(self) -> Dict:
        """RAG 시스템을 업데이트합니다."""
        # 새 파일 스캔
        new_files = self.scan_new_files()
        
        if not new_files:
            return {
                'success': True,
                'message': 'No new files to update',
                'new_files': 0,
                'total_files': len(list(self.passages_dir.glob("*.txt")))
            }
        
        # 백업 생성
        backup_path = self.backup_current_data()
        
        try:
            # 새 파일들을 RAG 시스템에 통합
            self._integrate_new_files(new_files)
            
            # 메타데이터 업데이트
            metadata = self.load_metadata()
            metadata['last_update'] = datetime.now().isoformat()
            metadata['total_files'] = len(list(self.passages_dir.glob("*.txt")))
            self.save_metadata(metadata)
            
            # RAG 시스템 재초기화 (전역 변수 업데이트)
            self._reinitialize_rag()
            
            return {
                'success': True,
                'message': f'Successfully updated with {len(new_files)} new files',
                'new_files': len(new_files),
                'total_files': metadata['total_files'],
                'backup_path': backup_path
            }
            
        except Exception as e:
            # 실패 시 백업에서 복원
            if Path(backup_path).exists():
                shutil.rmtree(self.passages_dir)
                shutil.copytree(backup_path, self.passages_dir)
            
            return {
                'success': False,
                'error': str(e),
                'backup_restored': True
            }
    
    def _integrate_new_files(self, new_files: List[Path]):
        """새 파일들을 RAG 시스템에 통합합니다."""
        for filepath in new_files:
            # 파일 내용 검증
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 최소 길이 검증
                if len(content.strip()) < 50:
                    print(f"Skipping {filepath.name}: content too short")
                    continue
                
                # 중복 내용 검사
                if self._is_duplicate_content(content):
                    print(f"Skipping {filepath.name}: duplicate content")
                    continue
                
                print(f"Integrated {filepath.name}")
                
            except Exception as e:
                print(f"Error processing {filepath.name}: {e}")
                continue
    
    def _is_duplicate_content(self, content: str) -> bool:
        """중복 내용인지 검사합니다."""
        # 간단한 중복 검사 (실제로는 더 정교한 방법 사용 가능)
        existing_files = list(self.passages_dir.glob("*.txt"))
        
        for existing_file in existing_files:
            if existing_file.name == "metadata.json":
                continue
                
            try:
                with open(existing_file, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
                
                # 내용 유사도 검사 (간단한 버전)
                if len(content) > 100 and len(existing_content) > 100:
                    # 첫 100자와 마지막 100자 비교
                    content_start = content[:100]
                    content_end = content[-100:]
                    
                    existing_start = existing_content[:100]
                    existing_end = existing_content[-100:]
                    
                    if (content_start == existing_start and 
                        content_end == existing_end):
                        return True
                        
            except Exception:
                continue
        
        return False
    
    def _reinitialize_rag(self):
        """RAG 시스템을 재초기화합니다."""
        # 전역 RAG 객체 업데이트
        import sys
        if 'backend.services_rag' in sys.modules:
            rag_module = sys.modules['backend.services_rag']
            
            # 새 패시지 로드
            new_passages = load_disk_passages()
            
            # RAG 시스템 재초기화
            rag_module.GLOBAL_RAG = HybridRAG(new_passages)
            
            print(f"RAG system reinitialized with {len(new_passages)} passages")
    
    def get_rag_statistics(self) -> Dict:
        """RAG 시스템 통계를 가져옵니다."""
        metadata = self.load_metadata()
        
        # 현재 파일 수
        current_files = len(list(self.passages_dir.glob("*.txt")))
        
        # 파일 크기 통계
        total_size = 0
        for filepath in self.passages_dir.glob("*.txt"):
            if filepath.name != "metadata.json":
                total_size += filepath.stat().st_size
        
        return {
            'total_files': current_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'last_update': metadata.get('last_update'),
            'version': metadata.get('version', 1)
        }
    
    def cleanup_old_backups(self, keep_days: int = 7):
        """오래된 백업을 정리합니다."""
        import time
        
        cutoff_time = time.time() - (keep_days * 24 * 60 * 60)
        
        for backup_dir in self.backup_dir.iterdir():
            if backup_dir.is_dir() and backup_dir.stat().st_mtime < cutoff_time:
                shutil.rmtree(backup_dir)
                print(f"Removed old backup: {backup_dir.name}")

# 전역 업데이터 인스턴스
rag_updater = RAGUpdater()
