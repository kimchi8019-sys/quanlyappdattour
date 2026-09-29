import os
import math
import hashlib
import re
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
import mysql.connector
from decimal import Decimal
from html import escape as _escape


def _ver():
    try:
        return tuple(int(x) for x in st.__version__.split(".")[:2])
    except Exception:
        return (1, 0)


STRETCH = {"width": "stretch"} if _ver() >= (1, 50) else {"use_container_width": True}

# ============================================================
# SMART TOUR - ĐẶT TOUR TRỌN GÓI (Streamlit + MySQL Aiven)
# Cài đặt:  pip install streamlit pandas mysql-connector-python
# Chạy:     streamlit run app.py
# ============================================================

st.set_page_config(page_title="SMART TOUR", page_icon="✈️", layout="wide",
                   initial_sidebar_state="expanded")

# ------------------------------------------------------------
# 1. CẤU HÌNH KẾT NỐI AIVEN MYSQL  (điền thông tin của bạn ở đây)
#    Hoặc dùng .streamlit/secrets.toml với mục [mysql], hoặc biến môi trường MYSQL_*
# ------------------------------------------------------------
DB_CONFIG = {
    "host": "mysql-1b346c1b-kimchi8019-4ea9.e.aivencloud.com",   # <-- Host trong Aiven
    "port": 21314,                            # <-- Port trong Aiven
    "user": "avnadmin",                      # <-- User
    "password": "AVNS_ZuLUVTHk6cKBskjg0Kp",             # <-- Password
    "database": "defaultdb",                 # <-- Database name
}


def load_db_config():
    cfg = dict(DB_CONFIG)
    try:
        sec = st.secrets["mysql"]
        for k in cfg:
            if k in sec:
                cfg[k] = sec[k]
    except Exception:
        pass
    for k in cfg:
        v = os.getenv("MYSQL_" + k.upper())
        if v:
            cfg[k] = v
    cfg["port"] = int(cfg["port"])
    return cfg


def new_conn():
    c = load_db_config()
    conn = mysql.connector.connect(
        host=c["host"], port=c["port"], user=c["user"], password=c["password"],
        database=c["database"], ssl_disabled=False,   # Aiven bắt buộc SSL
        autocommit=True, connection_timeout=20, charset="utf8mb4")
    cur = conn.cursor()
    cur.execute("SET time_zone = '+07:00'")
    cur.close()
    return conn


def get_conn():
    conn = st.session_state.get("_conn")
    try:
        if conn is None:
            raise RuntimeError
        conn.ping(reconnect=True, attempts=3, delay=1)
        if conn.in_transaction:
            conn.rollback()
    except Exception:
        conn = new_conn()
        st.session_state["_conn"] = conn
    return conn


def _norm(v):
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        return v.item()
    return v


def _params(params):
    return tuple(_norm(x) for x in params)


def query_df(sql, params=()):
    cur = get_conn().cursor()
    cur.execute(sql, _params(params))
    rows = cur.fetchall()
    cols = list(cur.column_names)
    cur.close()
    rows = [tuple(float(x) if isinstance(x, Decimal) else x for x in r) for r in rows]
    return pd.DataFrame(rows, columns=cols)


def execute_rc(sql, params=()):
    cur = get_conn().cursor()
    cur.execute(sql, _params(params))
    n = cur.rowcount
    cur.close()
    return n


def execute(sql, params=()):
    cur = get_conn().cursor()
    cur.execute(sql, _params(params))
    last = cur.lastrowid
    cur.close()
    return last


# ------------------------------------------------------------
# 2. KHỞI TẠO DATABASE + DỮ LIỆU MẪU
# ------------------------------------------------------------
def hash_password(p):
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


