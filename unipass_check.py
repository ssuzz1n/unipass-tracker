import requests
from bs4 import BeautifulSoup
import smtplib
import json
from email.mime.text import MIMEText
from email.utils import formataddr
import os

# 이메일 설정
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # 예: "pink_glitter@naver.com"
EMAIL_NAME = os.getenv("EMAIL_NAME") or "유니패스 알리미"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # 앱 비밀번호
TO_EMAIL = os.getenv("TO_EMAIL") or EMAIL_ADDRESS

# 상태 저장 파일
STATUS_FILE = "unipass_status.json"

# 상태 파일 불러오기
def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    return {}

# 상태 파일 저장
def save_status(status_data):
    with open(STATUS_FILE, "w") as f:
        json.dump(status_data, f, indent=4)

# 처리단계 조회
def check_status(customs_code, invoice_no):
    url = f"https://asap-china.com/guide/unipass_delivery.php?code={customs_code}&invoice={invoice_no}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        tables = soup.find_all("table")
        if len(tables) < 2:
            print(f"[❌ 처리단계 없음] {customs_code}, {invoice_no}")
            return []

        status_table = tables[1]  # 두 번째 테이블이 처리단계 테이블
        rows = status_table.find_all("tr")[1:]  # 첫 줄은 헤더니까 제외

        status_list = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                status = cols[1].text.strip()
                status_list.append(status)

        return status_list
    except Exception as e:
        print(f"[⚠️ 에러] {customs_code}, {invoice_no}: {e}")
        return []


# 메일 발송
def send_email(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((EMAIL_NAME, EMAIL_ADDRESS))
    msg["To"] = TO_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.naver.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"[📧 메일 전송 완료] {subject}")
    except Exception as e:
        print(f"[⚠️ 메일 전송 실패] {e}")

# 메인 로직
def main():
    if not os.path.exists("tracking_list.txt"):
        print("[📂 tracking_list.txt 없음]")
        return

    with open("tracking_list.txt", "r") as f:
        lines = f.readlines()

    status_data = load_status()
    new_lines = []

    for line in lines:
        customs_code, invoice_no = line.strip().split(",")
        key = f"{customs_code}_{invoice_no}"

        status_list = check_status(customs_code, invoice_no)
        if not status_list:
            new_lines.append(line)
            continue

        if "반입신고" in status_list:
            if status_data.get(key) != "반입신고":
                # 메일 보내고 삭제
                subject = "[✅ 자동 삭제] " + invoice_no
                body = f"송장번호 {invoice_no}가 반입신고 상태에 도달하여 자동으로 리스트에서 삭제되었습니다."
                send_email(subject, body)
                status_data[key] = "반입신고"
                print(f"[✅ 삭제 및 메일 발송] {invoice_no}")
            # 리스트에서 제거 (삭제)
        else:
            new_lines.append(line)

    # 파일 업데이트
    with open("tracking_list.txt", "w") as f:
        f.writelines(new_lines)

    save_status(status_data)

if __name__ == "__main__":
    print(f"[DEBUG] EMAIL_ADDRESS: {EMAIL_ADDRESS}")
print(f"[DEBUG] EMAIL_PASSWORD: {'SET' if EMAIL_PASSWORD else 'NOT SET'}")
print(f"[DEBUG] EMAIL_NAME: {EMAIL_NAME}")
print(f"[DEBUG] TO_EMAIL: {TO_EMAIL}")
    main()
