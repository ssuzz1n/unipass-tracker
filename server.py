import os
import requests
from flask import Flask

app = Flask(__name__)

# 🔥 GitHub 토큰 (Render 환경변수에서 가져옴)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# 🔥 여기에 네 레포 이름 넣어
GITHUB_REPO = "ssuzz1n/unipass-tracker"


@app.route("/run", methods=["POST"])
def run():

    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.everest-preview+json",
        "Content-Type": "application/json"
    }

    data = {
        "event_type": "run-script"
    }

    requests.post(url, headers=headers, json=data)

    return "Triggered GitHub Actions", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
