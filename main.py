from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import uvicorn

app = FastAPI()

@app.get("/api/schedule")
def get_schedule(x_user_cookie: str = Header(default=None)):
    if not x_user_cookie:
        raise HTTPException(status_code=400, detail="thiếu header cookie")
    
    headers = {
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
        'cookie': x_user_cookie
    }
    
    url = "https://sinhvien.ictu.edu.vn/TraCuuLichHoc/Index"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="không thể kết nối đến máy chủ trường")

    if "formLogin" in response.text:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "cookie đã hết hạn, yêu cầu renew"}
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=6969)