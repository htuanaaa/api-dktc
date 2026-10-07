import os
import json
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import uvicorn

load_dotenv()

ENV = os.getenv("ENV", "development").lower()
is_production = (ENV == "production")
API_KEY = os.getenv("API_KEY")
if not API_KEY or not API_KEY.strip():
    raise RuntimeError("Biến API_KEY chưa được thiết lập! vui lòng cấu hình trong file .env")
API_KEY = API_KEY.strip()
COOKIE_FILE = "cookie.json"

app = FastAPI(
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json"
)

CACHED_COOKIE: Optional[str] = None

def load_cookie_from_storage() -> Optional[str]:
    global CACHED_COOKIE
    if CACHED_COOKIE:
        return CACHED_COOKIE
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    CACHED_COOKIE = "; ".join(
                        [f"{c['name']}={c['value']}" for c in data if "name" in c and "value" in c]
                    )
                elif isinstance(data, dict) and "cookie" in data:
                    CACHED_COOKIE = data["cookie"]
                elif isinstance(data, str):
                    CACHED_COOKIE = data
                return CACHED_COOKIE
        except Exception:
            pass
    return None

def save_cookie_to_storage(cookie_str: str):
    global CACHED_COOKIE
    CACHED_COOKIE = cookie_str
    try:
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump({"cookie": cookie_str}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def clear_cached_cookie():
    global CACHED_COOKIE
    CACHED_COOKIE = None
    if os.path.exists(COOKIE_FILE):
        try:
            os.remove(COOKIE_FILE)
        except Exception:
            pass

def verify_api_key(x_api_key: Optional[str] = Header(default=None)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="api key không hợp lệ"
        )

def resolve_cookie(user_cookie: Optional[str]) -> str:
    if user_cookie and user_cookie.strip():
        return user_cookie.strip()
    cached = load_cookie_from_storage()
    if cached and cached.strip():
        return cached.strip()
    raise HTTPException(
        status_code=400,
        detail="hệ thống chưa có cookie..."
    )

def get_request_headers(cookie: str) -> dict:
    return {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'vi,en-US;q=0.9,en;q=0.8,fr-FR;q=0.7,fr;q=0.6',
        'cache-control': 'max-age=0',
        'priority': 'u=0, i',
        'referer': 'https://sinhvien.ictu.edu.vn/SinhVien',
        'sec-ch-ua': '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
        'cookie': cookie
    }

class SetCookieRequest(BaseModel):
    cookie: str

@app.post("/api/internal/set-cookie", dependencies=[Depends(verify_api_key)])
def set_cookie(payload: SetCookieRequest):
    if not payload.cookie or not payload.cookie.strip():
        raise HTTPException(status_code=400, detail="cookie không được để trống")
    save_cookie_to_storage(payload.cookie.strip())
    return {"status": "success", "message": "cập nhật cookie thành công!"}


@app.get("/api/schedule", dependencies=[Depends(verify_api_key)])
def get_schedule(x_user_cookie: Optional[str] = Header(default=None)):
    active_cookie = resolve_cookie(x_user_cookie)
    headers = get_request_headers(active_cookie)
    url = "https://sinhvien.ictu.edu.vn/TraCuuLichHoc/Index"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="không thể kết nối đến máy chủ trường")

    if "formLogin" in response.text:
        if not x_user_cookie:
            clear_cached_cookie()
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "cookie đã hết hạn..."}
        )

    soup = BeautifulSoup(response.text, "html.parser")
    schedule_list = []
    
    table = soup.find("table", class_="tkb-scroll")
    if not table:
        return {"status": "success", "total": 0, "data": []}

    tbody = table.find("tbody")
    if not tbody:
        return {"status": "success", "total": 0, "data": []}

    rows = tbody.find_all("tr")
    current_week = ""

    for row in rows:
        style = row.get("style", "")
        if "background-color:#e8e8e8" in style or "font-weight:bold" in style:
            td = row.find("td")
            if td:
                current_week = td.text.strip()
            continue

        cols = row.find_all("td")
        if len(cols) == 8:
            diadiem_td = cols[5]
            link = diadiem_td.find("a")
            diadiem_text = link["href"] if link else diadiem_td.text.strip()

            subject = {
                "tuan": current_week,
                "stt": cols[0].text.strip(),
                "ten_lop": cols[1].text.strip(),
                "tin_chi": cols[2].text.strip(),
                "thu": cols[3].text.strip(),
                "tiet_hoc": cols[4].text.strip(),
                "dia_diem": diadiem_text,
                "giang_vien": cols[6].text.strip(),
                "ngay_hoc": cols[7].text.strip()
            }
            schedule_list.append(subject)

    return {
        "status": "success",
        "total": len(schedule_list),
        "data": schedule_list
    }

@app.get("/api/exam-schedule", dependencies=[Depends(verify_api_key)])
def get_exam_schedule(x_user_cookie: Optional[str] = Header(default=None)):
    active_cookie = resolve_cookie(x_user_cookie)
    headers = get_request_headers(active_cookie)
    url = "https://sinhvien.ictu.edu.vn/TraCuuLichThi/Index"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="không thể kết nối đến máy chủ trường")

    if "formLogin" in response.text:
        if not x_user_cookie:
            clear_cached_cookie()
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "cookie đã hết hạn..."}
        )

    soup = BeautifulSoup(response.text, "html.parser")
    accordion = soup.find("div", id="accordionDotThi")
    if not accordion:
        data_div = soup.find("div", id="daTa")
        if data_div:
            accordion = data_div.find("div", class_="panel-group")

    if not accordion:
        return {"status": "success", "total_batches": 0, "data": []}

    batches = []
    panels = accordion.find_all("div", class_="panel")
    for panel in panels:
        title_tag = panel.find("h4", class_="panel-title")
        dot_thi_title = title_tag.get_text(strip=True) if title_tag else ""

        table = panel.find("table")
        if not table:
            continue

        tbody = table.find("tbody")
        if not tbody:
            continue

        rows = tbody.find_all("tr")
        exam_list = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) == 11:
                exam_item = {
                    "stt": cols[0].get_text(strip=True),
                    "ma_hp": cols[1].get_text(strip=True),
                    "ten_hp": cols[2].get_text(strip=True),
                    "ngay_thi": cols[3].get_text(strip=True),
                    "ca_thi": cols[4].get_text(strip=True),
                    "gio_thi": cols[5].get_text(strip=True),
                    "lan_thi": cols[6].get_text(strip=True),
                    "dot_thi": cols[7].get_text(strip=True),
                    "sbd": cols[8].get_text(strip=True),
                    "phong_thi": cols[9].get_text(strip=True),
                    "hinh_thuc": cols[10].get_text(strip=True)
                }
                exam_list.append(exam_item)

        batches.append({
            "dot_thi": dot_thi_title,
            "total_mon": len(exam_list),
            "danh_sach_thi": exam_list
        })

    return {
        "status": "success",
        "total_batches": len(batches),
        "data": batches
    }

@app.get("/ping")
def ping():
    return {"status": "alive"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=6969)
