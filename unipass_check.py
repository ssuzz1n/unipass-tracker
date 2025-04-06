import requests
import json
import smtplib
from email.mime.text import MIMEText
import os

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

with open("tracking_list.txt", "r") as f:
    tracking_list = [line.strip().split(",") for line in f if line.strip()]

for code, invoice in tracking_list:
    url = f"https://asap-china.com/guide/unipass_delivery.php?code={code}&invoice={invoice}"
    res = requests.get(url)
    if res.status_code != 200:
        print(f"[❌ 요청 실패] {code}")
        continue

    html = res.text
    stages = [
        "통관목록접수", "입항적재화물목록 제출", "입항적재화물목록 심사완료",
        "하선신고 수리", "입항보고 수리", "입항적재화물목록 운항정보 정정",
        "반입신고", "반출신고", "통관목록심사완료"
    ]
    current_stage = max([i for i, s in enumerate(stages) if s in html], default=-1)

    if current_stage == 6:  # 반입신고
        msg = MIMEText(f"[📦 반입신고] 송장번호: {code}")
        msg['Subject'] = f"반입신고 도착 - {code}"
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = EMAIL_ADDRESS

        with smtplib.SMTP_SSL('smtp.naver.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"[📬 메일 발송 완료] {code}")

        # 파일에서 삭제
        with open("tracking_list.txt", "r") as f:
            lines = f.readlines()
        with open("tracking_list.txt", "w") as f:
            for line in lines:
                if not line.startswith(code):
                    f.write(line)

    elif current_stage == 8:  # 통관목록심사완료
        print(f"[✅ 자동 삭제] {code}")
        with open("tracking_list.txt", "r") as f:
            lines = f.readlines()
        with open("tracking_list.txt", "w") as f:
            for line in lines:
                if not line.startswith(code):
                    f.write(line)
