from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Tuple


class SimpleRAG:
    def __init__(self, passages: List[str]):
        self.passages = passages
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=5000)
        self.matrix = self.vectorizer.fit_transform(self.passages)

    def search(self, query: str, top_k: int = 3) -> List[Tuple[str, float]]:
        if not query:
            return []
        q = self.vectorizer.transform([query])
        sim = cosine_similarity(q, self.matrix)[0]
        idxs = sim.argsort()[::-1][:top_k]
        return [(self.passages[i], float(sim[i])) for i in idxs]


DEFAULT_PASSAGES = [
    "열이 나면 미지근한 물수건으로 열을 내리고, 수분을 충분히 섭취하세요. 아세트아미노펜은 비교적 안전합니다.",
    "상처 출혈 시 직접 압박으로 지혈하고 깨끗한 물로 세척한 뒤 멸균 거즈를 적용하세요.",
    "설사 시 수분과 전해질을 보충하세요. 증상이 심하면 즉시 진료 받으세요.",
]

GLOBAL_RAG = SimpleRAG(DEFAULT_PASSAGES)


