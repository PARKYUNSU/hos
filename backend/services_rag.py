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
        
        # 한국어-일본어 의료 용어 매핑
        self.korean_japanese_mapping = {
            '벌레 물림': ['虫刺され', '虫に刺された', '虫刺症'],
            '말벌 쏘임': ['蜂に刺された', '蜂刺症', 'ハチ刺し'],
            '모기 물림': ['蚊に刺された', '蚊刺症', '蚊刺され'],
            '발열': ['発熱', '熱', '体温上昇'],
            '어지러움': ['めまい', '眩暈', '立ちくらみ'],
            '두통': ['頭痛', '頭が痛い'],
            '복통': ['腹痛', 'お腹が痛い', '腹部痛'],
            '구토': ['嘔吐', '吐く', '吐き気'],
            '설사': ['下痢', '下痢症'],
            '코피': ['鼻血', '鼻出血'],
            '손목': ['手首', '手関節'],
            '발진': ['発疹', '皮疹', '湿疹'],
            '마비': ['麻痺', 'しびれ', '感覚麻痺'],
            '목 아픔': ['首の痛み', '頸部痛', '首痛'],
            '가슴 답답': ['胸苦しい', '胸の圧迫感', '胸部不快感'],
            '호흡곤란': ['呼吸困難', '息切れ', '呼吸が苦しい'],
            '알레르기': ['アレルギー', '過敏症'],
            '응급처치': ['応急処置', '救急処置', '応急手当'],
            '눈이 부어': ['目の腫れ', '眼瞼浮腫', '眼の腫脹'],
            '눈 부어': ['目の腫れ', '眼瞼浮腫', '眼の腫脹'],
            '목소리': ['声', '音声', '発声'],
            '목소리가 나오지': ['声が出ない', '失声', '音声障害'],
            '손발이 차가워': ['手足が冷たい', '四肢冷感', '末梢循環不全'],
            '손발 차가워': ['手足が冷たい', '四肢冷感', '末梢循環不全'],
            '배가 아프고': ['お腹が痛くて', '腹痛と', '腹部痛と'],
            '머리가 아프고': ['頭が痛くて', '頭痛と', '頭部痛と'],
            '가슴이 두근거리고': ['胸がドキドキして', '動悸と', '心拍数増加と'],
            '숨이 차요': ['息切れ', '呼吸困難', '呼吸が苦しい'],
            '숨이 차': ['息切れ', '呼吸困難', '呼吸が苦しい'],
            '열': ['熱', '発熱', '体温上昇'],
            '기침': ['咳', '咳嗽'],
            '코막힘': ['鼻づまり', '鼻閉'],
            '인후통': ['喉の痛み', '咽頭痛'],
            '치통': ['歯痛', '歯の痛み'],
            '상처': ['傷', '外傷', '切り傷'],
            '출혈': ['出血', '流血'],
            '탈수': ['脱水', '脱水症状'],
            '경련': ['痙攣', 'けいれん'],
            '의식 잃음': ['意識喪失', '失神'],
            '호흡 정지': ['呼吸停止', '無呼吸'],
            '심정지': ['心停止', '心臓停止']
        }

    def _tokenize(self, text: str) -> List[str]:
        # 다국어 토큰화 (한국어, 일본어, 영어 모두 지원)
        # 한국어와 일본어는 공백으로 분리, 영어는 단어 경계로 분리
        tokens = []
        
        # 한국어/일본어 단어 (공백으로 분리)
        korean_japanese_words = re.findall(r'[가-힣あ-んア-ン一-龯]+', text)
        tokens.extend([word.lower() for word in korean_japanese_words])
        
        # 영어 단어 (단어 경계로 분리)
        english_words = re.findall(r'\b[a-zA-Z]+\b', text)
        tokens.extend([word.lower() for word in english_words])
        
        # 숫자
        numbers = re.findall(r'\d+', text)
        tokens.extend(numbers)
        
        return tokens

    def _translate_korean_to_japanese(self, query: str) -> str:
        """한국어 쿼리를 일본어로 변환합니다."""
        translated_terms = []
        
        # 한국어 키워드 매핑
        for korean, japanese_terms in self.korean_japanese_mapping.items():
            if korean in query:
                translated_terms.extend(japanese_terms)
        
        # 원본 쿼리와 번역된 용어들을 결합
        if translated_terms:
            return query + " " + " ".join(translated_terms)
        return query

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        if not query:
            return []
        
        # 한국어 쿼리를 일본어로 변환
        enhanced_query = self._translate_korean_to_japanese(query)
        
        # 변환된 쿼리로 검색
        q_tokens = self._tokenize(enhanced_query)
        bm_scores = self.bm25.get_scores(q_tokens)
        q_vec = self.vectorizer.transform([enhanced_query])
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
    # 발열 관련
    "熱があるときはぬるま湯で体を冷やし、水分を十分にとりましょう。アセトアミノフェンは比較的安全です。",
    "発熱時の応急処置：体温を下げるため、首、脇の下、足の付け根を冷やします。解熱剤はアセトアミノフェンが安全です。",
    "高熱の場合は脱水症状に注意し、水分補給を心がけてください。39度以上の熱が続く場合は医療機関を受診してください。",
    
    # 두통 관련
    "頭痛の応急処置：安静にし、暗い部屋で休みます。痛みが激しい場合は鎮痛剤（アセトアミノフェン）を服用してください。",
    "頭痛の原因は様々です。突然の激しい頭痛や意識障害を伴う場合は救急車を呼んでください。",
    
    # 복통 관련
    "腹痛の応急処置：温かい飲み物を飲み、腹部を温めます。激しい痛みの場合は絶食し、医療機関を受診してください。",
    "下痢のときは水分・電解質の補給を行ってください。症状が重い場合は受診してください。",
    "胃痛の場合は消化の良いものを食べ、胃を休めます。制酸剤や胃薬を服用することもできます。",
    
    # 벌레 물림 관련
    "虫刺されの応急処置：刺された部分を流水で洗い、冷やします。かゆみが強い場合は抗ヒスタミン剤を塗布してください。",
    "蜂に刺された場合は針を抜き、患部を冷やします。アレルギー反応がある場合は救急車を呼んでください。",
    "蚊に刺された場合は患部を清潔に保ち、かゆみ止めを塗布します。感染症の心配がある場合は医療機関を受診してください。",
    
    # 어지러움 관련
    "めまいの応急処置：安静にし、横になって休みます。水分補給を心がけ、症状が続く場合は医療機関を受診してください。",
    "立ちくらみの場合は座るか横になり、血圧の安定を待ちます。頻繁に起こる場合は医師に相談してください。",
    
    # 기타 응급처치
    "出血している傷は直接圧迫で止血し、きれいな水で洗浄後、滅菌ガーゼを当ててください。",
    "やけどの応急処置：流水で20分以上冷やします。水ぶくれができた場合は医療機関を受診してください。",
    "骨折の疑いがある場合は患部を動かさず、添え木で固定して医療機関を受診してください。",
    "意識がない場合は気道を確保し、呼吸を確認します。呼吸がない場合は心肺蘇生を行ってください。",
]
_disk = load_disk_passages()
_rag_data = load_rag_data_passages()
_all_passages = _disk + _rag_data + DEFAULT_PASSAGES
GLOBAL_RAG = HybridRAG(_all_passages)


