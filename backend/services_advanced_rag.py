"""
고도화된 RAG 시스템
- Sentence-BERT 임베딩
- Dense + Sparse 검색 결합
- 쿼리 확장 및 리랭킹
"""

import numpy as np
import pickle
import os
from typing import List, Tuple, Dict, Optional
from pathlib import Path
import re
import time
from concurrent.futures import ThreadPoolExecutor

# 기존 RAG 시스템
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Sentence-BERT 임베딩
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not available. Install with: pip install sentence-transformers")

# 쿼리 확장을 위한 라이브러리
try:
    import nltk
    from nltk.corpus import wordnet
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    print("Warning: NLTK not available. Install with: pip install nltk")


class AdvancedRAG:
    """고도화된 RAG 시스템"""
    
    def __init__(self, passages: List[str], model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.passages = passages
        self.model_name = model_name
        
        # 임베딩 모델 초기화
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            self.embedding_model = SentenceTransformer(model_name)
        else:
            self.embedding_model = None
            print("Warning: Using fallback embedding model")
        
        # 캐시 디렉토리 설정
        self.cache_dir = Path("data/cache/embeddings")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 임베딩 로드 또는 생성
        self.passage_embeddings = self._load_or_create_embeddings()
        
        # Sparse 검색 초기화 (기존 시스템)
        self.tokenized = [self._tokenize(p) for p in passages]
        self.bm25 = BM25Okapi(self.tokenized)
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=8000)
        self.tfidf = self.vectorizer.fit_transform(passages)
        
        # 쿼리 확장 초기화
        if NLTK_AVAILABLE:
            self._init_nltk()
    
    def _init_nltk(self):
        """NLTK 초기화"""
        try:
            nltk.data.find('corpora/wordnet')
        except LookupError:
            nltk.download('wordnet', quiet=True)
    
    def _tokenize(self, text: str) -> List[str]:
        """텍스트 토큰화"""
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens
    
    def _get_cache_path(self) -> Path:
        """임베딩 캐시 파일 경로"""
        passages_hash = hash(tuple(self.passages))
        return self.cache_dir / f"embeddings_{self.model_name}_{passages_hash}.pkl"
    
    def _load_or_create_embeddings(self) -> np.ndarray:
        """임베딩 로드 또는 생성"""
        cache_path = self._get_cache_path()
        
        # 캐시에서 로드 시도
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    embeddings = pickle.load(f)
                print(f"Loaded embeddings from cache: {cache_path}")
                return embeddings
            except Exception as e:
                print(f"Failed to load cache: {e}")
        
        # 임베딩 생성
        if self.embedding_model is None:
            # Fallback: TF-IDF 벡터 사용
            print("Using TF-IDF as fallback embedding")
            tfidf_matrix = TfidfVectorizer(max_features=512).fit_transform(self.passages)
            embeddings = tfidf_matrix.toarray()
        else:
            print(f"Creating embeddings with {self.model_name}...")
            embeddings = self.embedding_model.encode(
                self.passages, 
                show_progress_bar=True,
                batch_size=32
            )
        
        # 캐시에 저장
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(embeddings, f)
            print(f"Saved embeddings to cache: {cache_path}")
        except Exception as e:
            print(f"Failed to save cache: {e}")
        
        return embeddings
    
    def _expand_query(self, query: str) -> List[str]:
        """쿼리 확장"""
        if not NLTK_AVAILABLE:
            return [query]
        
        expanded_queries = [query]
        
        try:
            # 동의어 확장
            words = query.lower().split()
            for word in words:
                synsets = wordnet.synsets(word)
                for synset in synsets[:2]:  # 최대 2개 synset
                    for lemma in synset.lemmas()[:3]:  # 최대 3개 lemma
                        synonym = lemma.name().replace('_', ' ')
                        if synonym != word and len(synonym.split()) == 1:
                            expanded_queries.append(query.replace(word, synonym))
            
            # 의료 용어 확장 (간단한 매핑)
            medical_expansions = {
                '열': ['발열', '고열', '체온상승'],
                '두통': ['머리아픔', '두부통증'],
                '복통': ['배아픔', '위통', '복부통증'],
                '설사': ['하리', '변비반대'],
                '기침': ['해수', '기침증상'],
                '벌레': ['곤충', '해충'],
                '물림': ['교상', '쏘임'],
                '화상': ['화상상처', '열상처']
            }
            
            for korean, expansions in medical_expansions.items():
                if korean in query:
                    for expansion in expansions:
                        expanded_queries.append(query.replace(korean, expansion))
            
        except Exception as e:
            print(f"Query expansion error: {e}")
        
        # 중복 제거 및 길이 제한
        expanded_queries = list(set(expanded_queries))[:5]
        return expanded_queries
    
    def _dense_search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """Dense 검색 (임베딩 기반)"""
        if self.embedding_model is None:
            # Fallback: TF-IDF 기반 검색
            q_vec = self.vectorizer.transform([query])
            scores = cosine_similarity(q_vec, self.tfidf)[0]
        else:
            # Sentence-BERT 임베딩 기반 검색
            query_embedding = self.embedding_model.encode([query])
            scores = cosine_similarity(query_embedding, self.passage_embeddings)[0]
        
        # 상위 k개 선택
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(idx, float(scores[idx])) for idx in top_indices]
    
    def _sparse_search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """Sparse 검색 (BM25 + TF-IDF)"""
        q_tokens = self._tokenize(query)
        bm_scores = self.bm25.get_scores(q_tokens)
        q_vec = self.vectorizer.transform([query])
        tf_scores = cosine_similarity(q_vec, self.tfidf)[0]
        
        # BM25와 TF-IDF 결합
        combined_scores = 0.6 * bm_scores + 0.4 * tf_scores
        
        # 상위 k개 선택
        top_indices = np.argsort(combined_scores)[::-1][:top_k]
        return [(idx, float(combined_scores[idx])) for idx in top_indices]
    
    def _rerank_results(self, query: str, candidates: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        """결과 리랭킹"""
        if len(candidates) <= 1:
            return candidates
        
        # 쿼리 확장
        expanded_queries = self._expand_query(query)
        
        # 각 후보에 대해 확장된 쿼리들과의 유사도 계산
        reranked_scores = []
        for idx, original_score in candidates:
            passage = self.passages[idx]
            
            # 확장된 쿼리들과의 유사도 계산
            max_similarity = original_score
            for expanded_query in expanded_queries[1:]:  # 원본 쿼리 제외
                if self.embedding_model:
                    query_emb = self.embedding_model.encode([expanded_query])
                    passage_emb = self.passage_embeddings[idx:idx+1]
                    similarity = cosine_similarity(query_emb, passage_emb)[0][0]
                    max_similarity = max(max_similarity, similarity)
            
            # 키워드 매칭 보너스
            query_words = set(self._tokenize(query))
            passage_words = set(self._tokenize(passage))
            keyword_bonus = len(query_words.intersection(passage_words)) / len(query_words)
            
            # 최종 점수 계산
            final_score = 0.7 * max_similarity + 0.3 * keyword_bonus
            reranked_scores.append((idx, final_score))
        
        # 점수순 정렬
        reranked_scores.sort(key=lambda x: x[1], reverse=True)
        return reranked_scores
    
    def search(self, query: str, top_k: int = 5, use_reranking: bool = True) -> List[Tuple[str, float]]:
        """통합 검색"""
        if not query:
            return []
        
        # 1. Dense 검색
        dense_results = self._dense_search(query, top_k * 2)
        
        # 2. Sparse 검색
        sparse_results = self._sparse_search(query, top_k * 2)
        
        # 3. 결과 결합 (Reciprocal Rank Fusion)
        combined_scores = {}
        for rank, (idx, score) in enumerate(dense_results):
            rrf_score = 1.0 / (60 + rank + 1)  # Dense 검색 가중치
            combined_scores[idx] = combined_scores.get(idx, 0) + rrf_score
        
        for rank, (idx, score) in enumerate(sparse_results):
            rrf_score = 1.0 / (60 + rank + 1)  # Sparse 검색 가중치
            combined_scores[idx] = combined_scores.get(idx, 0) + rrf_score
        
        # 4. 상위 후보 선택
        candidates = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:top_k * 2]
        candidates = [(idx, score) for idx, score in candidates]
        
        # 5. 리랭킹 (선택적)
        if use_reranking and len(candidates) > 1:
            candidates = self._rerank_results(query, candidates)
        
        # 6. 최종 결과 반환
        final_results = []
        for idx, score in candidates[:top_k]:
            final_results.append((self.passages[idx], score))
        
        return final_results
    
    def get_search_stats(self) -> Dict:
        """검색 통계 정보"""
        return {
            "total_passages": len(self.passages),
            "embedding_model": self.model_name if self.embedding_model else "TF-IDF Fallback",
            "cache_available": self._get_cache_path().exists(),
            "nltk_available": NLTK_AVAILABLE,
            "sentence_transformers_available": SENTENCE_TRANSFORMERS_AVAILABLE
        }


