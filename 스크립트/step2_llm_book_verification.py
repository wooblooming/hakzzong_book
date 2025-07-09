#!/usr/bin/env python3.11
"""
2단계: LLM 기반 도서 검증 및 상세 추천 시스템
- Gemini를 사용한 도서 적합성 검증
- 250-300자 상세 추천 이유 생성
"""

import pandas as pd
import json
import re
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
import time
import requests
from typing import Dict, List, Tuple

# 환경 변수 로드 (상대 경로 지정)
load_dotenv('../설정파일/.env')

class LLMBookVerificationSystem:
    def __init__(self):
        """시스템 초기화"""
        # API 키 설정
        self.gemini_api_key = os.getenv('GOOGLE_API_KEY')
        self.naver_client_id = os.getenv('NAVER_CLIENT_ID')
        self.naver_client_secret = os.getenv('NAVER_CLIENT_SECRET')
        
        if not self.gemini_api_key:
            print("경고: GOOGLE_API_KEY가 .env 파일에 설정되지 않았습니다.")
            self.model = None
        else:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-1.5-pro')  # 빠르면서도 정확한 모델
            print("Gemini 1.5 Pro 모델 로드 완료 (도서 검증용)")
        
        if not self.naver_client_id or not self.naver_client_secret:
            raise ValueError("네이버 API 키가 .env 파일에 설정되지 않았습니다.")
    
    def extract_topic_info_with_llm(self, topic: str) -> Dict:
        """LLM을 사용하여 탐구주제 상세 분석"""
        if not self.model:
            raise ValueError("Gemini 모델이 초기화되지 않았습니다.")
        
        prompt = f"""
고등학생 탐구주제: "{topic}"

이 탐구주제를 분석하여 다음 정보를 JSON 형식으로 제공해주세요:

{{
    "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
    "academic_field": "주요 학문분야",
    "difficulty_level": "고등학생 수준에서의 난이도 (상/중/하)",
    "additional_keywords": ["추가검색용 키워드1", "추가검색용 키워드2"],
    "book_types": ["관련 도서 유형1", "관련 도서 유형2"],
    "cautions": "도서 선정 시 주의사항",
    "specific_topics": ["구체적 세부주제1", "구체적 세부주제2"],
    "recommended_approach": "탐구 접근 방법 제안"
}}

요구사항:
1. keywords: 도서 검색용 핵심 키워드 5개
2. academic_field: 물리학, 화학, 생물학, 수학, 사회과학, 인문학 등
3. difficulty_level: 고등학생 수준 적합도
4. additional_keywords: 보완 검색용 키워드
5. book_types: 이론서, 실험서, 교양서, 입문서 등
6. cautions: 부적절한 도서 회피 방안
7. specific_topics: 세부 탐구 영역
8. recommended_approach: 효과적 탐구 방법

반드시 JSON 형식으로만 응답해주세요.
"""
        
        try:
            print(f"  LLM으로 주제 분석 중...")
            response = self.model.generate_content(prompt)
            
            json_text = response.text.strip()
            if json_text.startswith('```json'):
                json_text = json_text[7:-3].strip()
            elif json_text.startswith('```'):
                json_text = json_text[3:-3].strip()
            
            result = json.loads(json_text)
            return result
            
        except Exception as e:
            print(f"  LLM 분석 오류: {e}")
            return {
                'keywords': [],
                'academic_field': '미분류',
                'difficulty_level': '중',
                'additional_keywords': [],
                'book_types': [],
                'cautions': 'LLM 분석 실패',
                'specific_topics': [],
                'recommended_approach': '기본 탐구 접근법'
            }
    
    def search_books_naver(self, keywords: List[str], max_per_keyword: int = 10) -> List[Dict]:
        """네이버 도서 API로 도서 검색"""
        all_books = []
        
        for keyword in keywords[:3]:  # 상위 3개 키워드만 사용
            try:
                print(f"    네이버 API 검색: {keyword}")
                
                headers = {
                    'X-Naver-Client-Id': self.naver_client_id,
                    'X-Naver-Client-Secret': self.naver_client_secret,
                }
                
                params = {
                    'query': keyword,
                    'display': max_per_keyword,
                    'sort': 'sim'  # 정확도순
                }
                
                response = requests.get(
                    'https://openapi.naver.com/v1/search/book.json',
                    headers=headers,
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    books = data.get('items', [])
                    
                    for book in books:
                        if book.get('isbn'):
                            all_books.append({
                                'title': re.sub(r'<[^>]+>', '', book.get('title', '')),
                                'author': re.sub(r'<[^>]+>', '', book.get('author', '')),
                                'publisher': book.get('publisher', ''),
                                'pubdate': book.get('pubdate', ''),
                                'isbn': book.get('isbn', '').split()[-1],  # 13자리 ISBN 사용
                                'description': re.sub(r'<[^>]+>', '', book.get('description', '')),
                                'search_keyword': keyword
                            })
                
                time.sleep(0.1)  # API 호출 간격
                
            except Exception as e:
                print(f"    네이버 API 오류 ({keyword}): {e}")
                continue
        
        # ISBN 기준 중복 제거
        unique_books = {}
        for book in all_books:
            isbn = book['isbn']
            if isbn and isbn not in unique_books:
                unique_books[isbn] = book
        
        return list(unique_books.values())
    
    def verify_books_with_llm(self, books: List[Dict], topic: str, topic_info: Dict) -> List[Dict]:
        """LLM을 사용하여 도서 적합성 검증 및 상세 추천 이유 생성"""
        if not books:
            return []
        
        if not self.model:
            return self._get_mock_verification(books, topic)
        
        # 상위 10권만 검증 (API 비용 절약)
        books_to_verify = books[:10]
        
        book_list = []
        for i, book in enumerate(books_to_verify, 1):
            book_info = f"{i}. 제목: {book['title']}\n"
            book_info += f"   저자: {book['author']}\n"
            book_info += f"   출판사: {book['publisher']}\n"
            book_info += f"   출간년도: {book['pubdate']}\n"
            book_info += f"   설명: {book['description'][:200]}...\n"
            book_list.append(book_info)
        
        prompt = f"""
고등학생 탐구주제: "{topic}"

주제 분석 정보:
- 학문분야: {topic_info.get('academic_field', '미분류')}
- 난이도: {topic_info.get('difficulty_level', '중')}
- 세부주제: {', '.join(topic_info.get('specific_topics', []))}
- 탐구접근법: {topic_info.get('recommended_approach', '기본 접근법')}

검증할 도서 목록:
{chr(10).join(book_list)}

각 도서에 대해 다음 기준으로 점수를 매기고 상세한 추천 이유를 제공해주세요:

{{
    "book_scores": [
        {{
            "book_number": 1,
            "relevance_score": 30,
            "appropriateness_score": 25,
            "reliability_score": 20,
            "recency_score": 15,
            "accessibility_score": 10,
            "total_score": 100,
            "detailed_recommendation": "250-300자의 매우 상세한 추천 이유",
            "strengths": ["장점1", "장점2", "장점3"],
            "potential_concerns": ["우려사항1", "우려사항2"],
            "usage_tips": "이 책을 활용한 탐구 방법"
        }},
        // ... 다른 도서들
    ]
}}

점수 기준:
1. relevance_score (0-30점): 탐구주제와의 직접적 관련성
2. appropriateness_score (0-25점): 고등학생 수준 적합성
3. reliability_score (0-20점): 저자/출판사 권위성, 내용 정확성
4. recency_score (0-15점): 최신성 (2020년 이후 만점)
5. accessibility_score (0-10점): 구매/대출 용이성, 읽기 난이도

detailed_recommendation 작성 기준:
- 반드시 250-300자로 작성
- 탐구주제와의 구체적 연관성 설명
- 고등학생에게 적합한 구체적 이유
- 이 책을 통해 얻을 수 있는 구체적 지식/인사이트
- 실제 탐구 활동에 활용할 수 있는 방법

반드시 JSON 형식으로만 응답해주세요.
"""
        
        try:
            print(f"  LLM으로 도서 검증 중...")
            response = self.model.generate_content(prompt)
            
            json_text = response.text.strip()
            if json_text.startswith('```json'):
                json_text = json_text[7:-3].strip()
            elif json_text.startswith('```'):
                json_text = json_text[3:-3].strip()
            
            result = json.loads(json_text)
            book_scores = result.get('book_scores', [])
            
            # 점수를 원본 도서 정보에 추가
            verified_books = []
            for score_info in book_scores:
                book_num = score_info.get('book_number', 1) - 1
                if 0 <= book_num < len(books_to_verify):
                    book = books_to_verify[book_num].copy()
                    book.update({
                        'llm_total_score': score_info.get('total_score', 0),
                        'llm_relevance': score_info.get('relevance_score', 0),
                        'llm_appropriateness': score_info.get('appropriateness_score', 0),
                        'llm_reliability': score_info.get('reliability_score', 0),
                        'llm_recency': score_info.get('recency_score', 0),
                        'llm_accessibility': score_info.get('accessibility_score', 0),
                        'detailed_recommendation': score_info.get('detailed_recommendation', ''),
                        'strengths': score_info.get('strengths', []),
                        'potential_concerns': score_info.get('potential_concerns', []),
                        'usage_tips': score_info.get('usage_tips', '')
                    })
                    verified_books.append(book)
            
            return sorted(verified_books, key=lambda x: x.get('llm_total_score', 0), reverse=True)
            
        except Exception as e:
            print(f"  LLM 검증 오류: {e}")
            return []
    

    
    def process_single_topic(self, topic: str) -> Dict:
        """단일 탐구주제 처리"""
        print(f"\n처리 중: {topic}")
        
        try:
            # 1단계: LLM으로 주제 상세 분석
            topic_info = self.extract_topic_info_with_llm(topic)
            print(f"  학문분야: {topic_info.get('academic_field', '미분류')}")
            print(f"  키워드: {topic_info.get('keywords', [])}")
            
            # 2단계: 네이버 API로 도서 검색
            books = self.search_books_naver(topic_info.get('keywords', []))
            print(f"  검색된 도서: {len(books)}권")
            
            # 3단계: LLM으로 도서 검증 및 상세 추천 이유 생성
            verified_books = self.verify_books_with_llm(books, topic, topic_info)
            
            # 상위 2권 선정
            top_books = verified_books[:2]
            
            result = {
                'topic': topic,
                'topic_analysis': topic_info,
                'total_books_found': len(books),
                'verified_books_count': len(verified_books),
                'recommended_books': []
            }
            
            for i, book in enumerate(top_books, 1):
                result['recommended_books'].append({
                    'rank': i,
                    'title': book['title'],
                    'author': book['author'],
                    'publisher': book['publisher'],
                    'publication_date': book['pubdate'],
                    'isbn': book['isbn'],
                    'description': book['description'][:200] + '...' if len(book['description']) > 200 else book['description'],
                    'total_score': book.get('llm_total_score', 0),
                    'score_breakdown': {
                        'relevance': book.get('llm_relevance', 0),
                        'appropriateness': book.get('llm_appropriateness', 0),
                        'reliability': book.get('llm_reliability', 0),
                        'recency': book.get('llm_recency', 0),
                        'accessibility': book.get('llm_accessibility', 0)
                    },
                    'detailed_recommendation': book.get('detailed_recommendation', ''),
                    'strengths': book.get('strengths', []),
                    'potential_concerns': book.get('potential_concerns', []),
                    'usage_tips': book.get('usage_tips', ''),
                    'search_keyword': book.get('search_keyword', '')
                })
            
            print(f"  최종 추천: {len(top_books)}권")
            
            # 상위 도서 정보 출력
            for i, book in enumerate(top_books, 1):
                print(f"    {i}위: {book['title']} (점수: {book.get('llm_total_score', 0)})")
                print(f"         ISBN: {book['isbn']}")
            
            return result
            
        except Exception as e:
            print(f"  처리 오류: {e}")
            return {
                'topic': topic,
                'topic_analysis': {'error': str(e)},
                'total_books_found': 0,
                'verified_books_count': 0,
                'recommended_books': []
            }

def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("2단계: LLM 기반 도서 검증 시스템")
    print("- Python 3.11 + google-generativeai 0.8.5")
    print("- Gemini 1.5 Pro 모델 사용 (검증 품질과 속도 균형)")
    print("- 상세 추천 이유 생성")
    print("=" * 80)
    
    try:
        # 시스템 초기화
        system = LLMBookVerificationSystem()
        
        # 테스트용 샘플 탐구주제들
        sample_topics = [
            "스마트폰 사용이 청소년의 수면 패턴에 미치는 영향",
            "재생 에너지를 이용한 친환경 발전 시스템 설계",
            "인공지능과 머신러닝의 교육 분야 활용 방안"
        ]
        
        results = []
        
        print(f"샘플 {len(sample_topics)}개 주제로 테스트 시작")
        print("=" * 80)
        
        for i, topic in enumerate(sample_topics, 1):
            print(f"\n[{i}/{len(sample_topics)}] 테스트 중...")
            result = system.process_single_topic(topic)
            results.append(result)
            
            # API 호출 간격
            time.sleep(1)
        
        # 결과 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = f'../결과파일/llm_book_verification_{timestamp}.json'
        
        final_results = {
            'test_topics': len(sample_topics),
            'results': results,
            'statistics': {
                'average_books_found': sum(r['total_books_found'] for r in results) / len(results) if results else 0,
                'average_verified_books': sum(r['verified_books_count'] for r in results) / len(results) if results else 0
            }
        }
        
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=2)
        
        # 결과 출력
        print("\n" + "=" * 80)
        print("LLM 도서 검증 테스트 완료!")
        print("=" * 80)
        print(f"처리된 주제: {len(sample_topics)}개")
        print(f"평균 발견 도서: {final_results['statistics']['average_books_found']:.1f}권/주제")
        print(f"평균 검증 도서: {final_results['statistics']['average_verified_books']:.1f}권/주제")
        print(f"결과 파일: {json_filename}")
        
        # 샘플 결과 출력
        if results:
            sample = results[0]
            print(f"\n샘플 결과:")
            print(f"주제: {sample['topic']}")
            
            if sample['recommended_books']:
                book = sample['recommended_books'][0]
                print(f"1위 추천도서: {book['title']}")
                print(f"ISBN: {book['isbn']}")
                print(f"총점: {book['total_score']}점")
                print(f"상세 추천이유: {book['detailed_recommendation'][:100]}...")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 