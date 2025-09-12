"""
PDF 파일 처리 및 텍스트 추출 모듈
"""

import os
import pathlib
from typing import List, Optional, Dict
import PyPDF2
import pdfplumber
import fitz  # PyMuPDF
from pathlib import Path


class PDFProcessor:
    """PDF 파일에서 텍스트를 추출하는 클래스"""
    
    def __init__(self):
        self.supported_formats = ['.pdf']
    
    def extract_text_pymupdf(self, pdf_path: str) -> str:
        """PyMuPDF를 사용한 텍스트 추출 (가장 빠름)"""
        try:
            # URL인지 로컬 파일인지 확인
            if pdf_path.startswith(('http://', 'https://')):
                doc = fitz.open(stream=pdf_path, filetype="pdf")
            else:
                doc = fitz.open(pdf_path)
            
            text = ""
            for page_num in range(doc.page_count):
                page = doc[page_num]
                text += page.get_text() + "\n"
            doc.close()
            return text.strip()
        except Exception as e:
            print(f"PyMuPDF로 텍스트 추출 실패: {e}")
            return ""
    
    def extract_text_pypdf2(self, pdf_path: str) -> str:
        """PyPDF2를 사용한 텍스트 추출"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            print(f"PyPDF2로 텍스트 추출 실패: {e}")
            return ""
    
    def extract_text_pdfplumber(self, pdf_path: str) -> str:
        """pdfplumber를 사용한 텍스트 추출 (더 정확함)"""
        try:
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text.strip()
        except Exception as e:
            print(f"pdfplumber로 텍스트 추출 실패: {e}")
            return ""
    
    def extract_text(self, pdf_path: str) -> str:
        """PDF에서 텍스트 추출 (PyMuPDF 우선, fallback 지원)"""
        # PyMuPDF 시도 (가장 빠름)
        text = self.extract_text_pymupdf(pdf_path)
        
        # PyMuPDF가 실패하면 pdfplumber 시도
        if not text or len(text.strip()) < 10:
            text = self.extract_text_pdfplumber(pdf_path)
        
        # pdfplumber도 실패하면 PyPDF2 시도
        if not text or len(text.strip()) < 10:
            text = self.extract_text_pypdf2(pdf_path)
        
        return text
    
    def process_pdf_file(self, pdf_path: str) -> Dict[str, str]:
        """PDF 파일을 처리하고 메타데이터와 함께 반환"""
        try:
            file_path = Path(pdf_path)
            if not file_path.exists():
                return {"error": "파일이 존재하지 않습니다."}
            
            if file_path.suffix.lower() != '.pdf':
                return {"error": "PDF 파일이 아닙니다."}
            
            # 텍스트 추출
            text = self.extract_text(str(file_path))
            
            if not text:
                return {"error": "텍스트를 추출할 수 없습니다."}
            
            # 파일 정보
            file_info = {
                "filename": file_path.name,
                "size": file_path.stat().st_size,
                "text": text,
                "pages": self._count_pages(str(file_path)),
                "extraction_method": self._get_extraction_method(text, pdf_path)
            }
            
            return file_info
            
        except Exception as e:
            return {"error": f"PDF 처리 중 오류 발생: {str(e)}"}
    
    def _count_pages(self, pdf_path: str) -> int:
        """PDF 페이지 수 계산 (PyMuPDF 사용)"""
        try:
            doc = fitz.open(pdf_path)
            page_count = doc.page_count
            doc.close()
            return page_count
        except:
            return 0
    
    def _get_extraction_method(self, text: str, pdf_path: str) -> str:
        """사용된 추출 방법 확인"""
        if not text:
            return "실패"
        
        # PyMuPDF로 시도해보고 성공하면 PyMuPDF
        try:
            pymupdf_text = self.extract_text_pymupdf(pdf_path)
            if pymupdf_text and len(pymupdf_text.strip()) > 10:
                return "PyMuPDF (빠름)"
        except:
            pass
        
        # pdfplumber로 시도해보고 성공하면 pdfplumber
        try:
            pdfplumber_text = self.extract_text_pdfplumber(pdf_path)
            if pdfplumber_text and len(pdfplumber_text.strip()) > 10:
                return "pdfplumber (정확함)"
        except:
            pass
        
        return "PyPDF2 (fallback)"
    
    def batch_process_pdfs(self, directory: str) -> List[Dict[str, str]]:
        """디렉토리의 모든 PDF 파일을 일괄 처리"""
        results = []
        pdf_dir = Path(directory)
        
        if not pdf_dir.exists():
            return results
        
        for pdf_file in pdf_dir.glob("*.pdf"):
            result = self.process_pdf_file(str(pdf_file))
            if "error" not in result:
                results.append(result)
        
        return results


def load_pdf_passages(directory: str = "data/rag_data") -> List[str]:
    """PDF 파일들에서 텍스트를 추출하여 passages 리스트로 반환"""
    processor = PDFProcessor()
    pdf_dir = Path(directory)
    
    if not pdf_dir.exists():
        return []
    
    passages = []
    
    # PDF 파일들 처리
    for pdf_file in pdf_dir.glob("*.pdf"):
        try:
            result = processor.process_pdf_file(str(pdf_file))
            if "error" not in result and result.get("text"):
                # 텍스트를 청크로 나누기 (너무 긴 텍스트는 여러 개로 분할)
                text = result["text"]
                chunks = _split_text_into_chunks(text, max_chunk_size=1000)
                
                for i, chunk in enumerate(chunks):
                    if chunk.strip():
                        # 청크에 메타데이터 추가
                        chunk_with_meta = f"[PDF: {result['filename']}, 페이지: {i+1}/{len(chunks)}]\n{chunk}"
                        passages.append(chunk_with_meta)
                        
        except Exception as e:
            print(f"PDF 파일 처리 실패 {pdf_file}: {e}")
            continue
    
    return passages


def _split_text_into_chunks(text: str, max_chunk_size: int = 1000) -> List[str]:
    """긴 텍스트를 적절한 크기의 청크로 분할"""
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    sentences = text.split('. ')
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk + sentence) <= max_chunk_size:
            current_chunk += sentence + ". "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + ". "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def load_pdf_from_url(url: str) -> Dict[str, str]:
    """URL에서 PDF를 직접 로드하여 텍스트 추출"""
    import requests
    
    try:
        # URL에서 PDF 다운로드
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # PDF 문서 열기
        doc = fitz.open(stream=response.content, filetype="pdf")
        page_count = doc.page_count  # 문서 닫기 전에 페이지 수 저장
        text = ""
        for page_num in range(page_count):
            page = doc[page_num]
            text += page.get_text() + "\n"
        doc.close()
        
        if not text.strip():
            return {"error": "PDF에서 텍스트를 추출할 수 없습니다."}
        
        # URL에서 파일명 추출
        filename = url.split('/')[-1]
        if not filename.endswith('.pdf'):
            filename += '.pdf'
        
        result = {
            "filename": filename,
            "url": url,
            "text": text.strip(),
            "pages": page_count,
            "extraction_method": "PyMuPDF (URL)",
            "size": len(text.encode('utf-8'))
        }
        
        return result
        
    except Exception as e:
        return {"error": f"URL에서 PDF 로드 실패: {str(e)}"}


def convert_pdf_to_txt(pdf_path: str, output_dir: str = "data/rag_data") -> Optional[str]:
    """PDF를 텍스트 파일로 변환하여 저장"""
    processor = PDFProcessor()
    result = processor.process_pdf_file(pdf_path)
    
    if "error" in result:
        return None
    
    # 출력 파일명 생성
    pdf_file = Path(pdf_path)
    txt_filename = pdf_file.stem + ".txt"
    output_path = Path(output_dir) / txt_filename
    
    try:
        # 출력 디렉토리 생성
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 텍스트 파일로 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result["text"])
        
        return str(output_path)
        
    except Exception as e:
        print(f"텍스트 파일 저장 실패: {e}")
        return None


# 테스트 함수
def test_pdf_processing():
    """PDF 처리 기능 테스트"""
    processor = PDFProcessor()
    
    # 테스트용 PDF 파일이 있다면 테스트
    test_pdf = "data/rag_data/test.pdf"
    if Path(test_pdf).exists():
        result = processor.process_pdf_file(test_pdf)
        print(f"PDF 처리 결과: {result}")
    else:
        print("테스트용 PDF 파일이 없습니다.")


if __name__ == "__main__":
    test_pdf_processing()
