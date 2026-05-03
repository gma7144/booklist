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
st.set_page_config(page_title="Scholastic 도서 검색기", layout="wide")
st.title("📚 부산영어도서관 자동 검색 웹앱")
st.markdown("깃허브에 연동된 `booklist.csv`에서 등록번호를 매칭하여 도서를 검색합니다.")

# --- 1. CSV 파일 메모리에 자동 로드 ---
@st.cache_data # 캐시를 사용해 새로고침해도 파일을 매번 읽지 않고 메모리에서 빠르게 가져옴
def load_data():
    try:
        # 깃허브 저장소에 함께 올라간 booklist.csv 파일을 읽어옵니다.
        df = pd.read_csv("booklist.csv")
        return df
    except Exception as e:
        return None

df = load_data()

if df is None:
    st.error("⚠️ 'booklist.csv' 파일을 찾을 수 없거나 읽는 데 실패했습니다. 깃허브에 파일이 있는지 확인해주세요.")
else:
    st.success(f"✅ 데이터 로드 완료! (총 {len(df)}권 대기 중)")
    
    # --- 2 & 3. 등록번호 숫자 입력 박스 ---
    st.markdown("### 🔍 도서 검색")
    col1, col2 = st.columns([3, 1])
    with col1:
        # BGE000330 이면 330만 입력받음
        user_input = st.text_input("등록번호 뒤 숫자만 입력하세요 (예: 330)")
    
    with col2:
        st.write("") # 버튼 위치 맞추기
        st.write("")
        search_btn = st.button("🚀 검색 실행", use_container_width=True)

    if search_btn:
        if not user_input.strip() or not user_input.isdigit():
            st.warning("숫자만 정확히 입력해주세요!")
        else:
            # --- 4. 등록번호와 매칭되는 도서명 찾기 ---
            target_num = int(user_input.strip())
            
            # E열(인덱스 4)에서 숫자만 쏙 뽑아내어 비교용 임시 열을 만듭니다.
            df['추출된숫자'] = df.iloc[:, 4].astype(str).str.extract(r'(\d+)').fillna(-1).astype(int)
            
            # 입력한 숫자와 일치하는 행을 찾습니다.
            matched_row = df[df['추출된숫자'] == target_num]
            
            if matched_row.empty:
                st.error(f"❌ 등록번호 숫자 '{target_num}'에 해당하는 도서를 CSV에서 찾을 수 없습니다.")
            else:
                # 매칭된 A열(인덱스 0)의 도서명 가져오기
                target_title = matched_row.iloc[0, 0]
                target_lexile = matched_row.iloc[0, 1] if len(matched_row.columns) > 1 else "-"
                
                st.info(f"💡 매칭된 도서명: **{target_title}** (Lexile: {target_lexile}) -> 서버 검색을 시작합니다...")
                
                # --- 5. 셀레니움으로 도서관 검색 진행 ---
                with st.spinner("도서관 서버에 접속하여 데이터를 수집 중입니다... (약 5~10초 소요)"):
                    try:
                        # 클라우드 서버(리눅스) 환경에 맞춘 웹드라이버 설정
                        chrome_options = Options()
                        chrome_options.add_argument("--headless=new") # 웹앱 서버는 모니터가 없으므로 무조건 헤드리스
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument('--log-level=3')
                        
                        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                        
                        # 도서관 검색 페이지 접속
                        driver.get("https://library.busan.go.kr/bengbooks/book/search/collectionOfMaterials#searchForm")
                        
                        # 검색어 입력 (A열에서 가져온 도서명)
                        time.sleep(1)
                        search_box = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='검색어']")
                        search_box.clear()
                        search_box.send_keys(target_title)
                        search_box.send_keys(Keys.ENTER)
                        
                        time.sleep(3) # 검색 결과 로딩 대기
                        
                        # 자바스크립트로 화면 데이터 긁어오기 (이전 GUI 로직과 동일)
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
                            st.success("🎉 검색 완료! 아래 결과를 확인하세요.")
                            # 긁어온 데이터를 웹 화면에 예쁜 표(DataFrame)로 출력
                            result_df = pd.DataFrame(data['items'])
                            st.dataframe(result_df, use_container_width=True)
                            
                    except Exception as e:
                        st.error(f"크롤링 중 에러가 발생했습니다: {e}")
                        if 'driver' in locals() and driver:
                            driver.quit()