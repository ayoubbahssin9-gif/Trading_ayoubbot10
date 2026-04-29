import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import yfinance as yf
import pandas as pd
from groq import Groq
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("8640378180:AAHjmdbQwWN0Cam8ljGlqp9oG80S5eKbvV8")
GROQ_API_KEY = os.getenv("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")

CAPITAL = 400
MAX_RISK = CAPITAL * 0.02
groq_client = Groq(api_key=GROQ_API_KEY)

MARKETS = {
    "🏅 ذهب": "GC=F",
    "🟤 نحاس": "HG=F",
    "🛢️ نفط": "CL=F",
    "📈 S&P500": "^GSPC",
    "💻 NASDAQ": "^IXIC",
    "₿ Bitcoin": "BTC-USD",
    "🇯🇵 ين": "JPY=X",
    "💵 دولار": "DX-Y.NYB",
}

def check_time():
    h = datetime.utcnow().hour
    w = datetime.utcnow().weekday()
    if w >= 5: return "⛔ السوق مغلق"
    if 8 <= h < 12: return "✅ جلسة لندن"
    if 13 <= h < 17: return "✅ جلسة نيويورك"
    if 2 <= h < 8: return "🟡 جلسة آسيا"
    return "⚠️ وقت ضعيف"

def calc_rsi(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(p).mean()
    l = -d.clip(upper=0).rolling(p).mean()
    return (100 - (100 / (1 + g/l))).iloc[-1]

def get_market_data():
    results = {}
    for name, ticker in MARKETS.items():
        try:
            df = yf.download(ticker, period="5d", interval="1h", progress=False)
            if df.empty or len(df) < 20: continue
            close = df["Close"].squeeze()
            price = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            change = round((price - prev) / prev * 100, 2)
            rsi = float(calc_rsi(close))
            ema20 = float(close.ewm(span=20).mean().iloc[-1])
            trend = "📈" if price > ema20 else "📉"
            results[name] = {"price": round(price, 4), "change": change, "rsi": round(rsi, 1), "trend": trend}
        except: continue
    return results

def get_fear_greed(data):
    score = 0
    total = 0
    for name, d in data.items():
        if d["rsi"] > 70: score += 2
        elif d["rsi"] > 55: score += 1
        elif d["rsi"] < 30: score -= 2
        elif d["rsi"] < 45: score -= 1
        if d["change"] > 0: score += 1
        else: score -= 1
        total += 3
    if total == 0: return "⚪ محايد", 50
    pct = max(0, min(100, int((score + total) / (total * 2) * 100)))
    if pct >= 75: return "🟢 طمع شديد", pct
    elif pct >= 55: return "🟡 طمع", pct
    elif pct <= 25: return "🔴 خوف شديد", pct
    elif pct <= 45: return "🟠 خوف", pct
    else: return "⚪ محايد", pct

def get_liquidity_flow(data):
    safe = 0
    risk = 0
    for name, d in data.items():
        if "ذهب" in name or "ين" in name or "دولار" in name:
            if d["change"] > 0: safe += 1
            else: safe -= 1
        else:
            if d["change"] > 0: risk += 1
            else: risk -= 1
    if risk > safe + 1: return "💸 السيولة تتجه للمخاطرة"
    elif safe > risk + 1: return "🛡️ السيولة تتجه للأمان"
    else: return "⚖️ السيولة محايدة"

def get_ai_analysis(data, fear_greed, liquidity):
    summary = "\n".join([f"{k}: السعر={v['price']}, تغيير={v['change']}%, RSI={v['rsi']}" for k,v in data.items()])
    prompt = f"""أنت محلل أسواق مالية خبير بـ15 سنة خبرة.
بيانات الأسواق: {summary}
مؤشر الطمع/الخوف: {fear_greed[0]} ({fear_greed[1]}%)
تدفق السيولة: {liquidity}
حلل بالعربية في 6 أسطر: الحالة العامة، أين السيولة، معنى الطمع/الخوف، أفضل أصل، أهم مخاطرة، توصية للمبتدئ."""
    r = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}]
    )
    return r.choices[0].message.content

