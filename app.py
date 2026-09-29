import streamlit as st
import mysql.connector
from mysql.connector import Error, IntegrityError
from datetime import datetime, date
import pandas as pd

# ============================================================
# CẤU HÌNH ỨNG DỤNG
# ============================================================

st.set_page_config(
    page_title="Hotel Manager",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Hình ảnh tùy chọn: nếu có VT.jpg trong cùng thư mục sẽ hiển thị.
import os
if os.path.exists("VT.jpg"):
    st.image("VT.jpg", use_container_width=True)

# ============================================================
# MYSQL AIVEN
# ============================================================
DB_CONFIG = {
    "host": "mysql-1b346c1b-kimchi8019-4ea9.e.aivencloud.com",
    "port": 21314,
    "user": "avnadmin",
    "password": "AVNS_ZuLUVTHk6cKBskjg0Kp",
    "database": "smart_tour",
    "connection_timeout": 15,
    "autocommit": False,
}
DB_NAME = "smart_tour"


# ============================================================
# KẾT NỐI DATABASE MYSQL AIVEN
# ============================================================

def get_server_connection():
    config = DB_CONFIG.copy()
    config.pop("database", None)
    return mysql.connector.connect(**config)


def create_database_if_not_exists():
    server_conn = None
    cursor = None
    try:
        server_conn = get_server_connection()
        cursor = server_conn.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        server_conn.commit()
        return True
    except Error as e:
        st.error("Không thể tạo/kiểm tra database MySQL Aiven.")
        st.error(str(e))
        return False
    finally:
        if cursor:
            cursor.close()
        if server_conn and server_conn.is_connected():
            server_conn.close()


def get_connection():
    config = DB_CONFIG.copy()
    return mysql.connector.connect(**config)


# Tạo database trước khi kết nối vào database.
if not create_database_if_not_exists():
    st.stop()

conn = get_connection()


# ============================================================
# KHỞI TẠO DATABASE
# ============================================================

def init_database():
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room_number VARCHAR(20) UNIQUE NOT NULL,
            room_type VARCHAR(100) NOT NULL,
            price DECIMAL(15,2) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'Trống',
            note VARCHAR(500) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(150) NOT NULL,
            phone VARCHAR(30),
            id_number VARCHAR(50),
            address VARCHAR(255),
            created_at DATETIME NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room_id INT NOT NULL,
            guest_id INT NOT NULL,
            check_in DATE NOT NULL,
            check_out DATE,
            adults INT DEFAULT 1,
            children INT DEFAULT 0,
            total_amount DECIMAL(15,2) DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'Đang ở',
            note VARCHAR(500) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_booking_room
                FOREIGN KEY(room_id) REFERENCES rooms(id)
                ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT fk_booking_guest
                FOREIGN KEY(guest_id) REFERENCES guests(id)
                ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    conn.commit()


init_database()



def ensure_connection():
    global conn
    try:
        if conn is None or not conn.is_connected():
            conn = get_connection()
        else:
            conn.ping(reconnect=True, attempts=3, delay=1)
    except Exception:
        conn = get_connection()
    return conn


# ============================================================
# HÀM HỖ TRỢ
# ============================================================

def format_money(amount):
    return f"{amount:,.0f} VNĐ"


def get_rooms():
    ensure_connection()
    ensure_connection()
    return pd.read_sql_query(
        "SELECT * FROM rooms ORDER BY room_number",
        conn
    )


def get_guests():
    ensure_connection()
    ensure_connection()
    return pd.read_sql_query(
        "SELECT * FROM guests ORDER BY id DESC",
        conn
    )


def get_bookings():
    ensure_connection()
    query = """
        SELECT
            bookings.id,
            rooms.room_number,
            rooms.room_type,
            rooms.price,
            guests.full_name,
            guests.phone,
            guests.id_number,
            bookings.check_in,
            bookings.check_out,
            bookings.adults,
            bookings.children,
            bookings.total_amount,
            bookings.status,
            bookings.note
        FROM bookings
        JOIN rooms ON bookings.room_id = rooms.id
        JOIN guests ON bookings.guest_id = guests.id
        ORDER BY bookings.id DESC
    """

    return pd.read_sql_query(query, conn)


def seed_rooms():
    ensure_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM rooms")
    count = cursor.fetchone()[0]

    if count == 0:
        sample_rooms = [
            ("101", "Phòng đơn", 350000, "Trống", ""),
            ("102", "Phòng đơn", 350000, "Trống", ""),
            ("103", "Phòng đôi", 500000, "Trống", ""),
            ("104", "Phòng đôi", 500000, "Trống", ""),
            ("201", "Phòng VIP", 800000, "Trống", ""),
            ("202", "Phòng VIP", 800000, "Trống", ""),
            ("203", "Phòng gia đình", 1000000, "Trống", ""),
            ("204", "Phòng gia đình", 1000000, "Trống", ""),
        ]

        cursor.executemany("""
            INSERT INTO rooms
            (room_number, room_type, price, status, note)
            VALUES (%s, %s, %s, %s, %s)
        """, sample_rooms)

        conn.commit()


seed_rooms()


def calculate_total(price, check_in, check_out):
    if isinstance(check_in, date):
        start = check_in
    else:
        start = datetime.strptime(check_in, "%Y-%m-%d").date()

    if isinstance(check_out, date):
        end = check_out
    else:
        end = datetime.strptime(check_out, "%Y-%m-%d").date()

    nights = (end - start).days

    if nights <= 0:
        nights = 1

    return price * nights, nights


# ============================================================
# CSS
# ============================================================

st.markdown("""
<style>

.main {
    background-color: #f5f7fa;
}

.block-container {
    padding-top: 1.5rem;
}

h1 {
    color: #17365d;
}

h2 {
    color: #244a73;
}

h3 {
    color: #345d8c;
}

[data-testid="stMetric"] {
    background-color: white;
    border-radius: 12px;
    padding: 15px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.room-card {
    background: white;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 15px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.available {
    color: #16803c;
    font-weight: bold;
}

.occupied {
    color: #d93025;
    font-weight: bold;
}

.cleaning {
    color: #f29900;
    font-weight: bold;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🏨 HOTEL MANAGER")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "📋 MENU",
    [
        "📊 Dashboard",
        "🛏️ Quản lý phòng",
        "👤 Quản lý khách",
        "📝 Check-in",
        "🚪 Check-out",
        "📅 Đặt phòng",
        "📈 Báo cáo"
    ]
)

st.sidebar.markdown("---")
st.sidebar.success("🟢 MySQL Aiven: Đã kết nối")
st.sidebar.info(
    "Ứng dụng quản lý phòng khách sạn\n\n"
    "• Streamlit\n"
    "• MySQL Aiven\n"
    "• Python"
)


# ============================================================
# DASHBOARD
# ============================================================

if menu == "📊 Dashboard":

    st.title("🏨 HỆ THỐNG QUẢN LÝ KHÁCH SẠN")

    st.write(
        "Quản lý phòng, khách lưu trú, check-in, check-out và doanh thu."
    )

    rooms = get_rooms()
    bookings = get_bookings()
    guests = get_guests()

    total_rooms = len(rooms)

    available_rooms = len(
        rooms[rooms["status"] == "Trống"]
    )

    occupied_rooms = len(
        rooms[rooms["status"] == "Đang ở"]
    )

    cleaning_rooms = len(
        rooms[rooms["status"] == "Đang dọn"]
    )

    total_revenue = bookings[
        bookings["status"] == "Đã trả phòng"
    ]["total_amount"].sum()

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("🏨 Tổng phòng", total_rooms)
    col2.metric("🟢 Phòng trống", available_rooms)
    col3.metric("🔴 Đang ở", occupied_rooms)
    col4.metric("🟠 Đang dọn", cleaning_rooms)
    col5.metric("💰 Doanh thu", format_money(total_revenue))

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:

        st.subheader("📊 Tình trạng phòng")

        if total_rooms > 0:

            status_data = rooms["status"].value_counts()

            st.bar_chart(status_data)

    with col_right:

        st.subheader("🏨 Danh sách phòng")

        if len(rooms) > 0:

            display_rooms = rooms[
                [
                    "room_number",
                    "room_type",
                    "price",
                    "status"
                ]
            ].copy()

            display_rooms.columns = [
                "Số phòng",
                "Loại phòng",
                "Giá/đêm",
                "Trạng thái"
            ]

            display_rooms["Giá/đêm"] = display_rooms[
                "Giá/đêm"
            ].apply(format_money)

            st.dataframe(
                display_rooms,
                use_container_width=True,
                hide_index=True
            )

    st.markdown("---")

    st.subheader("🕒 Các lượt đặt phòng gần đây")

    recent = bookings.head(10)

    if len(recent) > 0:

        recent_display = recent[
            [
                "room_number",
                "full_name",
                "check_in",
                "check_out",
                "status",
                "total_amount"
            ]
        ].copy()

        recent_display.columns = [
            "Phòng",
            "Khách",
            "Check-in",
            "Check-out",
            "Trạng thái",
            "Tổng tiền"
        ]

        recent_display["Tổng tiền"] = recent_display[
            "Tổng tiền"
        ].apply(format_money)

        st.dataframe(
            recent_display,
            use_container_width=True,
            hide_index=True
        )

    else:
        st.info("Chưa có dữ liệu đặt phòng.")


# ============================================================
# QUẢN LÝ PHÒNG
# ============================================================

elif menu == "🛏️ Quản lý phòng":

    st.title("🛏️ QUẢN LÝ PHÒNG")

    tab1, tab2, tab3 = st.tabs(
        [
            "📋 Danh sách phòng",
            "➕ Thêm phòng",
            "✏️ Cập nhật phòng"
        ]
    )

    # --------------------------------------------------------
    # DANH SÁCH PHÒNG
    # --------------------------------------------------------

    with tab1:

        rooms = get_rooms()

        col1, col2 = st.columns(2)

        with col1:
            status_filter = st.selectbox(
                "Lọc theo trạng thái",
                [
                    "Tất cả",
                    "Trống",
                    "Đang ở",
                    "Đang dọn",
                    "Bảo trì"
                ]
            )

        with col2:
            search = st.text_input(
                "🔍 Tìm phòng",
                placeholder="Nhập số phòng..."
            )

        filtered = rooms.copy()

        if status_filter != "Tất cả":
            filtered = filtered[
                filtered["status"] == status_filter
            ]

        if search:
            filtered = filtered[
                filtered["room_number"]
                .astype(str)
                .str.contains(search, case=False)
            ]

        st.write(
            f"Hiển thị **{len(filtered)}** phòng"
        )

        display = filtered[
            [
                "room_number",
                "room_type",
                "price",
                "status",
                "note"
            ]
        ].copy()

        display.columns = [
            "Số phòng",
            "Loại phòng",
            "Giá/đêm",
            "Trạng thái",
            "Ghi chú"
        ]

        display["Giá/đêm"] = display[
            "Giá/đêm"
        ].apply(format_money)

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True
        )

    # --------------------------------------------------------
    # THÊM PHÒNG
    # --------------------------------------------------------

    with tab2:

        st.subheader("➕ Thêm phòng mới")

        with st.form("add_room_form"):

            col1, col2 = st.columns(2)

            with col1:

                room_number = st.text_input(
                    "Số phòng *",
                    placeholder="Ví dụ: 305"
                )

                room_type = st.selectbox(
                    "Loại phòng",
                    [
                        "Phòng đơn",
                        "Phòng đôi",
                        "Phòng VIP",
                        "Phòng gia đình"
                    ]
                )

            with col2:

                price = st.number_input(
                    "Giá phòng/đêm (VNĐ)",
                    min_value=0,
                    value=500000,
                    step=50000
                )

                note = st.text_area(
                    "Ghi chú"
                )

            submit = st.form_submit_button(
                "➕ Thêm phòng",
                use_container_width=True
            )

            if submit:

                if not room_number.strip():

                    st.error("Vui lòng nhập số phòng.")

                else:

                    try:

                        cursor = conn.cursor()

                        cursor.execute("""
                            INSERT INTO rooms
                            (room_number, room_type, price, status, note)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            room_number.strip(),
                            room_type,
                            price,
                            "Trống",
                            note
                        ))

                        conn.commit()

                        st.success(
                            f"Đã thêm phòng {room_number}."
                        )

                        st.rerun()

                    except IntegrityError:

                        st.error(
                            "Số phòng này đã tồn tại."
                        )

    # --------------------------------------------------------
    # CẬP NHẬT PHÒNG
    # --------------------------------------------------------

    with tab3:

        rooms = get_rooms()

        if len(rooms) == 0:

            st.info("Chưa có phòng.")

        else:

            room_options = {
                f"{row['room_number']} - {row['room_type']}":
                row["id"]
                for _, row in rooms.iterrows()
            }

            selected_room = st.selectbox(
                "Chọn phòng",
                list(room_options.keys())
            )

            room_id = room_options[selected_room]

            room = rooms[
                rooms["id"] == room_id
            ].iloc[0]

            with st.form("update_room_form"):

                col1, col2 = st.columns(2)

                with col1:

                    new_type = st.selectbox(
                        "Loại phòng",
                        [
                            "Phòng đơn",
                            "Phòng đôi",
                            "Phòng VIP",
                            "Phòng gia đình"
                        ],
                        index=[
                            "Phòng đơn",
                            "Phòng đôi",
                            "Phòng VIP",
                            "Phòng gia đình"
                        ].index(room["room_type"])
                    )

                    new_price = st.number_input(
                        "Giá/đêm",
                        min_value=0,
                        value=int(room["price"]),
                        step=50000
                    )

                with col2:

                    new_status = st.selectbox(
                        "Trạng thái",
                        [
                            "Trống",
                            "Đang ở",
                            "Đang dọn",
                            "Bảo trì"
                        ],
                        index=[
                            "Trống",
                            "Đang ở",
                            "Đang dọn",
                            "Bảo trì"
                        ].index(room["status"])
                    )

                    new_note = st.text_area(
                        "Ghi chú",
                        value=room["note"] or ""
                    )

                update = st.form_submit_button(
                    "💾 Lưu thay đổi",
                    use_container_width=True
                )

                if update:

                    cursor = conn.cursor()

                    cursor.execute("""
                        UPDATE rooms
                        SET room_type = %s,
                            price = %s,
                            status = %s,
                            note = %s
                        WHERE id = %s
                    """, (
                        new_type,
                        new_price,
                        new_status,
                        new_note,
                        room_id
                    ))

                    conn.commit()

                    st.success(
                        "Đã cập nhật phòng."
                    )

                    st.rerun()


