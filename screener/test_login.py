import requests
import os

LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
LOGIN_URL  = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

login_id = os.getenv("KRX_ID")
login_pw = os.getenv("KRX_PW")
print(f"ID: {login_id}")
print(f"PW 길이: {len(login_pw) if login_pw else 0}")
print(f"PW 첫글자: {login_pw[0] if login_pw else '없음'}")
print(f"PW 마지막글자: {login_pw[-1] if login_pw else '없음'}")

session = requests.Session()
session.get(LOGIN_PAGE, headers={"User-Agent": USER_AGENT}, timeout=15)
session.get(LOGIN_JSP,  headers={"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE}, timeout=15)

payload = {"mbrNm": "", "telNo": "", "di": "", "certType": "", "mbrId": login_id, "pw": login_pw}
resp = session.post(LOGIN_URL, data=payload, headers={"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE}, timeout=15)

print(f"HTTP 상태코드: {resp.status_code}")
print(f"응답 내용: {resp.text}")
