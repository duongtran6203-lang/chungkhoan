import telebot
import yfinance as yf
import pandas as pd
import feedparser
import time
import schedule
import threading
import matplotlib
import matplotlib.pyplot as plt
import io
import pytz
from datetime import datetime
from flask import Flask

# Cấu hình Matplotlib chạy ngầm (Bắt buộc cho Server)
matplotlib.use('Agg')

# ==============================================================================
# 👇👇👇 HUYNH ĐIỀN TOKEN VÀ CHAT ID CỦA HUYNH VÀO ĐÂY NHÉ 👇👇👇
# ==============================================================================

API_TOKEN = '8384214679:AAE01deHHCPjpB7ZzxxTuXbTNLhbg58Q0gw'  # Ví dụ: '718273:AAGHs8...'
CHAT_ID = '6482223382'    # Ví dụ: '6482223382'

SYMBOL = 'VCB.VN' # Mã cổ phiếu
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh') # Múi giờ Việt Nam

# ==============================================================================

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- CẤU HÌNH WEB SERVER GIẢ (ĐỂ RENDER KHÔNG TẮT BOT) ---
@app.route('/')
def home():
    return f"🤖 BOT {SYMBOL} ĐANG CHẠY 24/7!"

def run_web():
    # Chạy trên cổng 8080 (Cổng mặc định Render thường dùng)
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.start()

# --- HÀM LẤY DỮ LIỆU ---
def get_data():
    try:
        # Lấy dữ liệu 6 tháng
        ticker = yf.Ticker(SYMBOL)
        df = ticker.history(period="6mo", interval="1d")
        if df.empty: return None
        
        # Tính RSI (14)
        delta = df['Close'].diff(1)
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # Tính EMA 50 (Xu hướng)
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        # Tính MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        return df
    except Exception as e:
        print(f"Lỗi lấy dữ liệu: {e}")
        return None

# --- TÍNH NĂNG 1: ĐỌC BÁO & PHÂN TÍCH (Mỗi sáng) ---
def job_daily_news():
    print("📰 Đang quét tin tức...")
    clean_symbol = SYMBOL.replace('.VN', '')
    url = f"https://news.google.com/rss/search?q={clean_symbol}+ch%E1%BB%A9ng+kho%C3%A1n&hl=vi&gl=VN&ceid=VN:vi"
    
    try:
        feed = feedparser.parse(url)
        now_str = datetime.now(VN_TZ).strftime('%d/%m/%Y')
        msg = f"🗞️ **BẢN TIN SÁNG {now_str}**\nFocus: #{clean_symbol}\n\n"
        
        total_score = 0
        positive_kws = ["lãi", "tăng", "kỷ lục", "cổ tức", "mua", "tích cực"]
        negative_kws = ["lỗ", "giảm", "bắt", "phạt", "nợ", "xấu", "tiêu cực"]

        for entry in feed.entries[:5]:
            title = entry.title
            score = 0
            t_lower = title.lower()
            
            for k in positive_kws: 
                if k in t_lower: score += 1
            for k in negative_kws: 
                if k in t_lower: score -= 1.5
            
            total_score += score
            icon = "🟢" if score > 0 else ("🔴" if score < 0 else "⚪")
            msg += f"{icon} [{title}]({entry.link})\n"

        rating = "TRUNG LẬP"
        if total_score >= 2: rating = "TÍCH CỰC (Tin Tốt)"
        elif total_score <= -2: rating = "TIÊU CỰC (Tin Xấu)"
        
        msg += f"\n📊 **Đánh giá AI:** {rating}"
        bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Lỗi news: {e}")