# ============================================================
# QUẢN LÝ KHÁCH
# ============================================================

elif menu == "👤 Quản lý khách":

    st.title("👤 QUẢN LÝ KHÁCH HÀNG")

    tab1, tab2 = st.tabs(
        [
            "📋 Danh sách khách",
            "➕ Thêm khách"
        ]
    )

    with tab1:

        guests = get_guests()

        search = st.text_input(
            "🔍 Tìm kiếm khách hàng",
            placeholder="Tên, số điện thoại hoặc CCCD..."
        )

        filtered = guests.copy()

        if search:

            mask = (
                filtered["full_name"]
                .astype(str)
                .str.contains(search, case=False)
                |
                filtered["phone"]
                .astype(str)
                .str.contains(search, case=False)
                |
                filtered["id_number"]
                .astype(str)
                .str.contains(search, case=False)
            )

            filtered = filtered[mask]

        display = filtered[
            [
                "full_name",
                "phone",
                "id_number",
                "address",
                "created_at"
            ]
        ].copy()

        display.columns = [
            "Họ tên",
            "Số điện thoại",
            "CCCD/CMND",
            "Địa chỉ",
            "Ngày tạo"
        ]

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True
        )

    with tab2:

        st.subheader("➕ Thêm khách hàng")

        with st.form("add_guest_form"):

            full_name = st.text_input(
                "Họ và tên *"
            )

            col1, col2 = st.columns(2)

            with col1:

                phone = st.text_input(
                    "Số điện thoại"
                )

                id_number = st.text_input(
                    "CCCD/CMND"
                )

            with col2:

                address = st.text_area(
                    "Địa chỉ"
                )

            submit = st.form_submit_button(
                "➕ Thêm khách hàng",
                use_container_width=True
            )

            if submit:

                if not full_name.strip():

                    st.error(
                        "Vui lòng nhập họ tên khách hàng."
                    )

                else:

                    cursor = conn.cursor()

                    cursor.execute("""
                        INSERT INTO guests
                        (full_name, phone, id_number, address, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        full_name.strip(),
                        phone,
                        id_number,
                        address,
                        datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    ))

                    conn.commit()

                    st.success(
                        "Đã thêm khách hàng."
                    )

                    st.rerun()


# ============================================================
# CHECK-IN
# ============================================================

elif menu == "📝 Check-in":

    st.title("📝 CHECK-IN KHÁCH")

    rooms = get_rooms()
    guests = get_guests()

    available_rooms = rooms[
        rooms["status"] == "Trống"
    ]

    if len(available_rooms) == 0:

        st.warning(
            "Hiện không có phòng trống để check-in."
        )

    else:

        with st.form("checkin_form"):

            st.subheader("🏨 Thông tin phòng")

            room_options = {
                f"Phòng {row['room_number']} - "
                f"{row['room_type']} - "
                f"{format_money(row['price'])}/đêm":
                row["id"]
                for _, row in available_rooms.iterrows()
            }

            selected_room = st.selectbox(
                "Chọn phòng",
                list(room_options.keys())
            )

            room_id = room_options[selected_room]

            st.subheader("👤 Thông tin khách")

            guest_options = {
                f"{row['full_name']} - "
                f"{row['phone'] or 'Không có SĐT'}":
                row["id"]
                for _, row in guests.iterrows()
            }

            if guest_options:

                selected_guest = st.selectbox(
                    "Khách hàng đã có",
                    list(guest_options.keys())
                )

                guest_id = guest_options[selected_guest]

                create_guest = False

            else:

                st.info(
                    "Chưa có khách hàng. "
                    "Hãy thêm khách trong mục Quản lý khách."
                )

                guest_id = None
                create_guest = False

            col1, col2 = st.columns(2)

            with col1:

                check_in = st.date_input(
                    "Ngày check-in",
                    value=date.today()
                )

                adults = st.number_input(
                    "Số người lớn",
                    min_value=1,
                    value=1
                )

            with col2:

                children = st.number_input(
                    "Số trẻ em",
                    min_value=0,
                    value=0
                )

                note = st.text_area(
                    "Ghi chú"
                )

            submit = st.form_submit_button(
                "📝 XÁC NHẬN CHECK-IN",
                use_container_width=True
            )

            if submit:

                if guest_id is None:

                    st.error(
                        "Vui lòng thêm khách hàng trước."
                    )

                else:

                    cursor = conn.cursor()

                    cursor.execute("""
                        INSERT INTO bookings
                        (
                            room_id,
                            guest_id,
                            check_in,
                            adults,
                            children,
                            status,
                            note
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        room_id,
                        guest_id,
                        check_in.strftime("%Y-%m-%d"),
                        adults,
                        children,
                        "Đang ở",
                        note
                    ))

                    cursor.execute("""
                        UPDATE rooms
                        SET status = 'Đang ở'
                        WHERE id = %s
                    """, (room_id,))

                    conn.commit()

                    st.success(
                        "✅ Check-in thành công!"
                    )

                    st.rerun()