def load_disk_passages() -> List[str]:
    """디스크에서 패시지 로드"""
    root = Path(__file__).resolve().parents[1]
    pdir = root / "data" / "passages" / "jp"
    if not pdir.exists():
        return []
    
    passages = []
    for p in sorted(pdir.glob("*.txt")):
        try:
            content = p.read_text(encoding="utf-8")
            if content.strip():  # 빈 파일 제외
                passages.append(content)
        except Exception:
            continue
    
    return passages


# 전역 인스턴스
DEFAULT_PASSAGES = [
    "熱があるときはぬるま湯で体を冷やし、水分を十分にとりましょう。アセトアミノフェンは比較的安全です。",
    "出血している傷は直接圧迫で止血し、きれいな水で洗浄後、滅菌ガーゼを当ててください。",
    "下痢のときは水分・電解質の補給を行ってください。症状が重い場合は受診してください。",
    "벌레 물림이나 말벌 쏘임의 경우, 즉시 해당 부위를 깨끗한 물로 씻고, 얼음팩으로 부기를 줄이세요. 알레르기 반응이 있으면 즉시 의료진에게 연락하세요.",
]

_disk_passages = load_disk_passages()
GLOBAL_ADVANCED_RAG = AdvancedRAG(_disk_passages if _disk_passages else DEFAULT_PASSAGES)
