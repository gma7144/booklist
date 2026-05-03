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
st.markdown("등록번호 숫자를 입력하면 자동으로 도서를 검색합니다.")

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
            
            df['추출된숫자'] = df.iloc[:, 4].astype(str).str.extract(r'(\d+)').fillna(-1).astype(int)
            matched_row = df[df['추출된숫자'] == target_num]
            
            if matched_row.empty:
                st.error(f"❌ 등록번호 숫자 '{target_num}'에 해당하는 도서를 찾을 수 없습니다.")
            else:
                target_title = matched_row.iloc[0, 0]
                target_lexile = matched_row.iloc[0, 1] if len(matched_row.columns) > 1 else "-"
                
                st.info(f"💡 매칭 도서: **{target_title}** (Lexile: {target_lexile})")
                
                # --- 서버 스크래핑 시작 ---
                with st.spinner("도서관 서버에서 데이터를 실시간으로 가져오는 중입니다..."):
                    try:
                        chrome_options = Options()
                        chrome_options.add_argument("--headless=new")
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument('--log-level=3')
                        
                        # [핵심 변경] 리눅스 서버에 설치된 크롬과 드라이버 경로를 직접 지정 (에러 127 해결!)
                        chrome_options.binary_location = "/usr/bin/chromium"
                        service = Service("/usr/bin/chromedriver")
                        
                        # 만약 윈도우 로컬에서 테스트할 경우를 대비한 안전장치 (try-except)
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
                            st.success("🎉 검색 완료!")
                            result_df = pd.DataFrame(data['items'])
                            st.dataframe(result_df, use_container_width=True)
                            
                    except Exception as e:
                        st.error(f"서버 접속 중 에러가 발생했습니다: {e}")
                        if 'driver' in locals() and driver:
                            driver.quit()