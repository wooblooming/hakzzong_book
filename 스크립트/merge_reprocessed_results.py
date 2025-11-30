#!/usr/bin/env python3.11
"""
재처리 결과 병합 스크립트
- 원본 전체 데이터 (21,281개)와 재처리된 실패 항목들 (5,038개)을 병합
- ID/주제 기준으로 매칭하여 재처리 결과로 업데이트
- 원본 데이터의 구조와 형식은 그대로 유지
"""

import pandas as pd
import json
from datetime import datetime
import os

def load_original_complete_data():
    """원본 전체 데이터 로드 (21,281개)"""
    print("원본 전체 데이터 로딩 중...")
    
    # JSON 파일 로드
    json_file = '../결과파일/book_recommendations_주제_테스트_250205_COMPLETE_20250716_041727.json'
    excel_file = '../결과파일/final_book_recommendations_주제_테스트_250205_TOPIC_BASED_20250716_060102.xlsx'
    
    # JSON 데이터 로드
    if os.path.exists(json_file):
        print(f"JSON 파일 로딩: {json_file}")
        with open(json_file, 'r', encoding='utf-8') as f:
            json_raw = json.load(f)
        
        # JSON 구조 확인 및 데이터 추출
        if isinstance(json_raw, dict) and 'results' in json_raw:
            json_data = json_raw['results']
            print(f"JSON 데이터 로드 완료: {len(json_data)}개 항목 (총 {json_raw.get('total_topics', 'Unknown')}개)")
        elif isinstance(json_raw, list):
            json_data = json_raw
            print(f"JSON 데이터 로드 완료: {len(json_data)}개 항목")
        else:
            raise ValueError("JSON 파일 구조를 인식할 수 없습니다.")
    else:
        raise FileNotFoundError(f"원본 JSON 파일을 찾을 수 없습니다: {json_file}")
    
    # Excel 데이터 로드
    if os.path.exists(excel_file):
        print(f"Excel 파일 로딩: {excel_file}")
        df_excel = pd.read_excel(excel_file, engine='openpyxl')
        print(f"Excel 데이터 로드 완료: {len(df_excel)}개 항목")
        print(f"Excel 컬럼: {list(df_excel.columns)}")
    else:
        raise FileNotFoundError(f"원본 Excel 파일을 찾을 수 없습니다: {excel_file}")
    
    return json_data, df_excel

def load_reprocessed_data():
    """재처리된 데이터 로드 (5,038개)"""
    print("재처리 데이터 로딩 중...")
    
    # JSON 파일 로드
    json_file = '../결과파일/book_recommendations_failed_topics_for_reprocessing_20250716_091106_20250716_124522.json'
    excel_file = '../결과파일/final_book_recommendations_failed_topics_FIXED_IDS_20250716_152154.xlsx'
    
    # JSON 데이터 로드
    if os.path.exists(json_file):
        print(f"재처리 JSON 파일 로딩: {json_file}")
        with open(json_file, 'r', encoding='utf-8') as f:
            json_raw = json.load(f)
        
        # JSON 구조 확인 및 데이터 추출
        if isinstance(json_raw, dict) and 'results' in json_raw:
            json_data = json_raw['results']
            print(f"재처리 JSON 데이터 로드 완료: {len(json_data)}개 항목 (총 {json_raw.get('total_topics', 'Unknown')}개)")
        elif isinstance(json_raw, list):
            json_data = json_raw
            print(f"재처리 JSON 데이터 로드 완료: {len(json_data)}개 항목")
        else:
            raise ValueError("재처리 JSON 파일 구조를 인식할 수 없습니다.")
    else:
        raise FileNotFoundError(f"재처리 JSON 파일을 찾을 수 없습니다: {json_file}")
    
    # Excel 데이터 로드
    if os.path.exists(excel_file):
        print(f"재처리 Excel 파일 로딩: {excel_file}")
        df_excel = pd.read_excel(excel_file, engine='openpyxl')
        print(f"재처리 Excel 데이터 로드 완료: {len(df_excel)}개 항목")
        print(f"재처리 Excel 컬럼: {list(df_excel.columns)}")
    else:
        raise FileNotFoundError(f"재처리 Excel 파일을 찾을 수 없습니다: {excel_file}")
    
    return json_data, df_excel