# ============================================================
# CHECK-OUT
# ============================================================

elif menu == "🚪 Check-out":

    st.title("🚪 CHECK-OUT KHÁCH")

    bookings = get_bookings()

    active_bookings = bookings[
        bookings["status"] == "Đang ở"
    ]

    if len(active_bookings) == 0:

        st.info(
            "Hiện không có khách đang lưu trú."
        )

    else:

        booking_options = {
            f"Phòng {row['room_number']} - "
            f"{row['full_name']} - "
            f"Check-in {row['check_in']}":
            row["id"]
            for _, row in active_bookings.iterrows()
        }

        selected_booking = st.selectbox(
            "Chọn lượt lưu trú",
            list(booking_options.keys())
        )

        booking_id = booking_options[selected_booking]

        booking = active_bookings[
            active_bookings["id"] == booking_id
        ].iloc[0]

        st.markdown("---")

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "🏨 Phòng",
            booking["room_number"]
        )

        col2.metric(
            "👤 Khách",
            booking["full_name"]
        )

        col3.metric(
            "💰 Giá phòng",
            format_money(booking["price"])
        )

        check_in_date = datetime.strptime(
            booking["check_in"],
            "%Y-%m-%d"
        ).date()

        check_out_date = st.date_input(
            "Ngày check-out",
            value=date.today(),
            min_value=check_in_date
        )

        total, nights = calculate_total(
            booking["price"],
            check_in_date,
            check_out_date
        )

        st.info(
            f"🛏️ Số đêm: **{nights} đêm**"
        )

        st.success(
            f"💰 TỔNG TIỀN PHÒNG: **{format_money(total)}**"
        )

        if st.button(
            "🚪 XÁC NHẬN CHECK-OUT",
            type="primary",
            use_container_width=True
        ):

            cursor = conn.cursor()

            cursor.execute("""
                UPDATE bookings
                SET check_out = %s,
                    total_amount = %s,
                    status = 'Đã trả phòng'
                WHERE id = %s
            """, (
                check_out_date.strftime("%Y-%m-%d"),
                total,
                booking_id
            ))

            cursor.execute("""
                UPDATE rooms
                SET status = 'Đang dọn'
                WHERE id = (
                    SELECT room_id
                    FROM bookings
                    WHERE id = %s
                )
            """, (booking_id,))

            conn.commit()

            st.success(
                "✅ Check-out thành công!"
            )

            st.rerun()


