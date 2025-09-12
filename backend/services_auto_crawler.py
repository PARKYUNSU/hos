"""
자동 크롤링 시스템
미처리 증상을 기반으로 자동으로 의료 데이터를 크롤링합니다.
"""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

try:
    from .services_logging import symptom_logger
except ImportError:
    # Streamlit Cloud에서 상대 import가 실패할 경우를 대비
    import sys
    import os
    sys.path.append(os.path.dirname(__file__))
    from services_logging import symptom_logger

class AutoCrawler:
    """자동 크롤링 클래스"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # 크롤링 대상 사이트들 (실제 작동하는 사이트들로 수정)
        self.target_sites = {
            'jrc': {
                'name': '日本赤十字社 (JRC)',
                'base_url': 'https://www.jrc.or.jp',
                'search_url': 'https://www.jrc.or.jp/study/kind/emergency/',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, div.content',
                    'links': 'a[href*="emergency"]'
                }
            },
            'mhlw_health': {
                'name': '厚生労働省 健康情報',
                'base_url': 'https://www.mhlw.go.jp',
                'search_url': 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, div.content',
                    'links': 'a[href*="kenkou"]'
                }
            },
            'med_or_jp': {
                'name': '日本医師会',
                'base_url': 'https://www.med.or.jp',
                'search_url': 'https://www.med.or.jp/',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, div.content',
                    'links': 'a[href*="med"]'
                }
            },
            'web_search': {
                'name': '웹 검색 (Google)',
                'base_url': 'https://www.google.com',
                'search_url': 'https://www.google.com/search?q={query}+site:jp+응급처치',
                'selectors': {
                    'title': 'h3',
                    'content': 'span',
                    'links': 'a[href*="http"]'
                }
            }
        }
    
    def extract_keywords(self, symptom_text: str) -> List[str]:
        """증상 텍스트에서 키워드를 추출합니다."""
        # 한국어-일본어 의료 용어 매핑
        korean_japanese_mapping = {
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
            # 새로운 증상들 추가
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
            '숨이 차': ['息切れ', '呼吸困難', '呼吸が苦しい']
        }
        
        keywords = []
        
        # 한국어 키워드 매핑
        for korean, japanese_terms in korean_japanese_mapping.items():
            if korean in symptom_text:
                keywords.extend(japanese_terms)
        
        # 일본어 의료 키워드 패턴
        medical_patterns = [
            r'[あ-ん]+',  # 히라가나
            r'[ア-ン]+',  # 가타카나
            r'[一-龯]+',  # 한자
        ]
        
        for pattern in medical_patterns:
            matches = re.findall(pattern, symptom_text)
            keywords.extend(matches)
        
        # 영어 의료 용어도 포함
        english_words = re.findall(r'[a-zA-Z]+', symptom_text)
        keywords.extend(english_words)
        
        # 중복 제거 및 길이 필터링
        keywords = list(set([kw for kw in keywords if len(kw) >= 2]))
        
        return keywords
    
    def search_site(self, site_key: str, keywords: List[str]) -> List[Dict]:
        """특정 사이트에서 키워드로 검색합니다."""
        site_config = self.target_sites[site_key]
        results = []
        
        try:
            # 웹 검색인 경우 특별 처리
            if site_key == 'web_search':
                return self.web_search(keywords)
            
            # 검색 URL 구성
            search_url = site_config['search_url']
            
            # 페이지 내용 가져오기
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 제목과 내용 추출
            titles = soup.select(site_config['selectors']['title'])
            contents = soup.select(site_config['selectors']['content'])
            links = soup.select(site_config['selectors']['links'])
            
            # 키워드 매칭으로 관련 내용 필터링
            for i, title in enumerate(titles):
                title_text = title.get_text().strip()
                
                # 키워드 매칭 (더 유연하게)
                matched_keywords = []
                for keyword in keywords:
                    if keyword in title_text or keyword in soup.get_text():
                        matched_keywords.append(keyword)
                
                # 매칭된 키워드가 있거나 제목이 의료 관련인 경우
                if matched_keywords or any(medical_word in title_text for medical_word in ['応急', '救急', '処置', '医療', '健康', '症状']):
                    # 관련 링크 찾기
                    related_links = []
                    for link in links:
                        link_text = link.get_text().strip()
                        if any(keyword in link_text for keyword in keywords):
                            href = link.get('href')
                            if href:
                                if href.startswith('/'):
                                    href = site_config['base_url'] + href
                                related_links.append({
                                    'text': link_text,
                                    'url': href
                                })
                    
                    # 내용 추출
                    content_text = ""
                    if i < len(contents):
                        content_text = contents[i].get_text().strip()
                    elif contents:
                        # 제목에 해당하는 내용이 없으면 전체 내용에서 관련 부분 찾기
                        full_text = soup.get_text()
                        if any(keyword in full_text for keyword in keywords):
                            content_text = full_text[:500] + "..." if len(full_text) > 500 else full_text
                    
                    results.append({
                        'site': site_config['name'],
                        'title': title_text,
                        'content': content_text,
                        'links': related_links,
                        'url': search_url,
                        'keywords_matched': matched_keywords
                    })
            
        except Exception as e:
            print(f"Error crawling {site_key}: {e}")
        
        return results
    
    def web_search(self, keywords: List[str]) -> List[Dict]:
        """웹 검색을 통해 일본 의료 정보를 찾습니다."""
        results = []
        
        try:
            # 검색 쿼리 구성
            query = '+'.join(keywords[:3])  # 상위 3개 키워드만 사용
            search_url = f"https://www.google.com/search?q={query}+site:jp+応急処置"
            
            # 검색 실행
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 검색 결과 추출
            search_results = soup.select('div.g')
            
            for result in search_results[:5]:  # 상위 5개 결과만
                title_elem = result.select_one('h3')
                content_elem = result.select_one('span')
                link_elem = result.select_one('a[href*="http"]')
                
                if title_elem and content_elem:
                    title = title_elem.get_text().strip()
                    content = content_elem.get_text().strip()
                    url = link_elem['href'] if link_elem else ''
                    
                    # 일본어 사이트인지 확인
                    if 'jp' in url or any(keyword in title for keyword in keywords):
                        results.append({
                            'title': title,
                            'content': content,
                            'url': url,
                            'site': '웹 검색 (Google)',
                            'keywords_matched': [kw for kw in keywords if kw in title]
                        })
            
        except Exception as e:
            print(f"웹 검색 오류: {e}")
        
        return results
    
    def crawl_for_symptoms(self, symptom_text: str) -> Dict:
        """증상에 대한 크롤링을 수행합니다."""
        keywords = self.extract_keywords(symptom_text)
        
        if not keywords:
            return {
                'success': False,
                'error': 'No keywords extracted',
                'results': []
            }
        
        all_results = []
        
        # 각 사이트에서 크롤링
        for site_key in self.target_sites.keys():
            try:
                site_results = self.search_site(site_key, keywords)
                all_results.extend(site_results)
            except Exception as e:
                print(f"Error crawling {site_key}: {e}")
                continue
        
        return {
            'success': True,
            'keywords': keywords,
            'results': all_results,
            'total_results': len(all_results)
        }
    
    def save_crawled_data(self, symptom_text: str, crawl_results: Dict) -> str:
        """크롤링된 데이터를 파일로 저장합니다."""
        if not crawl_results['success']:
            return None
        
        # 데이터 디렉토리 생성
        data_dir = Path("data/passages/jp")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성 (타임스탬프 + 증상)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_symptom = re.sub(r'[^\w\s-]', '', symptom_text)[:20]
        filename = f"{timestamp}_{safe_symptom}.txt"
        filepath = data_dir / filename
        
        # 데이터 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 증상: {symptom_text}\n")
            f.write(f"# 크롤링 시간: {datetime.now().isoformat()}\n")
            f.write(f"# 키워드: {', '.join(crawl_results['keywords'])}\n\n")
            
            for result in crawl_results['results']:
                f.write(f"## {result['site']} - {result['title']}\n")
                f.write(f"URL: {result['url']}\n")
                f.write(f"매칭 키워드: {', '.join(result['keywords_matched'])}\n\n")
                
                if result['content']:
                    f.write(f"{result['content']}\n\n")
                
                if result['links']:
                    f.write("관련 링크:\n")
                    for link in result['links']:
                        f.write(f"- {link['text']}: {link['url']}\n")
                    f.write("\n")
                
                f.write("-" * 50 + "\n\n")
        
        return str(filepath)
    
    def process_unhandled_symptoms(self, limit: int = 5) -> Dict:
        """미처리 증상들을 처리합니다."""
        unhandled = symptom_logger.get_unhandled_symptoms(limit)
        
        if not unhandled:
            return {
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'results': []
            }
        
        results = []
        successful = 0
        failed = 0
        
        for symptom in unhandled:
            symptom_text = symptom['symptom_text']
            
            # 크롤링 작업 생성
            keywords = self.extract_keywords(symptom_text)
            job_id = symptom_logger.create_crawling_job(
                keywords, 
                list(self.target_sites.keys())
            )
            
            try:
                # 크롤링 시작
                symptom_logger.update_crawling_job(job_id, 'started')
                
                # 크롤링 수행
                crawl_results = self.crawl_for_symptoms(symptom_text)
                
                if crawl_results['success'] and crawl_results['results']:
                    # 데이터 저장
                    filepath = self.save_crawled_data(symptom_text, crawl_results)
                    
                    if filepath:
                        # 작업 완료
                        symptom_logger.update_crawling_job(
                            job_id, 'completed', 
                            len(crawl_results['results'])
                        )
                        
                        # 미처리 증상 상태 업데이트
                        self._update_symptom_status(symptom_text, 'processed')
                        
                        successful += 1
                        results.append({
                            'symptom': symptom_text,
                            'status': 'success',
                            'filepath': filepath,
                            'results_count': len(crawl_results['results'])
                        })
                    else:
                        raise Exception("Failed to save data")
                else:
                    raise Exception("No results found")
                    
            except Exception as e:
                # 작업 실패
                symptom_logger.update_crawling_job(
                    job_id, 'failed', 0, str(e)
                )
                
                failed += 1
                results.append({
                    'symptom': symptom_text,
                    'status': 'failed',
                    'error': str(e)
                })
            
            # 요청 간격 조절
            time.sleep(2)
        
        return {
            'processed': len(unhandled),
            'successful': successful,
            'failed': failed,
            'results': results
        }
    
    def _update_symptom_status(self, symptom_text: str, status: str):
        """미처리 증상 상태를 업데이트합니다."""
        import sqlite3
        
        conn = sqlite3.connect(symptom_logger.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE unhandled_symptoms 
            SET status = ? 
            WHERE symptom_text = ?
        """, (status, symptom_text))
        
        conn.commit()
        conn.close()

# 전역 크롤러 인스턴스
auto_crawler = AutoCrawler()

def auto_crawl_unhandled_symptoms():
    """미처리 증상에 대해 자동 크롤링을 실행합니다."""
    try:
        result = auto_crawler.process_unhandled_symptoms()
        print(f"자동 크롤링 완료: {result['successful']}개 성공, {result['failed']}개 실패")
        return result
    except Exception as e:
        print(f"자동 크롤링 오류: {str(e)}")
        return {'processed': 0, 'successful': 0, 'failed': 1, 'results': []}
