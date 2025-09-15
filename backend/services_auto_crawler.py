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
from typing import Dict, List, Optional, Set
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from .services_logging import symptom_logger
    from .services_playwright_crawler import (
        is_playwright_enabled,
        fetch_html_with_playwright,
    )
except ImportError:
    # Streamlit Cloud에서 상대 import가 실패할 경우를 대비
    import sys
    import os
    sys.path.append(os.path.dirname(__file__))
    from services_logging import symptom_logger
    from services_playwright_crawler import (
        is_playwright_enabled,
        fetch_html_with_playwright,
    )

class AutoCrawler:
    """자동 크롤링 클래스"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # 도메인 화이트리스트 (우선순위 높은 공공/의료)
        self.allowed_domains: Set[str] = set([
            'www.jrc.or.jp', 'jrc.or.jp',
            'www.mhlw.go.jp', 'mhlw.go.jp',
            'www.fdma.go.jp', 'fdma.go.jp',
            'www.pmda.go.jp', 'pmda.go.jp',
            'www.rad-ar.or.jp', 'rad-ar.or.jp',
            'www.jrs.or.jp', 'jrs.or.jp',
            'www.niph.go.jp', 'niph.go.jp',
            'www.j-circ.or.jp', 'j-circ.or.jp',
            'www.jaam.jp', 'jaam.jp'
        ])
        # 링크 탐색 상한
        try:
            self.max_links_per_site = int(os.getenv('CRAWL_MAX_LINKS_PER_SITE', '5'))
        except Exception:
            self.max_links_per_site = 5
        
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
                    'content': 'p, li, div.content, article, section',
                    'links': 'a[href*="kenkou"], a[href*="iryou"], a[href*="/stf/"]'
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
            'fdma': {
                'name': '総務省消防庁 (FDMA)',
                'base_url': 'https://www.fdma.go.jp',
                'search_url': 'https://www.fdma.go.jp/publication/rescue/',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, article, section',
                    'links': 'a[href]'
                }
            },
            'pmda': {
                'name': 'PMDA',
                'base_url': 'https://www.pmda.go.jp',
                'search_url': 'https://www.pmda.go.jp/guide/otc-info.html',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, article, section',
                    'links': 'a[href]'
                }
            },
            'rad_ar': {
                'name': 'RAD-AR くすりのしおり',
                'base_url': 'https://www.rad-ar.or.jp',
                'search_url': 'https://www.rad-ar.or.jp/',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, article, section',
                    'links': 'a[href]'
                }
            },
            'jrs': {
                'name': '日本呼吸器学会 (JRS)',
                'base_url': 'https://www.jrs.or.jp',
                'search_url': 'https://www.jrs.or.jp/',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, article, section',
                    'links': 'a[href]'
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
        # 방문 중복 방지
        self._visited_urls: Set[str] = set()

    def _is_allowed(self, url: str) -> bool:
        try:
            netloc = urlparse(url).netloc.lower()
            if not self.allowed_domains:
                return True
            return any(netloc.endswith(d) for d in self.allowed_domains)
        except Exception:
            return False

    def _fetch_html(self, url: str, wait_selector: Optional[str] = None) -> Optional[str]:
        html: Optional[str] = None
        if 'http' in url and is_playwright_enabled():
            html = fetch_html_with_playwright(url, wait_selector=wait_selector)
        if not html:
            try:
                resp = self.session.get(url, timeout=12)
                resp.raise_for_status()
                # PDF 등 바이너리는 스킵
                ctype = (resp.headers.get('content-type') or '').lower()
                if 'pdf' in ctype:
                    return None
                html = resp.text
            except Exception:
                return None
        return html

    def _download_pdf(self, url: str) -> Optional[str]:
        try:
            if not url.lower().endswith('.pdf'):
                # 콘텐츠 타입 확인
                head = self.session.get(url, timeout=10, stream=True)
                ctype = (head.headers.get('content-type') or '').lower()
                if 'pdf' not in ctype:
                    return None
            # 다운로드
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            out_dir = Path('data/rag_data')
            out_dir.mkdir(parents=True, exist_ok=True)
            name = urlparse(url).path.split('/')[-1] or 'download.pdf'
            if not name.endswith('.pdf'):
                name += '.pdf'
            safe = re.sub(r'[^\w\-\.]+', '_', name)
            path = out_dir / safe
            path.write_bytes(resp.content)
            return str(path)
        except Exception:
            return None
    
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

        # 일상적 표현 매핑 보강
        korean_japanese_mapping.update({
            '머리가 아파요': ['頭痛', '頭が痛い', '片頭痛', '緊張型頭痛', '群発頭痛', '解熱鎮痛薬'],
            '어지러워요': ['めまい', '立ちくらみ', '良性発作性頭位めまい症', 'BPPV', '低血圧', '貧血'],
            '가슴이 아파요': ['胸痛', '狭心症', '心筋梗塞', '肋間神経痛', '胸部圧迫感', '救急'],
            '코피가 나요': ['鼻血', '鼻出血', '止血', '圧迫'],
            '목이 아파요': ['喉の痛み', '咽頭炎', '扁桃炎', 'のどの痛み', 'うがい', '鎮痛解熱薬'],
            '코막힘이 심해요': ['鼻づまり', '鼻閉', 'アレルギー性鼻炎', '点鼻薬', '抗ヒスタミン'],
            '치통이 있어요': ['歯痛', '虫歯', '歯周炎', '鎮痛薬', '歯科'],
            '상처가 있어요': ['傷', '外傷', '切創', '擦過傷', '止血', '消毒', 'ガーゼ'],
            '출혈이 멈추지 않아요': ['出血', '止血', '圧迫止血', '救急'],
            '탈수 증상이 있어요': ['脱水', '経口補水液', 'OS-1', '水分補給'],
            '경련이 있어요': ['痙攣', 'けいれん', '発作', 'てんかん', '救急'],
            '의식을 잃었어요': ['意識消失', '失神', '意識障害', '救急車', '119'],
        })
        
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
        
        # 키워드가 비었으면 간단 폴백 규칙 적용
        if not keywords:
            t = symptom_text
            if '머리' in t:
                keywords.extend(['頭痛', '解熱鎮痛薬'])
            if ('어지' in t) or ('현기' in t):
                keywords.extend(['めまい', '立ちくらみ'])
            if '가슴' in t:
                keywords.extend(['胸痛', '胸部圧迫感', '救急'])
            if '코피' in t:
                keywords.extend(['鼻血', '止血'])
            if ('숨' in t) or ('호흡' in t):
                keywords.extend(['呼吸困難', '息切れ'])
            if ('목' in t) or ('목이' in t):
                keywords.extend(['喉の痛み', '咽頭炎'])
            if '코막힘' in t:
                keywords.extend(['鼻づまり', '鼻閉'])
            if '치통' in t or '치아' in t:
                keywords.extend(['歯痛', '虫歯'])
            if '상처' in t:
                keywords.extend(['外傷', '切創', '止血'])
            if '출혈' in t:
                keywords.extend(['出血', '圧迫止血'])
            if '탈수' in t:
                keywords.extend(['脱水', '経口補水液'])
            if '경련' in t:
                keywords.extend(['痙攣', '発作'])
            if ('의식' in t) or ('기절' in t):
                keywords.extend(['意識消失', '失神', '救急車'])

        # 중복 제거 및 길이 필터링
        keywords = list(set([kw for kw in keywords if isinstance(kw, str) and len(kw.strip()) >= 2]))
        
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
            
            # 페이지 내용 가져오기 (Playwright 우선, 실패 시 requests)
            html: Optional[str] = self._fetch_html(
                search_url,
                wait_selector=site_config['selectors'].get('title', None),
            )
            if not html:
                return results
            
            soup = BeautifulSoup(html, 'html.parser')
            
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
            # 링크 추적(Depth 1): 관련 링크를 방문해 본문 추출 및 PDF 저장
            followed = 0
            for link in links:
                href = link.get('href')
                if not href:
                    continue
                if href.startswith('/'):
                    href = urljoin(site_config['base_url'], href)
                if href in self._visited_urls:
                    continue
                self._visited_urls.add(href)
                # 도메인 필터
                if not self._is_allowed(href):
                    continue
                if href.lower().endswith('.pdf'):
                    pdf_path = self._download_pdf(href)
                    if pdf_path:
                        results.append({
                            'site': site_config['name'],
                            'title': link.get_text().strip() or 'PDF',
                            'content': '',
                            'links': [],
                            'url': href,
                            'downloaded_pdf': pdf_path,
                            'keywords_matched': []
                        })
                        followed += 1
                        if followed >= self.max_links_per_site:
                            break
                    continue
                # HTML 페이지 렌더링 수집
                page_html = self._fetch_html(href)
                if not page_html:
                    continue
                psoup = BeautifulSoup(page_html, 'html.parser')
                body_text = psoup.get_text(separator=' ', strip=True)
                title_elem = psoup.find(['h1', 'title'])
                ptitle = (title_elem.get_text().strip() if title_elem else (link.get_text().strip() or ''))
                if body_text:
                    results.append({
                        'site': site_config['name'],
                        'title': ptitle[:120],
                        'content': body_text[:1200],
                        'links': [],
                        'url': href,
                        'keywords_matched': [kw for kw in keywords if kw in body_text][:5]
                    })
                    followed += 1
                    if followed >= self.max_links_per_site:
                        break
            
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

def _env_flag(name: str, default: str = "0") -> bool:
    val = os.getenv(name, default)
    return str(val).lower() in ("1", "true", "on", "yes")

def auto_crawl_unhandled_symptoms():
    """미처리 증상에 대해 자동 크롤링을 실행합니다.
    환경변수 AUTO_REINDEX_ON_CRAWL 활성 시, 성공 건이 있으면 RAG 자동 재색인을 트리거합니다.
    """
    try:
        result = auto_crawler.process_unhandled_symptoms()
        print(f"자동 크롤링 완료: {result['successful']}개 성공, {result['failed']}개 실패")

        # 선택적 자동 재색인 (하이브리드 전략)
        try:
            if _env_flag("AUTO_REINDEX_ON_CRAWL", "0") and result.get('successful', 0) > 0:
                # 디바운스: 마지막 업데이트 이후 120초 이내면 스킵
                from .services_rag_updater import rag_updater
                meta = rag_updater.load_metadata()
                from datetime import datetime, timedelta
                last = meta.get('last_update')
                allow = True
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                        if datetime.now() - last_dt < timedelta(seconds=int(os.getenv('REINDEX_DEBOUNCE_SEC', '120'))):
                            allow = False
                    except Exception:
                        allow = True
                if allow:
                    print("AUTO_REINDEX_ON_CRAWL: 업데이트 실행")
                    rag_updater.update_rag_system()
                else:
                    print("AUTO_REINDEX_ON_CRAWL: 디바운스로 인해 건너뜀")
        except Exception as e:
            print(f"자동 재색인 트리거 오류: {e}")

        return result
    except Exception as e:
        print(f"자동 크롤링 오류: {str(e)}")
        return {'processed': 0, 'successful': 0, 'failed': 1, 'results': []}
