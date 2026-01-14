import os
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

# Cấu hình Matplotlib chạy ngầm (Headless mode cho Server)
matplotlib.use('Agg')

# ================= CẤU HÌNH (LẤY TỪ RAILWAY) =================
# Huynh KHÔNG điền token vào đây nữa, mà sẽ điền trên web Railway
API_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
SYMBOL = 'VCB.VN'

# Kiểm tra nếu chưa cấu hình thì báo lỗi
if not API_TOKEN or not CHAT_ID:
    print("❌ LỖI: Chưa cấu hình BOT_TOKEN hoặc CHAT_ID trên Railway!")
    exit(1)

bot = telebot.TeleBot(API_TOKEN)
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh') # Múi giờ Việt Nam

# ================= TỪ KHÓA =================
POSITIVE_KEYWORDS = ["lãi", "lợi nhuận", "tăng trưởng", "cổ tức", "mua", "triển vọng", "kỷ lục", "tích cực", "khả quan"]
NEGATIVE_KEYWORDS = ["lỗ", "giảm", "sụt", "cảnh báo", "bắt", "nợ xấu", "tiêu cực", "bán tháo", "kém", "khó khăn"]

# ================= HÀM XỬ LÝ DỮ LIỆU =================
def get_data():
    try:
        ticker = yf.Ticker(SYMBOL)
        df = ticker.history(period="6mo", interval="1d")
        if df.empty: return None
        
        # Indicator Calculation
        delta = df['Close'].diff(1)
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        return df
    except Exception as e:
        print(f"Lỗi data: {e}")
        return None

# ================= TÁC VỤ 1: TIN TỨC =================
def job_daily_news():
    print("📰 Bot đang đọc báo...")
    clean_symbol = SYMBOL.replace('.VN', '')
    url = f"https://news.google.com/rss/search?q={clean_symbol}+ch%E1%BB%A9ng+kho%C3%A1n&hl=vi&gl=VN&ceid=VN:vi"
    
    try:
        feed = feedparser.parse(url)
        # Lấy ngày hiện tại theo giờ VN
        now_vn = datetime.now(VN_TZ).strftime('%d/%m/%Y')
        msg = f"🗞️ **BẢN TIN SÁNG {now_vn}: {clean_symbol}**\n\n"
        
        total_score = 0
        count = 0
        
        for entry in feed.entries[:5]:
            title = entry.title
            score = 0
            t_lower = title.lower()
            
            for k in POSITIVE_KEYWORDS: 
                if k in t_lower: score += 1
            for k in NEGATIVE_KEYWORDS: 
                if k in t_lower: score -= 1.5
            
            total_score += score
            icon = "🟢" if score > 0 else ("🔴" if score < 0 else "⚪")
            msg += f"{icon} [{title}]({entry.link})\n"
            count += 1

        rating = "TRUNG LẬP"
        if total_score >= 2: rating = "TÍCH CỰC (Tin tốt)"
        elif total_score <= -2: rating = "TIÊU CỰC (Tin xấu)"
        
        msg += f"\n📊 **Đánh giá:** {rating}"
        bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
        
    except Exception as e:
        print(f"Lỗi news: {e}")