# ============================================================
# ĐẶT PHÒNG
# ============================================================

elif menu == "📅 Đặt phòng":

    st.title("📅 ĐẶT PHÒNG")

    rooms = get_rooms()
    guests = get_guests()

    available_rooms = rooms[
        rooms["status"] == "Trống"
    ]

    if len(available_rooms) == 0:

        st.warning(
            "Không có phòng trống."
        )

    elif len(guests) == 0:

        st.warning(
            "Vui lòng thêm khách hàng trước."
        )

    else:

        with st.form("booking_form"):

            room_options = {
                f"Phòng {row['room_number']} - "
                f"{row['room_type']} - "
                f"{format_money(row['price'])}/đêm":
                row["id"]
                for _, row in available_rooms.iterrows()
            }

            selected_room = st.selectbox(
                "🏨 Chọn phòng",
                list(room_options.keys())
            )

            room_id = room_options[selected_room]

            guest_options = {
                f"{row['full_name']} - "
                f"{row['phone'] or 'Không có SĐT'}":
                row["id"]
                for _, row in guests.iterrows()
            }

            selected_guest = st.selectbox(
                "👤 Khách hàng",
                list(guest_options.keys())
            )

            guest_id = guest_options[selected_guest]

            col1, col2 = st.columns(2)

            with col1:

                booking_date = st.date_input(
                    "Ngày dự kiến nhận phòng",
                    value=date.today()
                )

            with col2:

                note = st.text_area(
                    "Ghi chú đặt phòng"
                )

            submit = st.form_submit_button(
                "📅 XÁC NHẬN ĐẶT PHÒNG",
                use_container_width=True
            )

            if submit:

                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO bookings
                    (
                        room_id,
                        guest_id,
                        check_in,
                        status,
                        note
                    )
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    room_id,
                    guest_id,
                    booking_date.strftime("%Y-%m-%d"),
                    "Đã đặt",
                    note
                ))

                cursor.execute("""
                    UPDATE rooms
                    SET status = 'Đang ở'
                    WHERE id = %s
                """, (room_id,))

                conn.commit()

                st.success(
                    "✅ Đặt phòng thành công!"
                )

                st.rerun()


