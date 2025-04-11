import os
import re
import requests
from bs4 import BeautifulSoup
from email.message import EmailMessage
import smtplib
from urllib.parse import urlparse, parse_qs

# ===================== 📌 환경변수 설정 =====================
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# 🔗 타오바오 상품 URL (👉 원하는 상품 링크로 바꿔서 실행)
TAOBAO_URL = "https://item.taobao.com/item.htm?id=783169758299"

# ===================== 🖼️ 대표 이미지 추출 함수 =====================
def extract_images(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    # 📷 주요 이미지 영역에서 추출
    img_tags = soup.find_all("img")
    candidates = []
    for img in img_tags:
        src = img.get("src") or ""
        if src.startswith("//"):
            src = "https:" + src
        if any(kw in src for kw in ["bao", "img.alicdn.com", "jpg", "png"]):
            candidates.append(src)

    # 중복 제거 및 앞쪽 대표 이미지 위주 선택
    unique = []
    for i in candidates:
        if i not in unique:
            unique.append(i)

    print(f"[🔍 이미지 {len(unique)}개 추출됨]")
    return unique[:5]  # 최대 5장만 첨부

# ===================== 📧 이메일 발송 함수 =====================
def send_email(images):
    msg = EmailMessage()
    msg["Subject"] = "[📸 타오바오 이미지 찾은 결과]"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS

    body = "아래는 타오바오 상품에서 추출한 이미지입니다.\n\n"
    for i, url in enumerate(images):
        body += f"{i+1}. {url}\n"
    msg.set_content(body)

    for i, url in enumerate(images):
        try:
            img_data = requests.get(url).content
            msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename=f"taobao_{i+1}.jpg")
        except Exception as e:
            print(f"[⚠️ 이미지 첨부 실패] {url}: {e}")

    try:
        with smtplib.SMTP_SSL("smtp.naver.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("[📧 이메일 전송 완료]")
    except Exception as e:
        print(f"[⚠️ 이메일 전송 실패] {e}")

# ===================== 🏁 실행 =====================
if __name__ == "__main__":
    print("[✅ 타오바오 이미지 추출 시작]")
    imgs = extract_images(TAOBAO_URL)
    if imgs:
        send_email(imgs)
    else:
        print("[❌ 이미지 없음]")
