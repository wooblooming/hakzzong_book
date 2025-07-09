#!/usr/bin/env python3.11
"""
API 비용 추적 기능 테스트 스크립트
- 3개 샘플 주제로 빠른 테스트
- API 비용 추적 기능 확인
"""

import json
from datetime import datetime
from step3_integrated_system import BookRecommendationSystem

def test_api_cost_tracking():
    """API 비용 추적 기능 테스트"""
    print("=" * 80)
    print("🧪 API 비용 추적 기능 테스트")
    print("=" * 80)
    
    # 테스트용 샘플 주제들 (3개만)
    test_topics = [
        "스마트폰 사용이 청소년의 수면 패턴에 미치는 영향",
        "재생 에너지를 이용한 친환경 발전 시스템 설계",
        "인공지능과 머신러닝의 교육 분야 활용 방안"
    ]
    
    try:
        # 시스템 초기화
        system = BookRecommendationSystem()
        system.total_count = len(test_topics)
        
        print(f"테스트 주제 {len(test_topics)}개로 API 비용 추적 테스트")
        print("-" * 50)
        
        results = []
        
        for i, topic in enumerate(test_topics, 1):
            print(f"\n[{i}/{len(test_topics)}] 테스트 중: {topic[:50]}...")
            
            # 개별 주제 처리 전 비용 확인
            cost_before = system.api_tracker.total_cost
            
            result = system.process_single_topic(topic)
            results.append(result)
            
            # 처리 후 비용 확인
            cost_after = system.api_tracker.total_cost
            topic_cost = cost_after - cost_before
            
            print(f"  이 주제 처리 비용: ${topic_cost:.4f} USD (₩{topic_cost * 1300:.0f})")
        
        # 결과 분석
        print("\n" + "=" * 80)
        print("📊 API 비용 추적 테스트 결과")
        print("=" * 80)
        
        total_calls = len(system.api_tracker.usage_log)
        total_cost = system.api_tracker.total_cost
        avg_cost_per_topic = total_cost / len(test_topics)
        
        print(f"총 API 호출 수: {total_calls}회")
        print(f"총 예상 비용: ${total_cost:.4f} USD (₩{total_cost * 1300:.0f})")
        print(f"주제당 평균 비용: ${avg_cost_per_topic:.4f} USD (₩{avg_cost_per_topic * 1300:.0f})")
        
        # 호출 유형별 분석
        keyword_calls = sum(1 for log in system.api_tracker.usage_log if log['call_type'] == 'keyword_extraction')
        verification_calls = sum(1 for log in system.api_tracker.usage_log if log['call_type'] == 'book_verification')
        
        print(f"\n📋 호출 유형별 통계:")
        print(f"  키워드 추출 호출: {keyword_calls}회")
        print(f"  도서 검증 호출: {verification_calls}회")
        
        # 50개 주제 처리시 예상 비용
        estimated_50_cost = avg_cost_per_topic * 50
        print(f"\n📈 50개 주제 처리시 예상 비용:")
        print(f"  예상 API 비용: ${estimated_50_cost:.4f} USD (₩{estimated_50_cost * 1300:.0f})")
        print(f"  예상 API 호출 수: {total_calls / len(test_topics) * 50:.0f}회")
        
        # API 사용량 리포트 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        api_report_filename = system.api_tracker.save_usage_report(
            f'../결과파일/api_cost_test_report_{timestamp}.txt'
        )
        
        # 테스트 결과 저장
        test_result = {
            'test_info': {
                'test_topics_count': len(test_topics),
                'total_api_calls': total_calls,
                'total_cost_usd': round(total_cost, 4),
                'average_cost_per_topic': round(avg_cost_per_topic, 4),
                'keyword_extraction_calls': keyword_calls,
                'book_verification_calls': verification_calls
            },
            'topic_results': [
                {
                    'topic': r['topic'],
                    'keywords': r['keywords'],
                    'books_found': r['total_books_found'],
                    'books_recommended': len(r['recommended_books'])
                }
                for r in results
            ]
        }
        
        test_filename = f'../결과파일/api_cost_test_result_{timestamp}.json'
        with open(test_filename, 'w', encoding='utf-8') as f:
            json.dump(test_result, f, ensure_ascii=False, indent=2)
        
        print(f"\n📁 생성된 파일:")
        print(f"  - API 사용량 리포트: {api_report_filename}")
        print(f"  - 테스트 결과: {test_filename}")
        
        print(f"\n✅ API 비용 추적 기능이 정상적으로 작동합니다!")
        
    except Exception as e:
        print(f"❌ 테스트 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_cost_tracking() 