def merge_json_data(original_json, reprocessed_json):
    """JSON 데이터 병합"""
    print("JSON 데이터 병합 시작...")
    
    # 원본 데이터 복사
    merged_json = original_json.copy()
    
    # 재처리 데이터를 ID 기준으로 딕셔너리 생성
    reprocessed_dict = {}
    for item in reprocessed_json:
        if 'id' in item:
            reprocessed_dict[item['id']] = item
        elif 'topic_id' in item:
            reprocessed_dict[item['topic_id']] = item
    
    print(f"재처리 딕셔너리 생성 완료: {len(reprocessed_dict)}개 항목")
    
    # 병합 처리
    updated_count = 0
    
    for i, item in enumerate(merged_json):
        item_id = None
        if 'id' in item:
            item_id = item['id']
        elif 'topic_id' in item:
            item_id = item['topic_id']
        
        if item_id and item_id in reprocessed_dict:
            # 재처리 결과를 무조건 반영 (성공/실패 관계없이)
            reprocessed_item = reprocessed_dict[item_id]
            merged_json[i] = reprocessed_item
            updated_count += 1
    
    print(f"JSON 병합 완료:")
    print(f"- 업데이트된 항목: {updated_count}")
    
    return merged_json

def merge_excel_data(original_df, reprocessed_df):
    """Excel 데이터 병합"""
    print("Excel 데이터 병합 시작...")
    
    # 원본 데이터 복사
    merged_df = original_df.copy()
    
    # ID 컬럼 찾기
    original_id_col = None
    for col in merged_df.columns:
        if 'id' in col.lower() or col == 'Column1':
            original_id_col = col
            break
    
    reprocessed_id_col = None
    for col in reprocessed_df.columns:
        if 'id' in col.lower() or col == 'Column1':
            reprocessed_id_col = col
            break
    
    if not original_id_col:
        original_id_col = merged_df.columns[0]
    if not reprocessed_id_col:
        reprocessed_id_col = reprocessed_df.columns[0]
    
    print(f"원본 ID 컬럼: {original_id_col}")
    print(f"재처리 ID 컬럼: {reprocessed_id_col}")
    
    # 병합 처리
    updated_count = 0
    
    for idx, reprocessed_row in reprocessed_df.iterrows():
        reprocessed_id = reprocessed_row[reprocessed_id_col]
        
        # 원본에서 해당 ID 찾기
        original_mask = merged_df[original_id_col] == reprocessed_id
        matching_indices = merged_df[original_mask].index
        
        if len(matching_indices) > 0:
            original_idx = matching_indices[0]
            
            # 재처리 결과를 무조건 반영 (성공/실패 관계없이)
            for col in reprocessed_df.columns:
                if col in merged_df.columns:
                    value = reprocessed_row[col]
                    # pandas 경고 방지를 위한 타입 변환
                    if pd.isna(value):
                        merged_df.loc[original_idx, col] = None
                    else:
                        merged_df.loc[original_idx, col] = value
            
            updated_count += 1
    
    print(f"Excel 병합 완료:")
    print(f"- 업데이트된 항목: {updated_count}")
    
    return merged_df

