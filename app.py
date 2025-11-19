from flask import Flask
import threading
import time
import schedule
from unipass_check import main  # 찡의 기존 자동화 함수

app = Flask(__name__)

@app.route("/")
def home():
    return "Tracking server running!"

def run_scheduler():
    schedule.every().day.at("09:00").do(main)  # 매일 오전 9시 실행

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    t = threading.Thread(target=run_scheduler)
    t.daemon = True
    t.start()
    app.run(host="0.0.0.0", port=10000)
