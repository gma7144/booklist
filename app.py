import streamlit as st
import pandas as pd
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# --- 웹앱 기본 설정 ---
st.set_page_config(page_title="Scholastic 도서 검색기", layout="centered") 
st.title("📚 자동 검색 웹앱")
st.markdown("등록번호 숫자를 입력하면 일치하는 정확한 도서를 찾아냅니다.")

# --- 1. CSV 파일 메모리에 자동 로드 ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("booklist.csv")
        return df
    except Exception as e:
        return None

df = load_data()

if df is None:
    st.error("⚠️ 'booklist.csv' 파일을 찾을 수 없습니다.")
else:
    st.success(f"✅ 데이터 로드 완료! (총 {len(df)}권 대기 중)")
    
    st.markdown("---")
    
    user_input = st.text_input("👇 등록번호 뒤 숫자만 입력하세요 (예: 330)", placeholder="숫자 입력 후 엔터를 치세요!")
    search_btn = st.button("🚀 검색 실행", use_container_width=True)

    if search_btn or user_input:
        if not user_input.strip() or not user_input.isdigit():
            st.warning("숫자만 정확히 입력해주세요!")
        else:
            target_num = int(user_input.strip())
            
            # [수정] '등록번호' 열의 이름으로 정확하게 접근하여 숫자만 추출합니다.
            if '등록번호' not in df.columns:
                st.error("원본 CSV 파일에 '등록번호' 열이 없습니다!")
            else:
                df['추출된숫자'] = df['등록번호'].astype(str).str.extract(r'(\d+)').fillna(-1).astype(int)
                matched_row = df[df['추출된숫자'] == target_num]
                
                if matched_row.empty:
                    st.error(f"❌ 등록번호 숫자 '{target_num}'에 해당하는 도서를 CSV에서 찾을 수 없습니다.")
                else:
                    # 도서명과 원본 CSV의 '정확한 전체 등록번호'를 가져옵니다.
                    target_title = matched_row.iloc[0]['도서명']
                    target_reg_num = str(matched_row.iloc[0]['등록번호']).strip()
                    target_lexile = matched_row.iloc[0]['Scholastic lexile'] if 'Scholastic lexile' in matched_row.columns else "-"
                    
                    st.info(f"💡 매칭 도서: **{target_title}** (원본 등록번호: {target_reg_num})")
                    
                    # --- 서버 스크래핑 시작 ---
                    with st.spinner("도서관 서버에서 데이터를 실시간으로 가져오는 중입니다..."):
                        try:
                            chrome_options = Options()
                            chrome_options.add_argument("--headless=new")
                            chrome_options.add_argument("--no-sandbox")
                            chrome_options.add_argument("--disable-dev-shm-usage")
                            chrome_options.add_argument("--disable-gpu")
                            chrome_options.add_argument('--log-level=3')
                            
                            # 리눅스 클라우드 서버 대응 (에러 127 방지)
                            chrome_options.binary_location = "/usr/bin/chromium"
                            service = Service("/usr/bin/chromedriver")
                            
                            try:
                                driver = webdriver.Chrome(service=service, options=chrome_options)
                            except:
                                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

                            driver.get("https://library.busan.go.kr/bengbooks/book/search/collectionOfMaterials#searchForm")
                            
                            time.sleep(1)
                            search_box = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='검색어']")
                            search_box.clear()
                            search_box.send_keys(target_title)
                            search_box.send_keys(Keys.ENTER)
                            
                            time.sleep(3) 
                            
                            js_extract = r"""
                            var bodyText = document.body.innerText.replace(/\s/g, ''); 
                            if (bodyText.includes('검색된도서가존재하지않') || bodyText.includes('총0건')) {
                                return {status: 'nodata'};
                            }
                            
                            var tables = document.querySelectorAll('table');
                            var items = [];
                            
                            for(var i=0; i<tables.length; i++) {
                                var table = tables[i];
                                var p = table.parentElement;
                                var blockText = "";
                                var callNumText = "-";
                                
                                for(var k=0; k<6; k++) {
                                    if(p && p.innerText) {
                                        blockText = p.innerText;
                                        break;
                                    }
                                    if(p) p = p.parentElement;
                                }
                                
                                var callMatch = blockText.match(/청구기호\s*:\s*([^\n]+)/);
                                if(callMatch) {
                                    callNumText = callMatch[1].trim();
                                }
                                
                                var trs = table.querySelectorAll('tbody tr');
                                for(var j=0; j<trs.length; j++) {
                                    var tds = trs[j].querySelectorAll('td');
                                    if(tds.length >= 3 && tds[0].innerText.includes("부산영어도서관")) {
                                        items.push({
                                            '소장위치': tds[0].innerText.trim(),
                                            '청구기호': callNumText,
                                            '등록번호': tds[1].innerText.trim(),
                                            '대출상태': tds[2].innerText.trim()
                                        });
                                    }
                                }
                            }
                            if (items.length === 0) return {status: 'nodata'};
                            return {status: 'success', items: items};
                            """
                            
                            data = driver.execute_script(js_extract)
                            driver.quit()
                            
                            if data['status'] == 'nodata':
                                st.warning("도서관에 해당 책이 검색되지 않거나, 영어도서관 소장 자료가 아닙니다.")
                            else:
                                # [핵심 로직] 스크래핑한 결과 중에서 '등록번호'가 정확히 일치하는 자료만 골라냅니다!
                                scraped_items = data['items']
                                
                                # 공백이나 대소문자 차이로 인한 오류를 막기 위해 특수기호를 제거하고 비교
                                clean_target_reg = re.sub(r'[^A-Za-z0-9]', '', target_reg_num).upper()
                                
                                filtered_items = []
                                for item in scraped_items:
                                    clean_scraped_reg = re.sub(r'[^A-Za-z0-9]', '', item['등록번호']).upper()
                                    if clean_target_reg == clean_scraped_reg:
                                        filtered_items.append(item)
                                
                                # 필터링 결과 출력
                                if not filtered_items:
                                    st.warning(f"⚠️ '{target_title}' 도서가 검색은 되었으나, 찾으시는 등록번호({target_reg_num})와 일치하는 자료가 없습니다. (동명이인 도서)")
                                else:
                                    st.success("🎉 검색 완료! 정확히 일치하는 도서를 찾았습니다.")
                                    result_df = pd.DataFrame(filtered_items)
                                    st.dataframe(result_df, use_container_width=True)
                                
                        except Exception as e:
                            st.error(f"서버 접속 중 에러가 발생했습니다: {e}")
                            if 'driver' in locals() and driver:
                                driver.quit()