# ================= TÁC VỤ 2: PHÂN TÍCH CHART =================
def job_daily_chart_review():
    print("📈 Bot đang vẽ chart...")
    df = get_data()
    if df is None: return

    last = df.iloc[-1]
    price = last['Close']
    
    # Vẽ Chart
    plt.figure(figsize=(10, 8))
    
    plt.subplot(2, 1, 1)
    plt.plot(df.index, df['Close'], label='Gia', color='green')
    plt.plot(df.index, df['EMA50'], label='EMA50', color='orange', linestyle='--')
    plt.title(f"{SYMBOL} - Gia: {price:,.0f} VND")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.subplot(2, 1, 2)
    plt.plot(df.index, df['RSI'], label='RSI', color='purple')
    plt.axhline(70, color='red', linestyle='--', linewidth=0.5)
    plt.axhline(30, color='green', linestyle='--', linewidth=0.5)
    plt.title(f"RSI: {last['RSI']:.2f}")
    plt.fill_between(df.index, 30, 70, color='gray', alpha=0.1)
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    # Phân tích lời
    points = []
    if last['RSI'] < 30: points.append("✅ RSI Quá bán (Giá rẻ) -> Canh Mua")
    elif last['RSI'] > 70: points.append("⚠️ RSI Quá mua (Nóng) -> Canh Bán")
    
    if price > last['EMA50']: points.append("✅ Trend Tăng (Trên EMA50)")
    else: points.append("⚠️ Trend Giảm (Dưới EMA50)")
    
    if last['MACD'] > last['Signal']: points.append("✅ MACD cắt lên -> Mua")
    else: points.append("⚠️ MACD cắt xuống -> Bán")

    advice = "QUAN SÁT"
    good_pts = sum(1 for p in points if "✅" in p)
    bad_pts = sum(1 for p in points if "⚠️" in p)
    
    if good_pts > bad_pts: advice = "NÊN MUA / GIỮ"
    elif bad_pts > good_pts: advice = "NÊN BÁN / HẠ TỶ TRỌNG"

    caption = f"🏆 **NHẬN ĐỊNH NGÀY {datetime.now(VN_TZ).strftime('%d/%m')}**\n\n"
    caption += "\n".join(points)
    caption += f"\n\n💡 **AI KHUYÊN:** {advice}"

    bot.send_photo(CHAT_ID, photo=buf, caption=caption, parse_mode='Markdown')

# ================= TÁC VỤ 3: CANH GIÁ 24/7 =================
def run_realtime_alert():
    print("🚀 Realtime Alert started...")
    last_state = "NORMAL"
    
    while True:
        try:
            # Chỉ check trong giờ giao dịch (9h-15h) để tiết kiệm tài nguyên
            h = datetime.now(VN_TZ).hour
            if 9 <= h <= 15:
                df = get_data()
                if df is not None:
                    last = df.iloc[-1]
                    rsi = last['RSI']
                    price = last['Close']
                    
                    msg = ""
                    current_state = "NORMAL"

                    if rsi < 30:
                        current_state = "BUY"
                        msg = f"🚨 **MUA GẤP!** RSI {rsi:.1f} (Quá bán)\nGiá: {price:,.0f}"
                    elif rsi > 75:
                        current_state = "SELL"
                        msg = f"⚠️ **BÁN NGAY!** RSI {rsi:.1f} (Quá mua)\nGiá: {price:,.0f}"
                    
                    # Chỉ báo nếu trạng thái thay đổi
                    if current_state != "NORMAL" and current_state != last_state:
                        bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
                        last_state = current_state
                    elif current_state == "NORMAL":
                        last_state = "NORMAL"

            time.sleep(300) # Check 5 phút/lần
        except Exception as e:
            print(f"Err realtime: {e}")
            time.sleep(60)

# ================= MAIN SCHEDULER =================
def run_scheduler():
    # Giờ server Railway là giờ UTC (Giờ VN = UTC + 7)
    # Tuy nhiên thư viện schedule dùng giờ hệ thống. 
    # Ta sẽ set múi giờ trên Railway là Asia/Ho_Chi_Minh nên cứ đặt giờ VN
    schedule.every().day.at("08:00").do(job_daily_news)       # 8h sáng đọc báo
    schedule.every().day.at("09:15").do(job_daily_chart_review) # 9h15 soi chart đầu phiên
    schedule.every().day.at("14:45").do(job_daily_chart_review) # 14h45 soi chart kết phiên

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    # Gửi tin báo bot khởi động
    try:
        bot.send_message(CHAT_ID, "🤖 **BOT VCB ĐÃ LÊN MÂY RAILWAY!**\nSẵn sàng trực chiến 24/7.")
    except:
        print("Không gửi được tin khởi động (Check Token/ChatID)")

    # Chạy đa luồng
    t1 = threading.Thread(target=run_realtime_alert)
    t2 = threading.Thread(target=run_scheduler)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()