# ============================================================
# BÁO CÁO
# ============================================================

elif menu == "📈 Báo cáo":

    st.title("📈 BÁO CÁO KHÁCH SẠN")

    bookings = get_bookings()
    rooms = get_rooms()

    st.subheader("💰 Doanh thu")

    completed = bookings[
        bookings["status"] == "Đã trả phòng"
    ].copy()

    total_revenue = completed[
        "total_amount"
    ].sum()

    total_bookings = len(completed)

    average_revenue = (
        total_revenue / total_bookings
        if total_bookings > 0
        else 0
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "💰 Tổng doanh thu",
        format_money(total_revenue)
    )

    col2.metric(
        "🧾 Số lượt đã trả phòng",
        total_bookings
    )

    col3.metric(
        "💵 Doanh thu trung bình",
        format_money(average_revenue)
    )

    st.markdown("---")

    if len(completed) > 0:

        st.subheader("📊 Doanh thu theo phòng")

        revenue_by_room = completed.groupby(
            "room_number"
        )["total_amount"].sum()

        st.bar_chart(
            revenue_by_room
        )

        st.subheader("📋 Chi tiết doanh thu")

        revenue_display = completed[
            [
                "room_number",
                "full_name",
                "check_in",
                "check_out",
                "total_amount"
            ]
        ].copy()

        revenue_display.columns = [
            "Phòng",
            "Khách",
            "Check-in",
            "Check-out",
            "Doanh thu"
        ]

        revenue_display["Doanh thu"] = revenue_display[
            "Doanh thu"
        ].apply(format_money)

        st.dataframe(
            revenue_display,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Chưa có dữ liệu doanh thu."
        )

    st.markdown("---")

    st.subheader("🏨 Thống kê loại phòng")

    if len(rooms) > 0:

        type_stats = rooms.groupby(
            "room_type"
        ).agg(
            Số_phòng=("id", "count")
        ).reset_index()

        type_stats.columns = [
            "Loại phòng",
            "Số phòng"
        ]

        st.dataframe(
            type_stats,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# FOOTER
# ============================================================

st.sidebar.markdown("---")
st.sidebar.caption(
    "© 2026 Hotel Manager | Streamlit"
)

