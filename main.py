import streamlit as st

from src import queries

pages = {
    "현황": [
        st.Page("pages/대시보드.py", title="대시보드", icon=":material/dashboard:", default=True),
    ],
    "생산관리": [
        st.Page("pages/작업지시_관리.py", title="작업지시 관리", icon=":material/assignment:"),
        st.Page("pages/원재료_입고.py", title="원재료 입고", icon=":material/inventory_2:"),
        st.Page("pages/극판공정_실적.py", title="극판공정 실적", icon=":material/science:"),
        st.Page("pages/조립공정_실적.py", title="조립공정 실적", icon=":material/layers:"),
        st.Page("pages/화성공정_실적.py", title="화성공정 실적", icon=":material/bolt:"),
    ],
    "품질/추적": [
        st.Page("pages/셀_시리얼_추적.py", title="셀 시리얼 추적", icon=":material/route:"),
    ],
}

nav = st.navigation(pages)

nav.run()