def analyze_final_results(merged_json, merged_df):
    """최종 결과 분석"""
    print("\n=== 최종 병합 결과 분석 ===")
    
    # JSON 분석
    print("JSON 데이터 분석:")
    total_json = len(merged_json)
    json_with_books = 0
    json_with_two_books = 0
    json_with_one_book = 0
    
    for item in merged_json:
        recommended_books = item.get('recommended_books', [])
        valid_books = []
        
        if isinstance(recommended_books, list):
            for book in recommended_books:
                if isinstance(book, dict) and book.get('title') and book.get('title').strip():
                    valid_books.append(book)
        
        book_count = len(valid_books)
        if book_count >= 1:
            json_with_books += 1
            if book_count >= 2:
                json_with_two_books += 1
            else:
                json_with_one_book += 1
    
    print(f"  총 항목: {total_json:,}")
    print(f"  2권 추천: {json_with_two_books:,} ({json_with_two_books/total_json*100:.1f}%)")
    print(f"  1권 추천: {json_with_one_book:,} ({json_with_one_book/total_json*100:.1f}%)")
    print(f"  추천 없음: {total_json-json_with_books:,} ({(total_json-json_with_books)/total_json*100:.1f}%)")
    print(f"  총 성공률: {json_with_books/total_json*100:.1f}%")
    
    # Excel 분석
    print("\nExcel 데이터 분석:")
    
    # 추천도서 컬럼 찾기
    book_columns = []
    for col in merged_df.columns:
        if '추천도서' in col or 'book' in col.lower():
            book_columns.append(col)
    
    if book_columns:
        book1_col = book_columns[0]
        book2_col = book_columns[1] if len(book_columns) > 1 else None
        
        total_excel = len(merged_df)
        has_book1 = merged_df[book1_col].notna() & (merged_df[book1_col].astype(str).str.strip() != '') & (merged_df[book1_col].astype(str) != 'nan')
        excel_with_books = has_book1.sum()
        
        if book2_col:
            has_book2 = merged_df[book2_col].notna() & (merged_df[book2_col].astype(str).str.strip() != '') & (merged_df[book2_col].astype(str) != 'nan')
            excel_with_both = (has_book1 & has_book2).sum()
            excel_with_one = (has_book1 & ~has_book2).sum()
            
            print(f"  총 항목: {total_excel:,}")
            print(f"  2권 추천: {excel_with_both:,} ({excel_with_both/total_excel*100:.1f}%)")
            print(f"  1권 추천: {excel_with_one:,} ({excel_with_one/total_excel*100:.1f}%)")
            print(f"  추천 없음: {total_excel-excel_with_books:,} ({(total_excel-excel_with_books)/total_excel*100:.1f}%)")
            print(f"  총 성공률: {excel_with_books/total_excel*100:.1f}%")

def save_merged_results(merged_json, merged_df):
    """병합 결과 저장"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON 저장
    json_output = f'../결과파일/FINAL_MERGED_COMPLETE_{timestamp}.json'
    print(f"최종 JSON 저장 중: {json_output}")
    
    with open(json_output, 'w', encoding='utf-8') as f:
        json.dump(merged_json, f, ensure_ascii=False, indent=2)
    
    # Excel 저장
    excel_output = f'../결과파일/FINAL_MERGED_COMPLETE_{timestamp}.xlsx'
    print(f"최종 Excel 저장 중: {excel_output}")
    
    with pd.ExcelWriter(excel_output, engine='openpyxl') as writer:
        merged_df.to_excel(writer, sheet_name='최종통합결과', index=False)
    
    print(f"저장 완료:")
    print(f"  JSON: {json_output}")
    print(f"  Excel: {excel_output}")
    
    return json_output, excel_output

def main():
    """메인 실행 함수"""
    try:
        print("=== 재처리 결과 병합 프로세스 시작 ===")
        
        # 1. 원본 전체 데이터 로드
        original_json, original_df = load_original_complete_data()
        
        # 2. 재처리 데이터 로드
        reprocessed_json, reprocessed_df = load_reprocessed_data()
        
        # 3. 데이터 병합
        print("\n=== 데이터 병합 시작 ===")
        merged_json = merge_json_data(original_json, reprocessed_json)
        merged_df = merge_excel_data(original_df, reprocessed_df)
        
        # 4. 결과 분석
        analyze_final_results(merged_json, merged_df)
        
        # 5. 결과 저장
        json_file, excel_file = save_merged_results(merged_json, merged_df)
        
        print(f"\n=== 병합 완료 ===")
        print(f"최종 파일:")
        print(f"  JSON: {json_file}")
        print(f"  Excel: {excel_file}")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 