from typing import List, Tuple
import pathlib
import re
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class HybridRAG:
    def __init__(self, passages: List[str]):
        self.passages = passages
        self.tokenized = [self._tokenize(p) for p in passages]
        self.bm25 = BM25Okapi(self.tokenized)
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=8000)
        self.tfidf = self.vectorizer.fit_transform(passages)

    def _tokenize(self, text: str) -> List[str]:
        # 간단한 토큰화 (공백, 구두점으로 분리)
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        if not query:
            return []
        q_tokens = self._tokenize(query)
        bm_scores = self.bm25.get_scores(q_tokens)
        q_vec = self.vectorizer.transform([query])
        tf_scores = cosine_similarity(q_vec, self.tfidf)[0]
        # 간단한 late fusion
        scores = [(i, 0.6 * bm_scores[i] + 0.4 * tf_scores[i]) for i in range(len(self.passages))]
        scores.sort(key=lambda x: x[1], reverse=True)
        idxs = [i for i, _ in scores[:top_k]]
        return [(self.passages[i], float(scores[j][1])) for j, i in enumerate(idxs)]


def load_disk_passages() -> list[str]:
    root = pathlib.Path(__file__).resolve().parents[1]
    pdir = root / "data" / "passages" / "jp"
    if not pdir.exists():
        return []
    out = []
    for p in sorted(pdir.glob("*.txt")):
        try:
            out.append(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return out


def load_rag_data_passages() -> list[str]:
    """RAG 데이터 디렉토리에서 텍스트와 PDF 파일들을 로드"""
    root = pathlib.Path(__file__).resolve().parents[1]
    rag_dir = root / "data" / "rag_data"
    
    if not rag_dir.exists():
        return []
    
    passages = []
    
    # 텍스트 파일들 로드
    for txt_file in sorted(rag_dir.glob("*.txt")):
        try:
            text = txt_file.read_text(encoding="utf-8")
            if text.strip():
                passages.append(text)
        except Exception:
            continue
    
    # PDF 파일들 로드
    try:
        from .services_pdf_processor import load_pdf_passages
        pdf_passages = load_pdf_passages(str(rag_dir))
        passages.extend(pdf_passages)
    except ImportError:
        print("PDF 처리 모듈을 찾을 수 없습니다. PDF 파일은 무시됩니다.")
    except Exception as e:
        print(f"PDF 파일 처리 중 오류: {e}")
    
    return passages


DEFAULT_PASSAGES = [
    "熱があるときはぬるま湯で体を冷やし、水分を十分にとりましょう。アセトアミノフェンは比較的安全です。",
    "出血している傷は直接圧迫で止血し、きれいな水で洗浄後、滅菌ガーゼを当ててください。",
    "下痢のときは水分・電解質の補給を行ってください。症状が重い場合は受診してください。",
]
_disk = load_disk_passages()
_rag_data = load_rag_data_passages()
_all_passages = _disk + _rag_data
GLOBAL_RAG = HybridRAG(_all_passages if _all_passages else DEFAULT_PASSAGES)


