import os
import json
import re
import html
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from datetime import datetime

# 1. 환경 변수 및 포트 설정
PORT = int(os.environ.get("PORT", 8000))

def load_env():
    env_path = ".env"
    if not os.path.exists(env_path): return
    with open(env_path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")

load_env()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 2. 전문적인 문장 다듬기 로직
def clean_record_text(text):
    if not text: return text
    text = re.sub(r'이 학생은|해당 학생은|본인은|저는', '', text).strip()
    sentences = text.split('. ')
    processed = []
    for sent in sentences:
        sent = sent.strip().rstrip('.')
        if not sent: continue
        # 어미 변환 (했다 -> 함 등)
        if not sent.endswith(('함', '됨', '임', '음', '기')):
            if sent.endswith(('했다', '하였다')): sent = sent[:-2] + '함'
            elif sent.endswith(('되었다', '됐다')): sent = sent[:-2] + '됨'
            elif sent.endswith('이다'): sent = sent[:-2] + '임'
        processed.append(sent + ".")
    return " ".join(processed)

# 3. 이미지 양식에 맞춘 프롬프트 빌더 (키워드 반영)
def build_expert_prompt(a_type, a_name, date, keywords):
    return f"""
너는 고등학교 생활기록부 작성 전문가야. 다음 정보를 바탕으로 풍부한 문장을 작성해라.

- 활동 구분: {a_type}
- 활동 일자: {date}
- 활동명: {a_name}
- 관찰 키워드: {keywords}

[작성 지침]
1. 시작은 '{a_name}({date}) 활동에서' 또는 '{a_name}({date})에 참여하여'로 시작할 것.
2. 입력된 '관찰 키워드'를 문장에 자연스럽게 녹여내어 구체적인 행동과 성장이 드러나게 할 것.
3. '특히', '나아가', '이를 바탕으로' 같은 연결어를 사용하여 문맥을 매끄럽게 할 것.
4. 모든 문장은 반드시 명사형 어미(~함, ~임, ~됨)로 끝낼 것.
"""

def call_openai_api(prompt):
    if not OPENAI_API_KEY: return "에러: API Key 미설정"
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "system", "content": "생기부 작성 전문가"}, {"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            res_body = json.loads(res.read().decode("utf-8"))
            return res_body['choices'][0]['message']['content'].strip()
    except Exception as e: return f"연결 에러: {str(e)}"

# 4. 이미지 UI를 그대로 재현한 템플릿
def render_template(result="", a_type="자율활동", a_name="", a_date="", a_keywords=""):
    res_safe = html.escape(result)
    sel_j = "selected" if a_type == "자율활동" else ""
    sel_z = "selected" if a_type == "진로활동" else ""
    
    return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>생활기록부 문장 생성기</title>
    <style>
        body {{ font-family: 'Pretendard', sans-serif; background-color: #f5f7fa; color: #333; display: flex; justify-content: center; padding: 20px; }}
        .container {{ width: 100%; max-width: 600px; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
        .header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 25px; }}
        .header h1 {{ font-size: 22px; color: #1e293b; margin: 0; }}
        .form-group {{ margin-bottom: 18px; }}
        label {{ display: block; font-weight: 600; margin-bottom: 8px; color: #475569; font-size: 14px; }}
        input, select, textarea {{ width: 100%; padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; box-sizing: border-box; font-size: 15px; }}
        textarea {{ resize: vertical; min-height: 100px; }}
        .btn-submit {{ width: 100%; padding: 15px; background: #2563eb; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 10px; transition: background 0.2s; }}
        .btn-submit:hover {{ background: #1d4ed8; }}
        .result-box {{ margin-top: 25px; padding: 20px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }}
        .copy-btn {{ background: #64748b; color: white; border: none; padding: 8px 12px; border-radius: 5px; cursor: pointer; float: right; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span>🎓</span><h1>생활기록부 문장 생성기</h1>
        </div>
        <form method="post" action="/generate">
            <div class="form-group">
                <label>활동 구분</label>
                <select name="a_type">
                    <option value="자율활동" {sel_j}>자율활동</option>
                    <option value="진로활동" {sel_z}>진로활동</option>
                </select>
            </div>
            <div class="form-group">
                <label>활동 날짜</label>
                <input type="date" name="a_date" value="{a_date}" required>
            </div>
            <div class="form-group">
                <label>활동명</label>
                <input type="text" name="a_name" value="{html.escape(a_name)}" placeholder="예: 양성평등 교육, 진로 캠프, 전공 탐색" required>
            </div>
            <div class="form-group">
                <label>내용 키워드 (관찰 기록)</label>
                <textarea name="a_keywords" placeholder="학생이 보여준 구체적인 행동, 소감 등을 적어주세요.">{html.escape(a_keywords)}</textarea>
            </div>
            <button type="submit" class="btn-submit">풍부한 문장 생성하기</button>
        </form>

        {f'''
        <div class="result-box">
            <button class="copy-btn" onclick="copyText()">복사</button>
            <label>생성된 문장</label>
            <textarea id="resultText" rows="6" readonly>{res_safe}</textarea>
        </div>
        ''' if result else ''}
    </div>
    <script>
        function copyText() {{
            const txt = document.getElementById("resultText");
            txt.select();
            document.execCommand("copy");
            alert("복사되었습니다!");
        }}
    </script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(render_template().encode("utf-8"))

    def do_POST(self):
        if self.path == "/generate":
            length = int(self.headers['Content-Length'])
            post_data = parse_qs(self.rfile.read(length).decode('utf-8'))
            t, n, d, k = post_data.get('a_type',[''])[0], post_data.get('a_name',[''])[0], post_data.get('a_date',[''])[0], post_data.get('a_keywords',[''])[0]
            
            # API 호출 및 가공
            prompt = build_expert_prompt(t, n, d, k)
            raw = call_openai_api(prompt)
            final = clean_record_text(raw)
            
            self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(render_template(final, t, n, d, k).encode("utf-8"))

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Server started on port {PORT}")
    server.serve_forever()