@st.cache_resource(show_spinner="Đang khởi tạo cơ sở dữ liệu...")
def init_db():
    conn = new_conn()
    cur = conn.cursor()
    T = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ddl = [
        f"""CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(120) NOT NULL,
            phone VARCHAR(20) NOT NULL UNIQUE,
            role VARCHAR(20) NOT NULL DEFAULT 'customer',
            password VARCHAR(100) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP) {T}""",
        f"""CREATE TABLE IF NOT EXISTS tours (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            destination VARCHAR(100) NOT NULL,
            days INT NOT NULL DEFAULT 3,
            nights INT NOT NULL DEFAULT 2,
            adult_price DOUBLE NOT NULL DEFAULT 0,
            child_price DOUBLE NOT NULL DEFAULT 0,
            interests VARCHAR(300) DEFAULT '',
            description TEXT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'Đang mở') {T}""",
        f"""CREATE TABLE IF NOT EXISTS departures (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tour_id INT NOT NULL,
            depart_at DATETIME NOT NULL,
            total_seats INT NOT NULL DEFAULT 30,
            available_seats INT NOT NULL DEFAULT 30,
            meeting_point VARCHAR(200) DEFAULT 'Văn phòng SMART TOUR',
            FOREIGN KEY (tour_id) REFERENCES tours(id)) {T}""",
        f"""CREATE TABLE IF NOT EXISTS hotels (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            destination VARCHAR(100) NOT NULL,
            stars INT NOT NULL DEFAULT 3,
            room_type VARCHAR(60) NOT NULL DEFAULT 'Phòng đôi',
            price_per_room DOUBLE NOT NULL DEFAULT 0,
            total_rooms INT NOT NULL DEFAULT 10,
            available_rooms INT NOT NULL DEFAULT 10,
            description VARCHAR(300) DEFAULT '',
            status VARCHAR(30) NOT NULL DEFAULT 'Đang hoạt động') {T}""",
        f"""CREATE TABLE IF NOT EXISTS meal_plans (
            id INT AUTO_INCREMENT PRIMARY KEY,
            destination VARCHAR(100) NOT NULL,
            restaurant VARCHAR(150) NOT NULL,
            plan_name VARCHAR(150) NOT NULL,
            meals_per_day INT NOT NULL DEFAULT 3,
            price_adult DOUBLE NOT NULL DEFAULT 0,
            price_child DOUBLE NOT NULL DEFAULT 0,
            description VARCHAR(300) DEFAULT '',
            status VARCHAR(30) NOT NULL DEFAULT 'Đang phục vụ') {T}""",
        f"""CREATE TABLE IF NOT EXISTS transports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tour_id INT NOT NULL,
            name VARCHAR(150) NOT NULL,
            vehicle_type VARCHAR(50) NOT NULL DEFAULT 'Xe du lịch',
            price_adult DOUBLE NOT NULL DEFAULT 0,
            price_child DOUBLE NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'Đang hoạt động',
            FOREIGN KEY (tour_id) REFERENCES tours(id)) {T}""",
        f"""CREATE TABLE IF NOT EXISTS price_seasons (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            destination VARCHAR(100) NOT NULL DEFAULT 'Tất cả',
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            surcharge_pct DOUBLE NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'Đang áp dụng') {T}""",
        f"""CREATE TABLE IF NOT EXISTS bookings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            tour_id INT NOT NULL,
            departure_id INT NOT NULL,
            hotel_id INT NOT NULL,
            meal_plan_id INT NOT NULL,
            transport_id INT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            adults INT NOT NULL,
            children INT NOT NULL DEFAULT 0,
            rooms INT NOT NULL DEFAULT 1,
            tour_cost DOUBLE NOT NULL,
            room_cost DOUBLE NOT NULL,
            peak_surcharge DOUBLE NOT NULL DEFAULT 0,
            meal_cost DOUBLE NOT NULL,
            transport_cost DOUBLE NOT NULL,
            total_amount DOUBLE NOT NULL,
            payment_method VARCHAR(60) NOT NULL,
            payment_status VARCHAR(30) NOT NULL DEFAULT 'Chưa thanh toán',
            booking_status VARCHAR(30) NOT NULL DEFAULT 'Chờ xác nhận',
            note VARCHAR(500) DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (tour_id) REFERENCES tours(id),
            FOREIGN KEY (departure_id) REFERENCES departures(id),
            FOREIGN KEY (hotel_id) REFERENCES hotels(id),
            FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id),
            FOREIGN KEY (transport_id) REFERENCES transports(id)) {T}""",
        f"""CREATE TABLE IF NOT EXISTS payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            booking_id INT NOT NULL,
            amount DOUBLE NOT NULL,
            method VARCHAR(60) NOT NULL,
            paid_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(30) NOT NULL DEFAULT 'Thành công',
            FOREIGN KEY (booking_id) REFERENCES bookings(id)) {T}""",
    ]
    for s in ddl:
        cur.execute(s)

    # ---- Admin mặc định (đăng nhập: admin / admin123)
    cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (full_name, phone, role, password) VALUES (%s,%s,'admin',%s)",
                    ("Quản trị viên", "admin", hash_password("admin123")))

    # ---- Dữ liệu mẫu
    cur.execute("SELECT COUNT(*) FROM tours")
    if cur.fetchone()[0] == 0:
        tours = [
            ("Vũng Tàu 3N2Đ - Biển & Ẩm thực", "Vũng Tàu", 3, 2, 1200000, 800000, "biển,ăn uống,nghỉ dưỡng,chụp ảnh",
             "Bãi Sau, Bạch Dinh, Núi Nhỏ, Hải Đăng và thưởng thức hải sản.", "bus"),
            ("Đà Lạt 3N2Đ - Hoa & Sống ảo", "Đà Lạt", 3, 2, 1600000, 1100000, "thiên nhiên,chụp ảnh,ăn uống,cafe",
             "Săn mây, vườn hoa, đồi chè, cà phê view đẹp và chợ đêm Đà Lạt.", "bus"),
            ("Phú Quốc 4N3Đ - Biển đảo", "Phú Quốc", 4, 3, 2200000, 1500000, "biển,nghỉ dưỡng,hải sản,gia đình",
             "Lặn ngắm san hô, cáp treo Hòn Thơm, chợ đêm và đặc sản Phú Quốc.", "air"),
            ("Nha Trang 3N2Đ - Biển & Giải trí", "Nha Trang", 3, 2, 1800000, 1200000, "biển,gia đình,giải trí,ăn uống",
             "Tour 4 đảo, tháp Bà Ponagar, tắm bùn khoáng và ẩm thực địa phương.", "air"),
            ("Đà Nẵng - Hội An 4N3Đ", "Đà Nẵng - Hội An", 4, 3, 2000000, 1400000, "biển,văn hóa,chụp ảnh,ăn uống",
             "Bà Nà Hills, Cầu Vàng, phố cổ Hội An và thả đèn hoa đăng.", "air"),
            ("Tây Nguyên 3N2Đ - Thiên nhiên & Văn hóa", "Buôn Ma Thuột", 3, 2, 1700000, 1100000,
             "thiên nhiên,văn hóa,khám phá,ăn uống", "Thác Dray Nur, buôn Đôn, văn hóa cồng chiêng và cà phê.", "bus"),
        ]
        trans_bus = [("Xe du lịch 45 chỗ đời mới", "Xe du lịch", 300000, 150000),
                     ("Xe Limousine VIP 9 chỗ", "Limousine", 600000, 400000)]
        trans_air = [("Máy bay phổ thông (khứ hồi)", "Máy bay", 2400000, 1800000),
                     ("Máy bay + xe đưa đón sân bay", "Máy bay", 2900000, 2200000)]
        hours = [(6, 0), (7, 30), (13, 0), (5, 30), (8, 0)]
        for i, (n, dest, d, ng, ap, cp, it, ds, tp) in enumerate(tours):
            cur.execute("INSERT INTO tours (name,destination,days,nights,adult_price,child_price,interests,description)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (n, dest, d, ng, ap, cp, it, ds))
            tid = cur.lastrowid
            for k, off in enumerate([5, 12, 19, 26, 40]):
                h, m = hours[(i + k) % len(hours)]
                dt = (datetime.now() + timedelta(days=off + i % 3)).replace(hour=h, minute=m, second=0, microsecond=0)
                cur.execute("INSERT INTO departures (tour_id,depart_at,total_seats,available_seats) VALUES (%s,%s,30,30)",
                            (tid, dt))
            for (tn, vt, pa, pc) in (trans_bus if tp == "bus" else trans_air):
                cur.execute("INSERT INTO transports (tour_id,name,vehicle_type,price_adult,price_child) VALUES (%s,%s,%s,%s,%s)",
                            (tid, tn, vt, pa, pc))

    cur.execute("SELECT COUNT(*) FROM hotels")
    if cur.fetchone()[0] == 0:
        hotels = [
            ("Ocean Vũng Tàu Hotel", "Vũng Tàu", 3, "Phòng đôi", 750000, 20, "Gần biển, phù hợp nghỉ dưỡng."),
            ("Sea Star Vũng Tàu", "Vũng Tàu", 4, "Phòng đôi", 1150000, 15, "4 sao, hồ bơi và tiện nghi đầy đủ."),
            ("Dalat Garden Hotel", "Đà Lạt", 3, "Phòng đôi", 850000, 20, "Yên tĩnh, gần trung tâm."),
            ("Pine Hill Đà Lạt", "Đà Lạt", 4, "Phòng đôi", 1350000, 15, "Cao cấp, view đồi thông."),
            ("Island Pearl Phú Quốc", "Phú Quốc", 4, "Phòng đôi", 1650000, 20, "Gần biển, nghỉ dưỡng."),
            ("Coco Bay Phú Quốc", "Phú Quốc", 3, "Phòng đôi", 1100000, 20, "Giá tốt, gần chợ đêm."),
            ("Sun Bay Nha Trang", "Nha Trang", 3, "Phòng đôi", 950000, 20, "Thuận tiện, gần biển."),
            ("Nha Trang Luxury Bay", "Nha Trang", 4, "Phòng đôi", 1550000, 15, "View vịnh, hồ bơi vô cực."),
            ("Hoi An Riverside", "Đà Nẵng - Hội An", 4, "Phòng đôi", 1450000, 15, "Bên sông, gần phố cổ."),
            ("Dragon Bridge Đà Nẵng", "Đà Nẵng - Hội An", 3, "Phòng đôi", 950000, 20, "Gần cầu Rồng và biển Mỹ Khê."),
            ("Highland Coffee Resort", "Buôn Ma Thuột", 3, "Phòng đôi", 800000, 15, "Gần điểm tham quan thiên nhiên."),
            ("Tây Nguyên Grand Hotel", "Buôn Ma Thuột", 4, "Phòng đôi", 1250000, 15, "Trung tâm thành phố, đầy đủ tiện nghi."),
        ]
        for n, dest, st_, rt, pr, tot, ds in hotels:
            cur.execute("INSERT INTO hotels (name,destination,stars,room_type,price_per_room,total_rooms,available_rooms,description)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (n, dest, st_, rt, pr, tot, tot, ds))

    cur.execute("SELECT COUNT(*) FROM meal_plans")
    if cur.fetchone()[0] == 0:
        rest = {"Vũng Tàu": "Nhà hàng Hải sản Bãi Sau", "Đà Lạt": "Nhà hàng Đồi Thông", "Phú Quốc": "Nhà hàng Hải sản Dinh Cậu",
                "Nha Trang": "Nhà hàng Hải sản Hòn Chồng", "Đà Nẵng - Hội An": "Nhà hàng Mỹ Khê - Phố Cổ",
                "Buôn Ma Thuột": "Nhà hàng Cao Nguyên"}
        for dest, r in rest.items():
            cur.execute("INSERT INTO meal_plans (destination,restaurant,plan_name,meals_per_day,price_adult,price_child,description)"
                        " VALUES (%s,%s,'Buffet sáng tại khách sạn',1,90000,50000,'Ăn sáng buffet mỗi ngày')", (dest, "Khách sạn"))
            cur.execute("INSERT INTO meal_plans (destination,restaurant,plan_name,meals_per_day,price_adult,price_child,description)"
                        " VALUES (%s,%s,'Trọn gói 3 bữa/ngày (sáng + trưa + tối)',3,350000,200000,'Thực đơn đặc sản địa phương')",
                        (dest, r))

    cur.execute("SELECT COUNT(*) FROM price_seasons")
    if cur.fetchone()[0] == 0:
        seasons = [("Noel & Tết Dương lịch", "2026-12-24", "2027-01-03", 25),
                   ("Tết Nguyên đán 2027", "2027-02-04", "2027-02-14", 50),
                   ("Lễ 30/4 - 1/5", "2027-04-29", "2027-05-03", 30),
                   ("Mùa hè", "2027-06-01", "2027-08-31", 15),
                   ("Lễ Quốc khánh 2/9", "2027-08-31", "2027-09-03", 25)]
        for n, a, b, p in seasons:
            cur.execute("INSERT INTO price_seasons (name,destination,start_date,end_date,surcharge_pct) VALUES (%s,'Tất cả',%s,%s,%s)",
                        (n, a, b, p))
    conn.close()
    return True


try:
    init_db()
except Exception as e:
    st.error("❌ Không kết nối được MySQL Aiven. Kiểm tra lại Host / Port / User / Password ở đầu file app.py.")
    st.code(str(e))
    st.stop()


# ------------------------------------------------------------
# 3. HÀM TIỆN ÍCH
# ------------------------------------------------------------
def money(v):
    return f"{float(v):,.0f} ₫".replace(",", ".")


def fdt(v):
    return pd.to_datetime(v).strftime("%H:%M - %d/%m/%Y")


def s(v):
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def esc(v):
    return _escape(s(v)).replace("$", "&#36;").replace("\r", " ").replace("\n", " ")


def html(text):
    st.markdown("\n".join(l.strip() for l in text.splitlines() if l.strip()), unsafe_allow_html=True)


def clean(v):
    if v is None or (not isinstance(v, (list, dict)) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if hasattr(v, "item"):
        return v.item()
    return v


STATUS_COLOR = {"Chờ xác nhận": "#f59e0b", "Đã xác nhận": "#0b5ed7", "Đã hoàn thành": "#16a34a", "Đã hủy": "#dc2626",
                "Đã thanh toán": "#16a34a", "Chưa thanh toán": "#f59e0b", "Chờ hoàn tiền": "#dc2626"}


def badge(text):
    return f'<span class="badge" style="background:{STATUS_COLOR.get(text, "#64748b")}">{text}</span>'


def table_editor(table, cols, key, config=None):
    """Bảng chỉnh sửa trực tiếp: sửa ô, thêm dòng mới (dòng cuối), xóa dòng -> bấm Lưu."""
    df = query_df(f"SELECT {', '.join(cols)} FROM {table} ORDER BY id")
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, **STRETCH,
                            disabled=["id"], column_config=config or {}, key=f"ed_{key}")
    if st.button("💾 Lưu thay đổi", key=f"save_{key}", type="primary"):
        ok, conn = True, get_conn()
        cur = conn.cursor()
        try:
            conn.start_transaction()
            old_ids, keep = set(df["id"].astype(int)), set()
            for _, r in edited.iterrows():
                vals = {c: clean(r[c]) for c in cols if c != "id"}
                rid = clean(r["id"])
                if rid is None:
                    ins = {k: v for k, v in vals.items() if v is not None}
                    if ins:
                        cur.execute(f"INSERT INTO {table} ({','.join(ins)}) VALUES ({','.join(['%s'] * len(ins))})",
                                    list(ins.values()))
                else:
                    keep.add(int(rid))
                    cur.execute(f"UPDATE {table} SET {', '.join(k + '=%s' for k in vals)} WHERE id=%s",
                                list(vals.values()) + [int(rid)])
            for rid in old_ids - keep:
                cur.execute(f"DELETE FROM {table} WHERE id=%s", (rid,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            ok = False
            st.error(f"Không lưu được (có thể thiếu dữ liệu bắt buộc hoặc mục đang được đơn đặt sử dụng): {e}")
        finally:
            cur.close()
        if ok:
            st.success("Đã lưu thay đổi.")
            st.rerun()


# ------------------------------------------------------------
# 4. NGHIỆP VỤ: BÁO GIÁ - ĐẶT TOUR - HỦY
# ------------------------------------------------------------
def make_quote(tour, dep_dt, hotel, meal, trans, adults, children, rooms):
    """Tính giá trọn gói. Giá phòng tự cộng phụ thu theo từng đêm nếu rơi vào mùa cao điểm admin đã đặt."""
    d0 = pd.to_datetime(dep_dt).date()
    seasons = query_df("SELECT * FROM price_seasons WHERE status='Đang áp dụng' AND (destination='Tất cả' OR destination=%s)",
                       (tour["destination"],))
    base_room = extra = 0.0
    peaks = []
    for i in range(int(tour["nights"])):
        d = d0 + timedelta(days=i)
        pct, nm = None, ""
        for _, se in seasons.iterrows():
            if pd.to_datetime(se["start_date"]).date() <= d <= pd.to_datetime(se["end_date"]).date():
                if pct is None or se["surcharge_pct"] > pct:
                    pct, nm = float(se["surcharge_pct"]), se["name"]
        night_base = float(hotel["price_per_room"]) * rooms
        base_room += night_base
        if pct:
            extra += night_base * pct / 100
            peaks.append(f"Đêm {d:%d/%m}: {nm} ({pct:+.0f}%)")
    tour_cost = adults * float(tour["adult_price"]) + children * float(tour["child_price"])
    meal_cost = (adults * float(meal["price_adult"]) + children * float(meal["price_child"])) * int(tour["days"])
    trans_cost = adults * float(trans["price_adult"]) + children * float(trans["price_child"])
    room_cost = base_room + extra
    return dict(tour=tour_cost, room=room_cost, base_room=base_room, peak=extra, meal=meal_cost,
                trans=trans_cost, total=tour_cost + room_cost + meal_cost + trans_cost, peaks=peaks)


def create_booking(uid, tour_id, dep_id, hotel_id, meal_id, trans_id, adults, children, rooms, q, method, note):
    conn = get_conn()
    cur = conn.cursor()
    try:
        conn.start_transaction()
        cur.execute("UPDATE departures SET available_seats=available_seats-%s WHERE id=%s AND available_seats>=%s",
                    (adults + children, dep_id, adults + children))
        if cur.rowcount == 0:
            raise ValueError("Chuyến khởi hành không còn đủ chỗ.")
        cur.execute("UPDATE hotels SET available_rooms=available_rooms-%s WHERE id=%s AND available_rooms>=%s",
                    (rooms, hotel_id, rooms))
        if cur.rowcount == 0:
            raise ValueError("Khách sạn không còn đủ phòng.")
        cur.execute("""INSERT INTO bookings (user_id,tour_id,departure_id,hotel_id,meal_plan_id,transport_id,adults,children,
                       rooms,tour_cost,room_cost,peak_surcharge,meal_cost,transport_cost,total_amount,payment_method,note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (uid, tour_id, dep_id, hotel_id, meal_id, trans_id, adults, children, rooms,
                     q["tour"], q["room"], q["peak"], q["meal"], q["trans"], q["total"], method, note))
        bid = cur.lastrowid
        conn.commit()
        return bid
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def cancel_booking(bid):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cur.execute("SELECT * FROM bookings WHERE id=%s FOR UPDATE", (bid,))
        b = cur.fetchone()
        if not b or b["booking_status"] == "Đã hủy":
            conn.rollback()
            return False
        cur.execute("UPDATE departures SET available_seats=available_seats+%s WHERE id=%s",
                    (b["adults"] + b["children"], b["departure_id"]))
        cur.execute("UPDATE hotels SET available_rooms=available_rooms+%s WHERE id=%s", (b["rooms"], b["hotel_id"]))
        pay = "Chờ hoàn tiền" if b["payment_status"] == "Đã thanh toán" else b["payment_status"]
        cur.execute("UPDATE bookings SET booking_status='Đã hủy', payment_status=%s WHERE id=%s", (pay, bid))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


BOOKING_SQL = """
SELECT b.*, u.full_name, u.phone, t.name AS tour_name, t.destination, t.days, t.nights,
       d.depart_at, d.meeting_point, h.name AS hotel_name, h.stars, h.room_type,
       m.restaurant, m.plan_name, m.meals_per_day, tr.name AS transport_name
FROM bookings b
JOIN users u ON b.user_id=u.id
JOIN tours t ON b.tour_id=t.id
JOIN departures d ON b.departure_id=d.id
JOIN hotels h ON b.hotel_id=h.id
JOIN meal_plans m ON b.meal_plan_id=m.id
JOIN transports tr ON b.transport_id=tr.id
"""


def render_ticket(b):
    b = b.copy()
    for k in ("full_name", "note", "tour_name", "hotel_name", "restaurant", "plan_name", "transport_name", "meeting_point"):
        b[k] = esc(b[k])
    peak = (f'<div class="row"><span>↳ Trong đó phụ thu cao điểm</span><span>{money(b["peak_surcharge"])}</span></div>'
            if float(b["peak_surcharge"]) else "")
    html(f"""
    <div class="ticket">
    <div class="tk-head"><div><b>🎫 PHIẾU ĐẶT TOUR #{int(b['id'])}</b><br>
    <small>Đặt lúc {fdt(b['created_at'])}</small></div>
    <div>{badge(b['booking_status'])} {badge(b['payment_status'])}</div></div>
    <h3>🌴 {b['tour_name']}</h3>
    <p>👤 <b>{b['full_name']}</b> · 📞 {b['phone']}</p>
    <p>🕒 Khởi hành: <b>{fdt(b['depart_at'])}</b> · 📍 Điểm đón: {s(b['meeting_point'])}</p>
    <p>👥 {int(b['adults'])} người lớn, {int(b['children'])} trẻ em · ⏱️ {int(b['days'])} ngày {int(b['nights'])} đêm</p>
    <p>🏨 {b['hotel_name']} ({'⭐' * int(b['stars'])}) · {b['room_type']} × {int(b['rooms'])} phòng</p>
    <p>🍽️ {b['restaurant']} — {b['plan_name']}</p>
    <p>🚐 {b['transport_name']}</p>
    <div class="row"><span>Tour (vé, HDV, tham quan)</span><span>{money(b['tour_cost'])}</span></div>
    <div class="row"><span>Phòng ở</span><span>{money(b['room_cost'])}</span></div>
    {peak}
    <div class="row"><span>Bữa ăn nhà hàng</span><span>{money(b['meal_cost'])}</span></div>
    <div class="row"><span>Xe cộ / vé di chuyển</span><span>{money(b['transport_cost'])}</span></div>
    <div class="row total"><span>TỔNG CỘNG</span><span>{money(b['total_amount'])}</span></div>
    <p class="small">💳 {b['payment_method']}{' · 📝 ' + s(b['note']) if s(b['note']) else ''}</p>
    </div>""")


# ------------------------------------------------------------
# 5. GIAO DIỆN (CSS)
# ------------------------------------------------------------
st.markdown("""
<style>
.stApp{background:#f4f7fb}
.hero{padding:30px;border-radius:20px;background:linear-gradient(135deg,#0b5ed7,#06b6d4);color:#fff;margin-bottom:20px;
box-shadow:0 8px 24px rgba(11,94,215,.25)}
.hero h1,.hero h2,.hero p{color:#fff!important;margin:4px 0}
.card{background:#fff;padding:20px;border-radius:15px;box-shadow:0 2px 12px rgba(0,0,0,.07);margin-bottom:15px;height:100%}
.recommend{border-left:5px solid #0b5ed7;background:#fff;padding:18px;border-radius:12px;margin-bottom:8px;
box-shadow:0 2px 10px rgba(0,0,0,.06)}
.recommend h3{margin:0 0 6px}
.price{color:#0b5ed7;font-size:20px;font-weight:700}
.small{color:#667085;font-size:14px}
.badge{color:#fff;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;margin-left:4px}
.peak{background:#fff7ed;border:1px solid #fdba74;color:#9a3412;padding:10px 14px;border-radius:10px;margin:6px 0;font-size:14px}
.ticket{background:#fff;border-radius:16px;padding:22px;box-shadow:0 4px 18px rgba(0,0,0,.09);border-top:6px solid #0b5ed7;margin-bottom:12px}
.ticket h3{margin:10px 0 6px;color:#0b5ed7}.ticket p{margin:4px 0}
.tk-head{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px}
.row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed #e5e7eb}
.row.total{font-size:20px;font-weight:800;color:#0b5ed7;border-bottom:none;border-top:2px solid #0b5ed7;margin-top:6px;padding-top:10px}
[data-testid="stMetric"]{background:#fff;padding:15px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.05)}
</style>
""", unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

# ------------------------------------------------------------
# 6. ĐĂNG NHẬP (khách chỉ cần Họ tên + Số điện thoại)
# ------------------------------------------------------------
if st.session_state.user is None:
    html("""<div class="hero"><h1>✈️ SMART TOUR</h1><p>Đặt tour trọn gói nhanh chóng, minh bạch</p>
    <p>🗓️ Ngày giờ khởi hành • 🏨 Phòng ở • 🍽️ Bữa ăn nhà hàng • 🚐 Xe cộ • 💰 Giá cao điểm minh bạch</p></div>""")
    t1, t2 = st.tabs(["🧳 Khách hàng", "🔐 Quản trị viên"])

    with t1:
        st.subheader("Bắt đầu đặt tour chỉ với 2 thông tin")
        with st.form("cust_login"):
            name = st.text_input("Họ và tên *")
            phone = st.text_input("Số điện thoại *", placeholder="VD: 0901234567")
            go = st.form_submit_button("🚀 Vào đặt tour", **STRETCH)
        if go:
            ph = re.sub(r"[\s.\-]", "", phone)
            if not name.strip():
                st.error("Vui lòng nhập họ tên.")
            elif not re.fullmatch(r"(\+84|0)\d{9,10}", ph):
                st.error("Số điện thoại không hợp lệ (VD: 0901234567).")
            else:
                ph = "0" + ph[3:] if ph.startswith("+84") else ph
                found = query_df("SELECT * FROM users WHERE phone=%s AND role='customer'", (ph,))
                if found.empty:
                    uid = execute("INSERT INTO users (full_name, phone, role) VALUES (%s,%s,'customer')", (name.strip(), ph))
                    found = query_df("SELECT * FROM users WHERE id=%s", (uid,))
                st.session_state.user = {k: clean(v) for k, v in found.iloc[0].to_dict().items()}
                st.rerun()
        st.caption("Số điện thoại dùng để tra cứu các đơn đã đặt của bạn.")

    with t2:
        with st.form("admin_login"):
            au = st.text_input("Tài khoản")
            ap = st.text_input("Mật khẩu", type="password")
            go2 = st.form_submit_button("🔐 Đăng nhập quản trị", **STRETCH)
        if go2:
            f = query_df("SELECT * FROM users WHERE phone=%s AND role='admin' AND password=%s",
                         (au.strip(), hash_password(ap)))
            if f.empty:
                st.error("Sai tài khoản hoặc mật khẩu.")
            else:
                st.session_state.user = {k: clean(v) for k, v in f.iloc[0].to_dict().items()}
                st.rerun()
        st.caption("Khu vực dành riêng cho quản trị viên.")
    st.stop()

user = st.session_state.user
_chk = query_df("SELECT id, role FROM users WHERE id=%s", (user["id"],))
if _chk.empty:
    st.session_state.user = None
    st.rerun()
user["role"] = _chk.iloc[0]["role"]
is_admin = user["role"] == "admin"

# ------------------------------------------------------------
# 7. SIDEBAR
# ------------------------------------------------------------
st.sidebar.markdown("# ✈️ SMART TOUR")
st.sidebar.caption("Đặt tour trọn gói")
st.sidebar.markdown("---")
menu = ["🏠 Trang chủ", "🔎 Tìm & đặt tour", "📋 Tour của tôi", "💳 Thanh toán"]
if is_admin:
    menu += ["🔧 Quản lý tour", "🏨 Khách sạn & giá cao điểm", "🍽️ Nhà hàng & bữa ăn",
             "👥 Quản lý khách hàng", "🧾 Quản lý đơn đặt", "📊 Dashboard Admin"]
if is_admin:
    menu = [m for m in menu if not m.endswith(("Tìm & đặt tour", "Tour của tôi", "Thanh toán"))]
page = st.sidebar.radio("MENU", menu)
ADMIN_SUFFIX = ("Quản lý tour", "Khách sạn & giá cao điểm", "Nhà hàng & bữa ăn",
                "Quản lý khách hàng", "Quản lý đơn đặt", "Dashboard Admin")
if not is_admin and page.endswith(ADMIN_SUFFIX):
    st.stop()
st.sidebar.markdown("---")
st.sidebar.write(f"👤 {user['full_name']}")
st.sidebar.caption("Quản trị viên" if is_admin else f"📞 {user['phone']}")
if st.sidebar.button("🚪 Đăng xuất", **STRETCH):
    for k in list(st.session_state.keys()):
        if k != "_conn":
            st.session_state.pop(k, None)
    st.rerun()


if is_admin:
    with st.sidebar.expander("🔑 Đổi mật khẩu admin"):
        with st.form("chg_pw"):
            old_pw = st.text_input("Mật khẩu hiện tại", type="password")
            new_pw = st.text_input("Mật khẩu mới (từ 6 ký tự)", type="password")
            new_pw2 = st.text_input("Nhập lại mật khẩu mới", type="password")
            chg = st.form_submit_button("Đổi mật khẩu", **STRETCH)
        if chg:
            okp = query_df("SELECT id FROM users WHERE id=%s AND password=%s", (user["id"], hash_password(old_pw)))
            if okp.empty:
                st.error("Mật khẩu hiện tại không đúng.")
            elif len(new_pw) < 6 or new_pw != new_pw2:
                st.error("Mật khẩu mới phải từ 6 ký tự và nhập lại phải khớp.")
            else:
                execute("UPDATE users SET password=%s WHERE id=%s", (hash_password(new_pw), user["id"]))
                st.success("Đã đổi mật khẩu.")


def admin_only():
    if not is_admin:
        st.error("Bạn không có quyền truy cập khu vực Admin.")
        st.stop()


# ============================================================
# TRANG CHỦ
# ============================================================
if page == "🏠 Trang chủ":
    html(f"""<div class="hero"><h1>Xin chào, {esc(user['full_name'])} 👋</h1>
    <p>Đặt tour trọn gói: chọn ngày giờ khởi hành, khách sạn, bữa ăn nhà hàng và phương tiện — thấy giá ngay, không phát sinh.</p></div>""")

    tours = query_df("SELECT * FROM tours WHERE status='Đang mở'")
    nxt = query_df("SELECT tour_id, MIN(depart_at) AS next_dep FROM departures WHERE depart_at>NOW() AND available_seats>0 GROUP BY tour_id")
    mine = query_df("SELECT * FROM bookings WHERE user_id=%s AND booking_status<>'Đã hủy'", (user["id"],))
    if is_admin:
        st.info("👑 Bạn đang đăng nhập với quyền quản trị. Xem số liệu tổng hợp tại mục **Dashboard Admin**.")
    else:
        unpaid = int((mine["payment_status"] == "Chưa thanh toán").sum()) if not mine.empty else 0
        up = query_df("SELECT MIN(d.depart_at) AS nd FROM bookings b JOIN departures d ON b.departure_id=d.id "
                      "WHERE b.user_id=%s AND b.booking_status<>'Đã hủy' AND d.depart_at>NOW()", (user["id"],))
        nd_txt = fdt(up["nd"][0]) if not up.empty and pd.notna(up["nd"][0]) else "Chưa có"
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 Đơn của tôi", len(mine))
        c2.metric("💳 Chờ thanh toán", unpaid)
        c3.metric("🕒 Chuyến sắp tới", nd_txt)
        c4.metric("💰 Tổng đã đặt", money(mine["total_amount"].sum()) if not mine.empty else "0 ₫")

    st.subheader("⭐ Vì sao chọn SMART TOUR?")
    a, b, c, d = st.columns(4)
    for col, ic, t, tx in [(a, "📦", "Trọn gói", "Tour + phòng ở + bữa ăn nhà hàng + xe cộ trong một lần đặt."),
                           (b, "👨‍👩‍👧", "Người lớn / Trẻ em", "Giá riêng cho người lớn và trẻ em, tự tính số phòng gợi ý."),
                           (c, "🔥", "Giá cao điểm minh bạch", "Phụ thu lễ/Tết hiển thị rõ từng đêm trước khi bạn đặt."),
                           (d, "🎯", "Gợi ý phù hợp", "Sắp xếp tour theo ngân sách, điểm đến và sở thích của bạn.")]:
        col.markdown(f'<div class="card"><h3>{ic} {t}</h3><p>{tx}</p></div>', unsafe_allow_html=True)

    seasons = query_df("SELECT * FROM price_seasons WHERE status='Đang áp dụng' AND end_date>=CURDATE() ORDER BY start_date LIMIT 4")
    if not seasons.empty:
        st.subheader("🔥 Mùa cao điểm sắp tới")
        for _, se in seasons.iterrows():
            st.markdown(f'<div class="peak">📅 <b>{se["name"]}</b> ({pd.to_datetime(se["start_date"]):%d/%m/%Y} → '
                        f'{pd.to_datetime(se["end_date"]):%d/%m/%Y}) — giá phòng <b>{float(se["surcharge_pct"]):+.0f}%</b> '
                        f'· áp dụng: {se["destination"]}</div>', unsafe_allow_html=True)

    st.subheader("🌴 Tour nổi bật")
    cols = st.columns(2)
    for i, (_, t) in enumerate(tours.head(4).iterrows()):
        n = nxt[nxt["tour_id"] == t["id"]]
        nd = fdt(n.iloc[0]["next_dep"]) if not n.empty else "Đang cập nhật"
        with cols[i % 2]:
            html(f"""<div class="recommend"><h3>🌴 {t['name']}</h3>
            <p>📍 {t['destination']} · ⏱️ {t['days']}N{t['nights']}Đ · 🕒 Khởi hành gần nhất: {nd}</p>
            <p class="price">Từ {money(t['adult_price'])}/người lớn</p><p>{s(t['description'])}</p></div>""")

# ============================================================
# TÌM & ĐẶT TOUR
# ============================================================
elif page == "🔎 Tìm & đặt tour":

    def load_catalog():
        return (query_df("SELECT * FROM tours WHERE status='Đang mở'"),
                query_df("SELECT * FROM hotels WHERE status='Đang hoạt động'"),
                query_df("SELECT * FROM meal_plans WHERE status='Đang phục vụ'"),
                query_df("SELECT * FROM transports WHERE status='Đang hoạt động'"),
                query_df("SELECT * FROM departures WHERE depart_at>NOW() AND available_seats>0"))

    def estimate(t, cat, adults, children, rooms):
        _, hotels, meals, trans, _ = cat
        h, m, tr = hotels[hotels["destination"] == t["destination"]], meals[meals["destination"] == t["destination"]], \
            trans[trans["tour_id"] == t["id"]]
        if h.empty or m.empty or tr.empty:
            return None
        return (adults * t["adult_price"] + children * t["child_price"]
                + h["price_per_room"].min() * t["nights"] * rooms
                + (adults * m["price_adult"] + children * m["price_child"]).min() * t["days"]
                + (adults * tr["price_adult"] + children * tr["price_child"]).min())

    def booking_section(tour_id):
        tdf = query_df("SELECT * FROM tours WHERE id=%s", (tour_id,))
        if tdf.empty:
            st.session_state.pop("selected_tour_id", None)
            st.rerun()
        tour = tdf.iloc[0]
        sp = st.session_state.get("search", {})
        if st.button("← Quay lại danh sách tour"):
            st.session_state.pop("selected_tour_id", None)
            st.rerun()
        st.subheader(f"📅 ĐẶT TOUR: {tour['name']}")
        st.caption(f"📍 {tour['destination']} · ⏱️ {tour['days']} ngày {tour['nights']} đêm · "
                   f"Người lớn {money(tour['adult_price'])} · Trẻ em {money(tour['child_price'])}")

        left, right = st.columns([3, 2])
        with left:
            c1, c2 = st.columns(2)
            adults = int(c1.number_input("🧑 Số người lớn", 1, 50, int(sp.get("adults", 2)), key="bk_adults"))
            children = int(c2.number_input("🧒 Số trẻ em (dưới 12 tuổi)", 0, 50, int(sp.get("children", 0)), key="bk_children"))
            guests = adults + children

            deps = query_df("SELECT * FROM departures WHERE tour_id=%s AND depart_at>NOW() AND available_seats>=%s ORDER BY depart_at",
                            (tour_id, guests))
            hotels_all = query_df("SELECT * FROM hotels WHERE destination=%s AND status='Đang hoạt động' "
                                  "ORDER BY stars DESC, price_per_room", (tour["destination"],))
            meals = query_df("SELECT * FROM meal_plans WHERE destination=%s AND status='Đang phục vụ' ORDER BY price_adult",
                             (tour["destination"],))
            trans = query_df("SELECT * FROM transports WHERE tour_id=%s AND status='Đang hoạt động' ORDER BY price_adult",
                             (tour_id,))
            if deps.empty:
                st.error("Không còn chuyến khởi hành nào đủ chỗ cho số khách này. Hãy giảm số người hoặc chọn tour khác.")
                return
            if hotels_all.empty or meals.empty or trans.empty:
                st.error("Tour này chưa cấu hình đủ khách sạn / bữa ăn / phương tiện. Vui lòng liên hệ admin.")
                return

            dmap = {int(r["id"]): r for _, r in deps.iterrows()}
            dep_id = st.selectbox("🕒 Ngày giờ khởi hành", list(dmap),
                                  format_func=lambda i: f"{fdt(dmap[i]['depart_at'])} — còn {int(dmap[i]['available_seats'])} chỗ")
            st.caption(f"📍 Điểm đón: {s(dmap[dep_id]['meeting_point'])}")

            rec = max(1, math.ceil((adults + children / 2) / 2))
            rooms = int(st.number_input("🛏️ Số phòng (gợi ý theo số khách)", 1, 20, rec, key=f"bk_rooms_{adults}_{children}"))
            hotels = hotels_all[hotels_all["available_rooms"] >= rooms]
            if hotels.empty:
                st.error("Không có khách sạn nào đủ số phòng bạn chọn.")
                return
            hmap = {int(r["id"]): r for _, r in hotels.iterrows()}
            hotel_id = st.selectbox("🏨 Khách sạn / phòng ở", list(hmap),
                                    format_func=lambda i: f"{hmap[i]['name']} · {'⭐' * int(hmap[i]['stars'])} · "
                                                          f"{hmap[i]['room_type']} · {money(hmap[i]['price_per_room'])}/đêm")
            mmap = {int(r["id"]): r for _, r in meals.iterrows()}
            meal_id = st.selectbox("🍽️ Bữa ăn nhà hàng", list(mmap),
                                   format_func=lambda i: f"{mmap[i]['restaurant']} · {mmap[i]['plan_name']} · "
                                                         f"NL {money(mmap[i]['price_adult'])} / TE {money(mmap[i]['price_child'])} mỗi ngày")
            tmap = {int(r["id"]): r for _, r in trans.iterrows()}
            trans_id = st.selectbox("🚐 Phương tiện di chuyển", list(tmap),
                                    format_func=lambda i: f"{tmap[i]['name']} · NL {money(tmap[i]['price_adult'])} / TE {money(tmap[i]['price_child'])}")

        q = make_quote(tour, dmap[dep_id]["depart_at"], hmap[hotel_id], mmap[meal_id], tmap[trans_id], adults, children, rooms)
        with right:
            peak_row = (f'<div class="row"><span>↳ gồm phụ thu cao điểm</span><span>{money(q["peak"])}</span></div>'
                        if q["peak"] else "")
            html(f"""<div class="ticket"><b>💰 BÁO GIÁ TRỰC TIẾP</b>
            <div class="row"><span>🌴 Tour ({adults} NL + {children} TE)</span><span>{money(q['tour'])}</span></div>
            <div class="row"><span>🏨 Phòng ({rooms} phòng × {tour['nights']} đêm)</span><span>{money(q['room'])}</span></div>
            {peak_row}
            <div class="row"><span>🍽️ Bữa ăn ({tour['days']} ngày)</span><span>{money(q['meal'])}</span></div>
            <div class="row"><span>🚐 Xe cộ / di chuyển</span><span>{money(q['trans'])}</span></div>
            <div class="row total"><span>TỔNG</span><span>{money(q['total'])}</span></div>
            <p class="small">≈ {money(q['total'] / guests)}/khách</p></div>""")
            for p in q["peaks"]:
                st.markdown(f'<div class="peak">🔥 {p}</div>', unsafe_allow_html=True)
            budget = float(sp.get("budget", 0) or 0)
            if budget:
                if q["total"] > budget:
                    st.warning(f"⚠️ Vượt ngân sách {money(q['total'] - budget)}. Thử khách sạn/phương tiện rẻ hơn hoặc đổi ngày khởi hành.")
                else:
                    st.success(f"✅ Trong ngân sách, còn dư {money(budget - q['total'])}.")

        method = st.selectbox("💳 Phương thức thanh toán", ["Chuyển khoản ngân hàng", "Ví điện tử", "Thanh toán tại văn phòng"])
        note = st.text_area("📝 Ghi chú / yêu cầu đặc biệt", placeholder="VD: phòng tầng thấp, ăn chay, trẻ em cần ghế ngồi...")
        if st.button("🚀 XÁC NHẬN ĐẶT TOUR", type="primary", **STRETCH):
            bid, err = None, None
            try:
                bid = create_booking(int(user["id"]), int(tour_id), dep_id, hotel_id, meal_id, trans_id,
                                     adults, children, rooms, q, method, note.strip())
            except ValueError as e:
                err = str(e)
            except Exception as e:
                err = f"Lỗi hệ thống: {e}"
            if err:
                st.error(err)
            else:
                st.session_state["done_booking"] = bid
                st.session_state.pop("selected_tour_id", None)
                st.rerun()

    st.title("🔎 TÌM & ĐẶT TOUR TRỌN GÓI")

    if "done_booking" in st.session_state:
        st.balloons()
        st.success("🎉 Đặt tour thành công! Vui lòng thanh toán ở mục **💳 Thanh toán** để được xác nhận.")
        det = query_df(BOOKING_SQL + " WHERE b.id=%s AND b.user_id=%s", (st.session_state["done_booking"], user["id"]))
        if not det.empty:
            render_ticket(det.iloc[0])
        if st.button("➕ Đặt tour khác"):
            st.session_state.pop("done_booking", None)
            st.rerun()

    elif "selected_tour_id" in st.session_state:
        booking_section(st.session_state["selected_tour_id"])

    else:
        st.write("Cho hệ thống biết nhu cầu, chúng tôi chấm điểm và tính sẵn **giá trọn gói** (tour + phòng + ăn + xe) thấp nhất.")
        with st.form("smart_search"):
            c1, c2, c3, c4 = st.columns(4)
            dests = ["Tất cả"] + query_df("SELECT DISTINCT destination FROM tours WHERE status='Đang mở'")["destination"].tolist()
            destination = c1.selectbox("📍 Điểm đến", dests)
            adults = c2.number_input("🧑 Người lớn", 1, 50, 2)
            children = c3.number_input("🧒 Trẻ em", 0, 50, 0)
            budget = c4.number_input("💰 Ngân sách tổng (₫)", 1000000, value=10000000, step=500000)
            interests = st.multiselect("❤️ Bạn thích gì?",
                                       ["biển", "ăn uống", "nghỉ dưỡng", "chụp ảnh", "cafe", "thiên nhiên", "gia đình",
                                        "giải trí", "văn hóa", "khám phá", "hải sản"], default=["biển", "ăn uống"])
            go = st.form_submit_button("🔍 TÌM PHƯƠNG ÁN PHÙ HỢP", **STRETCH)
        if go:
            st.session_state["search"] = dict(destination=destination, adults=int(adults), children=int(children),
                                              budget=float(budget), interests=interests)

        sp = st.session_state.get("search")
        if sp:
            cat = load_catalog()
            tours_df, deps_df = cat[0], cat[4]
            guests = sp["adults"] + sp["children"]
            rooms = max(1, math.ceil((sp["adults"] + sp["children"] / 2) / 2))
            results = []
            for _, t in tours_df.iterrows():
                d = deps_df[(deps_df["tour_id"] == t["id"]) & (deps_df["available_seats"] >= guests)]
                est = estimate(t, cat, sp["adults"], sp["children"], rooms)
                if d.empty or est is None:
                    continue
                score = 0
                if sp["destination"] == "Tất cả" or sp["destination"].lower() in t["destination"].lower():
                    score += 30
                score += sum(15 for i in sp["interests"] if i.lower() in s(t["interests"]).lower())
                score += 30 if est <= sp["budget"] else (10 if est <= sp["budget"] * 1.15 else 0)
                score += 10
                results.append((score, est, t, d["depart_at"].min()))
            results.sort(key=lambda x: (-x[0], x[1]))

            st.markdown("---")
            if not results:
                st.warning("Không có tour nào còn đủ chỗ / đủ dịch vụ cho nhu cầu này.")
            else:
                score, est, best, _ = results[0]
                html(f"""<div class="hero"><h2>💡 Phương án đề xuất tốt nhất</h2><h1>{best['name']}</h1>
                <p>📍 {best['destination']} · 👥 {sp['adults']} NL + {sp['children']} TE · 🛏️ ~{rooms} phòng</p>
                <p>💰 Giá trọn gói từ: <b>{money(est)}</b></p></div>""")
                if est > sp["budget"]:
                    st.error(f"⚠️ Vượt ngân sách khoảng {money(est - sp['budget'])} (chưa tính phụ thu cao điểm).")
                else:
                    st.success(f"✅ Trong ngân sách, còn dư khoảng {money(sp['budget'] - est)}.")
                st.subheader("📋 Các phương án")
                for score, est, t, nd in results[:6]:
                    ok = "✅ Trong ngân sách" if est <= sp["budget"] else "⚠️ Vượt ngân sách"
                    html(f"""<div class="recommend"><h3>🌴 {t['name']}</h3>
                    <p>📍 {t['destination']} · ⏱️ {t['days']}N{t['nights']}Đ · 🕒 Chuyến gần nhất: {fdt(nd)}</p>
                    <p>📦 Trọn gói (phòng + ăn + xe rẻ nhất): <span class="price">{money(est)}</span></p>
                    <p>⭐ Điểm phù hợp: <b>{score}</b> · {ok}</p><p>{s(t['description'])}</p></div>""")
                    if st.button(f"📅 Chọn & tùy chỉnh: {t['name']}", key=f"choose_{int(t['id'])}"):
                        for _k in [k for k in st.session_state if str(k).startswith("bk_")]:
                            st.session_state.pop(_k, None)
                        st.session_state["selected_tour_id"] = int(t["id"])
                        st.rerun()

# ============================================================
# TOUR CỦA TÔI
# ============================================================
elif page == "📋 Tour của tôi":
    st.title("📋 TOUR CỦA TÔI")
    bks = query_df(BOOKING_SQL + " WHERE b.user_id=%s ORDER BY b.id DESC", (user["id"],))
    if bks.empty:
        st.info("Bạn chưa có đơn đặt tour nào.")
    for _, b in bks.iterrows():
        with st.expander(f"#{int(b['id'])} — {b['tour_name']} — {fdt(b['depart_at'])} — {b['booking_status']}"):
            render_ticket(b)
            if b["booking_status"] == "Chờ xác nhận" and b["payment_status"] == "Chưa thanh toán":
                if st.button("❌ Hủy đơn này", key=f"cancel_{int(b['id'])}"):
                    cancel_booking(int(b["id"]))
                    st.success("Đã hủy đơn, chỗ và phòng đã được trả lại.")
                    st.rerun()

# ============================================================
# THANH TOÁN
# ============================================================
elif page == "💳 Thanh toán":
    st.title("💳 THANH TOÁN")
    bks = query_df(BOOKING_SQL + " WHERE b.user_id=%s AND b.payment_status='Chưa thanh toán' AND b.booking_status<>'Đã hủy' "
                                 "ORDER BY b.id DESC", (user["id"],))
    if bks.empty:
        st.success("🎉 Không có đơn nào đang chờ thanh toán.")
    else:
        opts = {f"Đơn #{int(r['id'])} - {r['tour_name']} - {money(r['total_amount'])}": int(r["id"]) for _, r in bks.iterrows()}
        pick = st.selectbox("Chọn đơn cần thanh toán", list(opts))
        b = bks[bks["id"] == opts[pick]].iloc[0]
        render_ticket(b)
        method = st.radio("Phương thức thanh toán", ["Chuyển khoản ngân hàng", "Ví điện tử", "Thanh toán tại văn phòng"])
        if method == "Chuyển khoản ngân hàng":
            st.info(f"🏦 Ngân hàng: **SMART BANK** · STK: **0123 456 789** · Chủ TK: **CTY SMART TOUR**\n\n"
                    f"Số tiền: **{money(b['total_amount'])}** · Nội dung: **ST{int(b['id'])} {b['phone']}**")
        elif method == "Ví điện tử":
            st.info(f"📱 Chuyển vào ví **0901 234 567** · Nội dung: **ST{int(b['id'])}**")
        else:
            st.info("🏢 Vui lòng đến văn phòng SMART TOUR trước ngày khởi hành để thanh toán.")
        if st.button("💳 XÁC NHẬN THANH TOÁN", type="primary", **STRETCH):
            rows = execute_rc("UPDATE bookings SET payment_status='Đã thanh toán', booking_status='Đã xác nhận', "
                              "payment_method=%s WHERE id=%s AND user_id=%s AND payment_status='Chưa thanh toán' "
                              "AND booking_status<>'Đã hủy'", (method, int(b["id"]), int(user["id"])))
            if rows:
                execute("INSERT INTO payments (booking_id, amount, method) VALUES (%s,%s,%s)",
                        (int(b["id"]), float(b["total_amount"]), method))
                st.success("✅ Thanh toán thành công! Đơn của bạn đã được xác nhận.")
                st.rerun()
            else:
                st.error("Đơn này đã được thanh toán hoặc đã bị hủy.")

# ============================================================
# ADMIN - QUẢN LÝ TOUR
# ============================================================
elif page == "🔧 Quản lý tour":
    admin_only()
    st.title("🔧 QUẢN LÝ TOUR")
    st.caption("Sửa trực tiếp trong bảng, thêm dòng mới ở hàng cuối, chọn dòng + phím Delete để xóa, rồi bấm **Lưu thay đổi**.")
    t1, t2, t3 = st.tabs(["🌴 Tour", "🕒 Lịch khởi hành", "🚐 Phương tiện"])
    with t1:
        table_editor("tours", ["id", "name", "destination", "days", "nights", "adult_price", "child_price",
                               "interests", "description", "status"], "tours", {
            "name": "Tên tour", "destination": "Điểm đến", "days": "Số ngày", "nights": "Số đêm",
            "adult_price": st.column_config.NumberColumn("Giá người lớn", format="%d"),
            "child_price": st.column_config.NumberColumn("Giá trẻ em", format="%d"),
            "interests": "Sở thích (cách nhau dấu phẩy)", "description": "Mô tả",
            "status": st.column_config.SelectboxColumn("Trạng thái", options=["Đang mở", "Tạm dừng", "Đã đóng"])})
    with t2:
        st.caption("tour_id = ID của tour ở tab bên cạnh.")
        table_editor("departures", ["id", "tour_id", "depart_at", "total_seats", "available_seats", "meeting_point"], "deps", {
            "depart_at": st.column_config.DatetimeColumn("Ngày giờ khởi hành", format="DD/MM/YYYY HH:mm"),
            "total_seats": "Tổng chỗ", "available_seats": "Chỗ còn", "meeting_point": "Điểm đón"})
    with t3:
        table_editor("transports", ["id", "tour_id", "name", "vehicle_type", "price_adult", "price_child", "status"], "trans", {
            "name": "Tên phương tiện", "vehicle_type": "Loại",
            "price_adult": st.column_config.NumberColumn("Giá người lớn", format="%d"),
            "price_child": st.column_config.NumberColumn("Giá trẻ em", format="%d"),
            "status": st.column_config.SelectboxColumn("Trạng thái", options=["Đang hoạt động", "Tạm dừng"])})

# ============================================================
# ADMIN - KHÁCH SẠN & GIÁ CAO ĐIỂM
# ============================================================
elif page == "🏨 Khách sạn & giá cao điểm":
    admin_only()
    st.title("🏨 KHÁCH SẠN & GIÁ CAO ĐIỂM")
    t1, t2 = st.tabs(["🏨 Khách sạn", "🔥 Mùa cao điểm (phụ thu giá phòng)"])
    with t1:
        table_editor("hotels", ["id", "name", "destination", "stars", "room_type", "price_per_room", "total_rooms",
                                "available_rooms", "description", "status"], "hotels", {
            "name": "Khách sạn", "destination": "Điểm đến", "stars": "Sao", "room_type": "Loại phòng",
            "price_per_room": st.column_config.NumberColumn("Giá phòng/đêm (giá gốc)", format="%d"),
            "total_rooms": "Tổng phòng", "available_rooms": "Phòng còn", "description": "Mô tả",
            "status": st.column_config.SelectboxColumn("Trạng thái", options=["Đang hoạt động", "Tạm dừng"])})
    with t2:
        st.info("Đặt khoảng ngày cao điểm và % phụ thu. Giá phòng của **từng đêm** rơi vào khoảng này sẽ tự tăng "
                "(nhập số âm nếu muốn giảm giá mùa thấp). Điểm đến = 'Tất cả' hoặc đúng tên điểm đến. "
                "Nếu trùng nhiều mùa, hệ thống lấy mức cao nhất.")
        table_editor("price_seasons", ["id", "name", "destination", "start_date", "end_date", "surcharge_pct", "status"],
                     "seasons", {
            "name": "Tên mùa / dịp lễ", "destination": "Điểm đến (hoặc 'Tất cả')",
            "start_date": st.column_config.DateColumn("Từ ngày", format="DD/MM/YYYY"),
            "end_date": st.column_config.DateColumn("Đến ngày", format="DD/MM/YYYY"),
            "surcharge_pct": st.column_config.NumberColumn("Phụ thu (%)", format="%.0f"),
            "status": st.column_config.SelectboxColumn("Trạng thái", options=["Đang áp dụng", "Tạm dừng"])})

# ============================================================
# ADMIN - NHÀ HÀNG & BỮA ĂN
# ============================================================
elif page == "🍽️ Nhà hàng & bữa ăn":
    admin_only()
    st.title("🍽️ NHÀ HÀNG & GÓI BỮA ĂN")
    st.caption("Giá tính theo mỗi ngày của tour (số ngày × giá gói).")
    table_editor("meal_plans", ["id", "destination", "restaurant", "plan_name", "meals_per_day", "price_adult",
                                "price_child", "description", "status"], "meals", {
        "destination": "Điểm đến", "restaurant": "Nhà hàng", "plan_name": "Tên gói", "meals_per_day": "Số bữa/ngày",
        "price_adult": st.column_config.NumberColumn("Giá người lớn/ngày", format="%d"),
        "price_child": st.column_config.NumberColumn("Giá trẻ em/ngày", format="%d"),
        "description": "Mô tả",
        "status": st.column_config.SelectboxColumn("Trạng thái", options=["Đang phục vụ", "Tạm dừng"])})

# ============================================================
# ADMIN - KHÁCH HÀNG
# ============================================================
elif page == "👥 Quản lý khách hàng":
    admin_only()
    st.title("👥 QUẢN LÝ KHÁCH HÀNG")
    users = query_df("""SELECT u.id, u.full_name, u.phone, u.created_at, COUNT(b.id) AS so_don,
                        COALESCE(SUM(CASE WHEN b.booking_status<>'Đã hủy' THEN b.total_amount END),0) AS tong_tien
                        FROM users u LEFT JOIN bookings b ON b.user_id=u.id
                        WHERE u.role='customer' GROUP BY u.id ORDER BY u.id DESC""")
    kw = st.text_input("🔍 Tìm theo tên hoặc số điện thoại")
    if kw:
        users = users[users["full_name"].str.contains(kw, case=False) | users["phone"].str.contains(kw)]
    if users.empty:
        st.info("Chưa có khách hàng.")
    else:
        st.dataframe(users.rename(columns={"id": "ID", "full_name": "Họ tên", "phone": "Điện thoại",
                                           "created_at": "Ngày đăng ký", "so_don": "Số đơn", "tong_tien": "Tổng chi tiêu"}),
                     **STRETCH, hide_index=True)

# ============================================================
# ADMIN - ĐƠN ĐẶT
# ============================================================
elif page == "🧾 Quản lý đơn đặt":
    admin_only()
    st.title("🧾 QUẢN LÝ ĐƠN ĐẶT TOUR")
    allb = query_df(BOOKING_SQL + " ORDER BY b.id DESC")
    if allb.empty:
        st.info("Chưa có đơn đặt tour.")
    else:
        flt = st.selectbox("Lọc theo trạng thái", ["Tất cả", "Chờ xác nhận", "Đã xác nhận", "Đã hoàn thành", "Đã hủy"])
        view = allb if flt == "Tất cả" else allb[allb["booking_status"] == flt]
        st.dataframe(view[["id", "full_name", "phone", "tour_name", "depart_at", "adults", "children", "rooms",
                           "total_amount", "payment_status", "booking_status"]].rename(columns={
            "id": "ID", "full_name": "Khách hàng", "phone": "SĐT", "tour_name": "Tour", "depart_at": "Khởi hành",
            "adults": "Người lớn", "children": "Trẻ em", "rooms": "Phòng", "total_amount": "Tổng tiền",
            "payment_status": "Thanh toán", "booking_status": "Đơn hàng"}), **STRETCH, hide_index=True)
        st.markdown("---")
        if not view.empty:
            bid = st.selectbox("Chọn ID đơn để xử lý", view["id"].tolist())
            b = allb[allb["id"] == bid].iloc[0]
            render_ticket(b)
            STS = ["Chờ xác nhận", "Đã xác nhận", "Đã hoàn thành", "Đã hủy"]
            new = st.selectbox("Trạng thái đơn", STS, index=STS.index(b["booking_status"]))
            if st.button("💾 Cập nhật trạng thái", **STRETCH):
                if b["booking_status"] == "Đã hủy" and new != "Đã hủy":
                    st.error("Đơn đã hủy không thể mở lại.")
                    st.stop()
                if new == "Đã hủy":
                    cancel_booking(int(bid))
                else:
                    execute("UPDATE bookings SET booking_status=%s WHERE id=%s", (new, int(bid)))
                st.success("Đã cập nhật đơn.")
                st.rerun()

# ============================================================
# ADMIN - DASHBOARD
# ============================================================
elif page == "📊 Dashboard Admin":
    admin_only()
    st.title("📊 DASHBOARD QUẢN TRỊ SMART TOUR")
    n_users = int(query_df("SELECT COUNT(*) n FROM users WHERE role='customer'")["n"][0])
    bk = query_df("SELECT * FROM bookings")
    pay = query_df("SELECT * FROM payments WHERE status='Thành công'")
    revenue = pay["amount"].sum() if not pay.empty else 0
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("👥 Khách hàng", n_users)
    c2.metric("🌍 Số tour", int(query_df("SELECT COUNT(*) n FROM tours")["n"][0]))
    c3.metric("🧾 Đơn đặt", len(bk))
    c4.metric("✅ Đơn đã xác nhận", len(bk[bk["booking_status"].isin(["Đã xác nhận", "Đã hoàn thành"])]) if not bk.empty else 0)
    c5.metric("💰 Doanh thu", money(revenue))
    st.markdown("---")
    l, r = st.columns(2)
    with l:
        st.subheader("📈 Đơn theo trạng thái")
        if not bk.empty:
            st.bar_chart(bk["booking_status"].value_counts())
    with r:
        st.subheader("💳 Doanh thu theo phương thức")
        if not pay.empty:
            st.bar_chart(pay.groupby("method")["amount"].sum())
    l2, r2 = st.columns(2)
    with l2:
        st.subheader("🌏 Doanh thu theo điểm đến")
        rv = query_df("""SELECT t.destination, SUM(b.total_amount) AS doanh_thu FROM bookings b JOIN tours t ON b.tour_id=t.id
                         WHERE b.payment_status='Đã thanh toán' GROUP BY t.destination""")
        if not rv.empty:
            st.bar_chart(rv.set_index("destination"))
    with r2:
        st.subheader("🔥 Phụ thu cao điểm đã thu")
        pk = query_df("SELECT COALESCE(SUM(peak_surcharge),0) AS v FROM bookings WHERE booking_status<>'Đã hủy'")["v"][0]
        st.metric("Tổng phụ thu mùa cao điểm", money(pk))
    st.subheader("🏆 Tour được đặt nhiều")
    pop = query_df("""SELECT t.name AS Tour, t.destination AS `Điểm đến`, COUNT(b.id) AS `Số lượt đặt`,
                      SUM(b.adults) AS `Người lớn`, SUM(b.children) AS `Trẻ em`
                      FROM bookings b JOIN tours t ON b.tour_id=t.id WHERE b.booking_status<>'Đã hủy'
                      GROUP BY t.id ORDER BY COUNT(b.id) DESC""")
    if pop.empty:
        st.info("Chưa có dữ liệu.")
    else:
        st.dataframe(pop, **STRETCH, hide_index=True)
    st.subheader("🕒 Mức lấp đầy chuyến sắp khởi hành")
    fill = query_df("""SELECT t.name AS Tour, d.depart_at AS `Khởi hành`, d.total_seats AS `Tổng chỗ`,
                       d.total_seats-d.available_seats AS `Đã đặt`,
                       ROUND((d.total_seats-d.available_seats)*100/d.total_seats) AS `Lấp đầy (%)`
                       FROM departures d JOIN tours t ON d.tour_id=t.id WHERE d.depart_at>NOW()
                       ORDER BY d.depart_at LIMIT 15""")
    st.dataframe(fill, **STRETCH, hide_index=True)