def calc_rsi_series(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(p).mean()
    l = -d.clip(upper=0).rolling(p).mean()
    return 100 - (100 / (1 + g/l))

def analyze_single(ticker, tf="1h"):
    period = "5d" if tf in ["15m","1h"] else "3mo"
    df = yf.download(ticker, period=period, interval=tf, progress=False)
    if df.empty or len(df) < 30: return None
    close = df["Close"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()
    price = float(close.iloc[-1])
    rsi = float(calc_rsi_series(close).iloc[-1])
    ema20 = float(close.ewm(span=20).mean().iloc[-1])
    ema50 = float(close.ewm(span=50).mean().iloc[-1])
    ema200 = float(close.ewm(span=200).mean().iloc[-1])
    tr = pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    score = 0
    if rsi < 30: score += 2
    elif rsi < 45: score += 1
    elif rsi > 70: score -= 2
    elif rsi > 55: score -= 1
    if ema20 > ema50: score += 1
    else: score -= 1
    if price > ema200: score += 1
    else: score -= 1
    conf = sum([rsi<45, ema20>ema50, price>ema200])
    if score >= 3 and conf >= 3: signal = "🚀 شراء قوي"
    elif score >= 1 and conf >= 2: signal = "📈 شراء محتمل"
    elif score <= -3: signal = "📉 بيع قوي"
    elif score <= -1: signal = "⚠️ بيع محتمل"
    else: signal = "⏳ انتظار"
    sl = round(price - atr*1.5, 4)
    tp = round(price + atr*2.5, 4)
    rr = round(abs(tp-price)/abs(sl-price),1) if abs(sl-price)>0 else 0
    pos = round(MAX_RISK/abs(price-sl),4) if abs(price-sl)>0 else 0
    return {"price":round(price,4),"rsi":round(rsi,1),"ema_trend":"صاعد 📈" if ema20>ema50 else "هابط 📉","ema200":"فوق ✅" if price>ema200 else "تحت ⚠️","signal":signal,"conf":conf,"sl":sl,"tp":tp,"rr":rr,"pos":pos}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌍 تحليل كل الأسواق", callback_data="all_markets")],
        [InlineKeyboardButton("🧠 تحليل AI الشامل", callback_data="ai_analysis")],
        [InlineKeyboardButton("📊 تحليل أصل واحد", callback_data="single")],
        [InlineKeyboardButton("💰 إدارة المال", callback_data="money")],
    ]
    await update.message.reply_text(f"🤖 *Bot Trading AYB*\n\n🕐 {check_time()}\n\nاختر نوع التحليل:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "all_markets":
        await query.edit_message_text("⏳ جاري تحليل 8 أسواق...")
        mdata = get_market_data()
        if not mdata:
            await query.edit_message_text("❌ خطأ")
            return
        fg, fg_pct = get_fear_greed(mdata)
        liq = get_liquidity_flow(mdata)
        msg = f"🌍 *تحليل الأسواق*\n🕐 {check_time()}\n──────────────\n"
        for name, d in mdata.items():
            arrow = "🟢" if d["change"] > 0 else "🔴"
            msg += f"{arrow} {name}: `{d['price']}` ({d['change']:+}%) RSI:{d['rsi']} {d['trend']}\n"
        msg += f"──────────────\n😱 {fg} ({fg_pct}%)\n💸 {liq}\n⚠️ _للتعليم فقط_"
        context.user_data["mdata"] = mdata
        context.user_data["fg"] = (fg, fg_pct)
        context.user_data["liq"] = liq
        keyboard = [[InlineKeyboardButton("🧠 تحليل AI", callback_data="ai_analysis")],[InlineKeyboardButton("🔄 تحديث", callback_data="all_markets"),InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "ai_analysis":
        await query.edit_message_text("🧠 يحلل...")
        mdata = context.user_data.get("mdata") or get_market_data()
        fg = context.user_data.get("fg") or get_fear_greed(mdata)
        liq = context.user_data.get("liq") or get_liquidity_flow(mdata)
        analysis = get_ai_analysis(mdata, fg, liq)
        await query.edit_message_text(f"🧠 *تحليل AI*\n\n{analysis}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
    elif data == "single":
        keyboard = [[InlineKeyboardButton(n, callback_data=f"sym_{n}")] for n in MARKETS]
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
        await query.edit_message_text("اختر الأصل:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("sym_"):
        symbol = data[4:]
        context.user_data["symbol"] = symbol
        keyboard = [[InlineKeyboardButton("⚡ 15د", callback_data="tf_15m"),InlineKeyboardButton("🕐 1h", callback_data="tf_1h")],[InlineKeyboardButton("🕓 4h", callback_data="tf_4h"),InlineKeyboardButton("📅 1d", callback_data="tf_1d")]]
        await query.edit_message_text(f"📌 *{symbol}* — اختر الإطار:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("tf_"):
        tf = data[3:]
        symbol = context.user_data.get("symbol","🏅 ذهب")
        ticker = MARKETS[symbol]
        await query.edit_message_text("⏳ جاري التحليل...")
        r = analyze_single(ticker, tf)
        if not r:
            await query.edit_message_text("❌ خطأ، حاول مجدداً.")
            return
        warn = "\n⚠️ *المؤشرات غير متفقة — لا تدخل!*" if r["conf"] < 2 else ""
        msg = (f"📊 *{symbol} — {tf}*\n──────────────\n💰 السعر: `{r['price']}`\n📊 RSI: `{r['rsi']}`\n📈 EMA: {r['ema_trend']}\n📉 EMA200: {r['ema200']}\n✅ تأكيدات: `{r['conf']}/3`\n──────────────\n🎯 *{r['signal']}*{warn}\n🛑 SL: `{r['sl']}`\n✅ TP: `{r['tp']}`\n📐 R/R: `1:{r['rr']}`\n──────────────\n💵 حجم: `{r['pos']}` وحدة\n💸 خسارة max: `${MAX_RISK}`\n🕐 {check_time()}\n⚠️ _للتعليم فقط_")
        keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data=f"tf_{tf}"),InlineKeyboardButton("🔙 رجوع", callback_data="single")]]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "money":
        msg = (f"💰 *إدارة المال*\n──────────────\n💵 رأس المال: `$400`\n⚡ خسارة/صفقة: `$8`\n📊 أقصى صفقتين\n🛑 خسرت $40/أسبوع = توقف\n🎯 الهدف: `$20-40/شهر`\n──────────────\n1️⃣ تأكيدات 3/3 فقط\n2️⃣ لا تدخل قبل أخبار\n3️⃣ لا وقت ضعيف\n4️⃣ لا تضاعف الخسائر\n5️⃣ الصبر = النجاح")
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
    elif data == "back":
        keyboard = [[InlineKeyboardButton("🌍 تحليل كل الأسواق", callback_data="all_markets")],[InlineKeyboardButton("🧠 تحليل AI الشامل", callback_data="ai_analysis")],[InlineKeyboardButton("📊 تحليل أصل واحد", callback_data="single")],[InlineKeyboardButton("💰 إدارة المال", callback_data="money")]]
        await query.edit_message_text(f"🤖 *Bot Trading AYB*\n\n🕐 {check_time()}\n\nاختر نوع التحليل:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    print("✅ البوت يعمل!")
    app.run_polling()

if __name__ == "__main__":
    main()