# --- TÍNH NĂNG 2: GỬI BIỂU ĐỒ & NHẬN ĐỊNH (Sáng/Chiều) ---
def job_daily_chart():
    print("📈 Đang vẽ biểu đồ...")
    df = get_data()
    if df is None: return

    last = df.iloc[-1]
    price = last['Close']
    
    # 1. Vẽ Chart ra ảnh
    plt.figure(figsize=(10, 8))
    
    # Chart Giá
    plt.subplot(2, 1, 1)
    plt.plot(df.index, df['Close'], label='Gia', color='green')
    plt.plot(df.index, df['EMA50'], label='EMA 50', color='orange', linestyle='--')
    plt.title(f"Bieu do {SYMBOL} - Gia: {price:,.0f} VND")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Chart RSI
    plt.subplot(2, 1, 2)
    plt.plot(df.index, df['RSI'], label='RSI', color='purple')
    plt.axhline(70, color='red', linestyle='--') # Vùng quá mua
    plt.axhline(30, color='green', linestyle='--') # Vùng quá bán
    plt.fill_between(df.index, 30, 70, color='gray', alpha=0.1)
    plt.title(f"RSI Indicator: {last['RSI']:.2f}")
    plt.tight_layout()
    
    # Lưu ảnh vào RAM
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    # 2. Viết lời bình
    points = []
    # Phân tích RSI
    if last['RSI'] < 30: points.append("✅ RSI Vùng đáy (Quá bán) -> Cơ hội MUA")
    elif last['RSI'] > 70: points.append("⚠️ RSI Vùng đỉnh (Quá mua) -> Cẩn thận chỉnh")
    else: points.append("ℹ️ RSI Trung tính")
    
    # Phân tích Xu hướng
    if price > last['EMA50']: points.append("✅ Xu hướng Tăng (Giá > EMA50)")
    else: points.append("⚠️ Xu hướng Giảm (Giá < EMA50)")
    
    # Phân tích MACD
    if last['MACD'] > last['Signal']: points.append("✅ MACD cắt lên -> Động lượng Tăng")
    else: points.append("⚠️ MACD cắt xuống -> Động lượng Giảm")

    # Tổng kết
    good = sum(1 for p in points if "✅" in p)
    bad = sum(1 for p in points if "⚠️" in p)
    
    advice = "QUAN SÁT THÊM"
    if good > bad: advice = "NÊN MUA / NẮM GIỮ 🚀"
    elif bad > good: advice = "NÊN BÁN / HẠ TỶ TRỌNG 📉"

    caption = f"🏆 **NHẬN ĐỊNH NGÀY {datetime.now(VN_TZ).strftime('%d/%m')}**\n\n"
    caption += "\n".join(points)
    caption += f"\n\n💡 **AI KHUYÊN:** {advice}"

    bot.send_photo(CHAT_ID, photo=buf, caption=caption, parse_mode='Markdown')

# --- TÍNH NĂNG 3: CANH GIÁ REAL-TIME (24/7) ---
def run_realtime_alert():
    print("🚀 Realtime Alert started...")
    last_state = "NORMAL"
    
    while True:
        try:
            # Chỉ check trong giờ hành chính (9h - 15h) để đỡ tốn tài nguyên
            h = datetime.now(VN_TZ).hour
            if 9 <= h <= 15:
                df = get_data()
                if df is not None:
                    last = df.iloc[-1]
                    rsi = last['RSI']
                    price = last['Close']
                    
                    state = "NORMAL"
                    msg = ""

                    if rsi < 30:
                        state = "BUY"
                        msg = f"🚨 **BÁO ĐỘNG MUA!**\n{SYMBOL} rơi về vùng quá bán!\nRSI: {rsi:.1f}\nGiá: {price:,.0f}"
                    elif rsi > 75:
                        state = "SELL"
                        msg = f"⚠️ **BÁO ĐỘNG BÁN!**\n{SYMBOL} tăng quá nóng!\nRSI: {rsi:.1f}\nGiá: {price:,.0f}"
                    
                    # Nếu trạng thái thay đổi thì mới báo (tránh spam)
                    if state != "NORMAL" and state != last_state:
                        bot.send_message(CHAT_ID, msg)
                        last_state = state
                    elif state == "NORMAL":
                        last_state = "NORMAL"
            
            # Nghỉ 5 phút check 1 lần
            time.sleep(300)
            
        except Exception as e:
            print(f"Lỗi realtime: {e}")
            time.sleep(60)

# --- BỘ HẸN GIỜ (SCHEDULER) ---
def run_scheduler():
    # Giờ này là giờ hệ thống Server (Thường là UTC)
    # Nhưng vì ta set timezone VN ở logic hiển thị nên cứ hẹn giờ VN ở đây cũng được 
    # nếu server chỉnh đúng giờ. Để chắc ăn, ta dùng giờ tương đối.
    
    # 8:00 Sáng đọc báo
    schedule.every().day.at("08:00").do(job_daily_news)
    # 9:15 Sáng soi chart đầu phiên
    schedule.every().day.at("09:15").do(job_daily_chart)
    # 14:45 Chiều tổng kết phiên
    schedule.every().day.at("14:45").do(job_daily_chart)

    while True:
        schedule.run_pending()
        time.sleep(60)

# --- CHẠY CHƯƠNG TRÌNH ---
if __name__ == "__main__":
    # 1. Khởi động Web Server giả (Để Render thấy bot còn sống)
    keep_alive()

    # 2. Gửi tin nhắn báo bot đã bật
    try:
        bot.send_message(CHAT_ID, f"🤖 **BOT {SYMBOL} ĐÃ ONLINE TRÊN RENDER!**\nSẵn sàng phục vụ huynh.")
    except Exception as e:
        print("Lỗi Token/ChatID: Kiểm tra lại đi huynh ơi!")

    # 3. Chạy đa luồng (Realtime + Hẹn giờ)
    t1 = threading.Thread(target=run_realtime_alert)
    t2 = threading.Thread(target=run_scheduler)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()