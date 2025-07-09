#!/usr/bin/env python3.11
"""
1단계: Gemini API를 사용한 키워드 추출
고등학생 탐구주제에서 도서 검색용 키워드 5-7개 추출
"""

import pandas as pd
import json
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
import time

# 환경 변수 로드 (상대 경로 지정)
load_dotenv('../설정파일/.env')

def extract_keywords_with_gemini(topic: str, model) -> tuple:
    """Gemini를 사용하여 키워드 추출"""
    prompt = f"""
고등학생 탐구주제: "{topic}"

이 탐구주제를 분석하여 다음 정보를 JSON 형식으로 제공해주세요:

{{
    "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5", "키워드6", "키워드7"],
    "academic_field": "주요 학문분야",
    "difficulty_level": "고등학생 수준에서의 난이도 (상/중/하)",
    "additional_keywords": ["추가검색용 키워드1", "추가검색용 키워드2"],
    "book_types": ["관련 도서 유형1", "관련 도서 유형2"],
    "cautions": "도서 선정 시 주의사항"
}}

주요 요구사항:
1. keywords: 도서 검색에 효과적인 5-7개 키워드 (한국어, 구체적이고 검색 가능한 용어)
2. academic_field: 물리학, 화학, 생물학, 수학, 사회과학, 인문학 등
3. difficulty_level: 고등학생이 이해할 수 있는 수준인지 평가
4. additional_keywords: 보완적 검색용 키워드 1-2개
5. book_types: 이론서, 실험서, 교양서, 입문서 등 적절한 도서 유형
6. cautions: 너무 어렵거나 부적절한 도서를 피하기 위한 주의사항

반드시 JSON 형식으로만 응답해주세요.
"""
    
    try:
        print(f"Gemini API로 키워드 추출 중: {topic[:50]}...")
        response = model.generate_content(prompt)
        
        # JSON 파싱
        json_text = response.text.strip()
        if json_text.startswith('```json'):
            json_text = json_text[7:-3].strip()
        elif json_text.startswith('```'):
            json_text = json_text[3:-3].strip()
            
        result = json.loads(json_text)
        
        keywords = result.get('keywords', [])
        print(f"  추출된 키워드: {keywords}")
        print(f"  학문분야: {result.get('academic_field', '미분류')}")
        
        return keywords, result
        
    except Exception as e:
        print(f"Gemini API 오류: {e}")
        print(f"  키워드 추출 실패")
        return [], {
            'keywords': [],
            'academic_field': '미분류',
            'difficulty_level': '중',
            'additional_keywords': [],
            'book_types': [],
            'cautions': 'API 오류로 인한 처리 실패'
        }

def process_excel_file(input_file: str) -> None:
    """Excel 파일의 모든 탐구주제에서 키워드 추출"""
    print(f"Excel 파일 로드 중: {input_file}")
    
    # Excel 파일 읽기
    df = pd.read_excel(input_file)
    
    if 'task' not in df.columns:
        raise ValueError("Excel 파일에 'task' 컬럼이 없습니다.")
    
    topics = df['task'].dropna().tolist()
    total_count = len(topics)
    
    print(f"총 {total_count}개 탐구주제에서 키워드 추출 시작")
    print("=" * 80)
    
    # Gemini API 설정
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_API_KEY가 .env 파일에 설정되지 않았습니다.")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')  # 빠른 모델 사용
    print("Gemini 1.5 Flash 모델 로드 완료 (빠른 키워드 추출용)")
    
    keywords_list = []
    academic_fields = []
    results = []
    
    for i, topic in enumerate(topics, 1):
        print(f"\n[{i}/{total_count}] 처리 중: {topic}")
        
        keywords, topic_info = extract_keywords_with_gemini(topic, model)
        
        # 데이터 수집
        keywords_list.append(', '.join(keywords))
        academic_fields.append(topic_info.get('academic_field', '미분류'))
        
        results.append({
            'topic': topic,
            'keywords': keywords,
            'topic_analysis': topic_info
        })
        
        # 진행률 표시
        progress = (i / total_count) * 100
        print(f"  진행률: {progress:.1f}%")
        
        # API 호출 간격 (과부하 방지)
        time.sleep(0.3)  # Flash 모델이므로 더 짧은 간격
    
    # Excel 파일에 keywords 컬럼 추가
    df['keywords'] = keywords_list
    df['academic_field'] = academic_fields
    
    # 결과 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON 결과 저장
    json_filename = f'../결과파일/keywords_extraction_{timestamp}.json'
    final_results = {
        'total_topics': total_count,
        'extraction_results': results,
        'statistics': {
            'academic_fields': pd.Series(academic_fields).value_counts().to_dict(),
            'average_keywords_per_topic': sum(len(r['keywords']) for r in results) / len(results)
        }
    }
    
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    
    # Excel 결과 저장
    excel_filename = f'../결과파일/step1_keywords_only_{timestamp}.xlsx'
    df.to_excel(excel_filename, index=False)
    
    # 결과 출력
    print("\n" + "=" * 80)
    print("키워드 추출 완료!")
    print("=" * 80)
    print(f"처리된 탐구주제: {total_count}개")
    print(f"평균 키워드 수: {final_results['statistics']['average_keywords_per_topic']:.1f}개/주제")
    
    print(f"\n학문분야별 분포:")
    for field, count in final_results['statistics']['academic_fields'].items():
        print(f"  - {field}: {count}개")
    
    print(f"\n결과 파일:")
    print(f"  - JSON: {json_filename}")
    print(f"  - Excel: {excel_filename}")
    
    # 샘플 결과 출력
    if results:
        sample = results[0]
        print(f"\n샘플 결과 ('{sample['topic'][:30]}...'):")
        print(f"  키워드: {', '.join(sample['keywords'])}")
        print(f"  학문분야: {sample['topic_analysis'].get('academic_field', '미분류')}")
        print(f"  난이도: {sample['topic_analysis'].get('difficulty_level', '중')}")

def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("1단계: Gemini API를 사용한 키워드 추출")
    print("- Python 3.11 + google-generativeai 0.8.5")
    print("- Gemini 1.5 Flash 모델 사용 (빠른 처리)")
    print("=" * 80)
    
    try:
        input_file = '../원천파일/주제테스트_50.xlsx'
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"{input_file} 파일을 찾을 수 없습니다.")
        
        process_excel_file(input_file)
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 