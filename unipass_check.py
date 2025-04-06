import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import os

TRACKING_FILE = "tracking_list.txt"

EMAIL_ADDRESS = "pink_glitter@naver.com"
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

def send_email(invoice_no):
    msg = MIMEText(f"[반입신고 도착] 송장번호 {invoice_no}가 반입신고 단계에 도달했습니다.")
    msg['Subject'] = f"[반입신고 도착] {invoice_no}"
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS

    with smtplib.SMTP_SSL('smtp.naver.com', 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

def check_status(invoice_no):
    url = f"https://asap-china.com/guide/unipass_delivery.php?invoice={invoice_no}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        table = soup.find('table')
        rows = table.find_all('tr')[1:] if table else []

        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 3:
                stage = cols[1].text.strip()
                if '반입신고' in stage:
                    print(f"[반입신고 감지] {invoice_no}")
                    send_email(invoice_no)
                    return True
    except Exception as e:
        print(f"[에러] {invoice_no}: {e}")
    return False

def load_tracking_list():
    if not os.path.exists(TRACKING_FILE):
        return []
    with open(TRACKING_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def save_tracking_list(invoice_list):
    with open(TRACKING_FILE, 'w') as f:
        for invoice in invoice_list:
            f.write(f"{invoice}\n")

def main():
    invoice_list = load_tracking_list()
    remaining_list = []

    for invoice in invoice_list:
        if not check_status(invoice):
            remaining_list.append(invoice)
    
    save_tracking_list(remaining_list)

if __name__ == "__main__":
    main()
