import time
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Binance LOB Monitor", layout="wide")
st.title("📈 Binance 即時行情 / 訂單簿")

# 每 1000ms 重新執行一次整個 app
st_autorefresh(interval=1000, key="auto-refresh")

from collections import deque, defaultdict
from datetime import datetime

import pandas as pd
import streamlit as st
from binance.spot import Spot

# -----------------------------
# 基本設定
# -----------------------------
st.set_page_config(page_title="Binance LOB Monitor", layout="wide")

# 自動刷新：每 1000ms 重新執行一次 app
try:
    st.autorefresh(interval=1000, key="auto-refresh")
except Exception:
    pass

# 初始化 Binance 客戶端（只讀公開資料，不需要 API Key）
client = Spot()

# -----------------------------
# 側邊欄控制
# -----------------------------
with st.sidebar:
    st.header("⚙️ 設定")
    default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "BTCUSD", "ETHUSD", "BTCEUR", "ETHEUR"]
    symbols = st.multiselect(
        "選擇交易對（可多選）",
        options=default_symbols,
        default=["BTCUSDT", "ETHUSDT"],
        help="可輸入其他現貨交易對（例如：SOLUSDT、XRPUSDT…）"
    )
    depth_limit = st.selectbox("訂單簿階數（雙邊）", [5, 10, 20, 50, 100], index=2)
    history_len = st.slider("走勢保存點數（每秒一點）", min_value=30, max_value=600, value=180, step=30)
    st.caption("此頁面每秒自動刷新；若不想刷新，可暫停瀏覽器的自動重新整理外掛。")

# 歷史價 + 上次數值（用於判斷漲跌）
if "history" not in st.session_state:
    st.session_state.history = defaultdict(lambda: deque(maxlen=history_len))
if "last_vals" not in st.session_state:
    # last_vals[sym] = {"price": float|None, "mid":..., "bid":..., "ask":...}
    st.session_state.last_vals = defaultdict(lambda: {"price": None, "mid": None, "bid": None, "ask": None})

# 若使用者修改了 history_len，更新 deque 的 maxlen
for sym, dq in list(st.session_state.history.items()):
    if dq.maxlen != history_len:
        st.session_state.history[sym] = deque(dq, maxlen=history_len)

if not symbols:
    st.info("請從左側選擇至少一個交易對。")
    st.stop()

# -----------------------------
# 工具：著色 + 箭頭
# -----------------------------
def colored_arrow(curr: float, prev: float | None):
    if prev is None:
        return "", ""
    if curr > prev:
        return "▲", "green"
    if curr < prev:
        return "▼", "red"
    return "→", "#888"

def color_text(label: str, value: float, prev: float | None, fmt: str = ",.2f"):
    arrow, color = colored_arrow(value, prev)
    val_str = format(value, fmt)
    if prev is None:
        return f"{label}：{val_str}"
    return f"""<span>{label}：</span>
               <span style="color:{color}; font-weight:700;">{val_str} {arrow}</span>"""

# -----------------------------
# 取資料的函式
# -----------------------------
def fetch_ticker(symbol: str):
    data = client.ticker_price(symbol)
    return float(data["price"])

def fetch_depth_best(symbol: str, limit: int):
    ob = client.depth(symbol, limit=limit)
    bids = ob.get("bids", [])
    asks = ob.get("asks", [])
    if not bids or not asks:
        return None

    best_bid_price = float(bids[0][0])
    best_bid_size  = float(bids[0][1])
    best_ask_price = float(asks[0][0])
    best_ask_size  = float(asks[0][1])
    spread = best_ask_price - best_bid_price
    mid = (best_ask_price + best_bid_price) / 2
    rel_spread_bps = (spread / mid) * 10_000 if mid else 0.0

    return {
        "best_bid_price": best_bid_price,
        "best_bid_size": best_bid_size,
        "best_ask_price": best_ask_price,
        "best_ask_size": best_ask_size,
        "spread": spread,
        "mid": mid,
        "rel_spread_bps": rel_spread_bps,
        "bids": bids,
        "asks": asks,
    }

# -----------------------------
# 主內容
# -----------------------------
now = datetime.now()
st.caption(f"最後更新時間：{now.strftime('%Y-%m-%d %H:%M:%S')}")

for sym in symbols:
    with st.container():
        cols = st.columns([1.2, 1.4, 1.4])  # 左：指標卡；中：走勢；右：深度表

        # 取資料
        try:
            ticker_price = fetch_ticker(sym)
            depth_info = fetch_depth_best(sym, depth_limit)
        except Exception as e:
            st.error(f"{sym} 取數據失敗：{e}")
            continue

        if not depth_info:
            st.warning(f"{sym} 沒有取得到訂單簿資料。")
            continue

        # 讀前值
        last = st.session_state.last_vals[sym]
        prev_price = last["price"]
        prev_mid   = last["mid"]
        prev_bid   = last["bid"]
        prev_ask   = last["ask"]

        # 更新歷史 & 前值
        st.session_state.history[sym].append({
            "ts": now,
            "price": ticker_price,
            "mid": depth_info["mid"],
            "bid": depth_info["best_bid_price"],
            "ask": depth_info["best_ask_price"],
        })
        last["price"] = ticker_price
        last["mid"]   = depth_info["mid"]
        last["bid"]   = depth_info["best_bid_price"]
        last["ask"]   = depth_info["best_ask_price"]

        # ---------- 左：重點指標（含紅綠箭頭） ----------
        with cols[0]:
            st.subheader(sym)

            # 1) 最新價（使用 metric 顯示 delta，自動紅綠）
            delta_price = None if prev_price is None else ticker_price - prev_price
            st.metric("最新價", f"{ticker_price:,.2f}",
                      delta=None if delta_price is None else f"{delta_price:+.2f}")

            # 2) Mid（metric + 紅綠箭頭）
            delta_mid = None if prev_mid is None else depth_info["mid"] - prev_mid
            st.metric("Mid", f"{depth_info['mid']:,.2f}",
                      delta=None if delta_mid is None else f"{delta_mid:+.2f}")

            # 3) Spread & 相對價差
            kpi3, kpi4 = st.columns(2)
            kpi3.metric("Spread", f"{depth_info['spread']:,.4f}")
            kpi4.metric("相對價差", f"{depth_info['rel_spread_bps']:,.1f} bps")

            # 4) Bid/Ask 文字行加紅綠箭頭
            bid_html = color_text("最佳買一",
                                  depth_info["best_bid_price"], prev_bid, fmt=",.2f")
            ask_html = color_text("最佳賣一",
                                  depth_info["best_ask_price"], prev_ask, fmt=",.2f")
            st.markdown(bid_html, unsafe_allow_html=True)
            st.write(f"數量：{depth_info['best_bid_size']}")
            st.markdown(ask_html, unsafe_allow_html=True)
            st.write(f"數量：{depth_info['best_ask_size']}")

        # ---------- 中：走勢（每秒一點，畫 mid） ----------
        with cols[1]:
            st.markdown("**價格走勢（mid）**")
            hist_df = pd.DataFrame(st.session_state.history[sym])
            if not hist_df.empty:
                hist_df = hist_df.set_index("ts")
                # 你也可改成多線：hist_df[["mid","bid","ask"]]
                st.line_chart(hist_df[["mid"]])
            else:
                st.info("等待累積資料…")

        # ---------- 右：深度（前 N 檔） ----------
        with cols[2]:
            st.markdown(f"**訂單簿前 {depth_limit} 檔**")
            bids_df = pd.DataFrame(depth_info["bids"], columns=["Bid Price", "Bid Size"]).astype(float)
            asks_df = pd.DataFrame(depth_info["asks"], columns=["Ask Price", "Ask Size"]).astype(float)
            bids_df = bids_df.sort_values("Bid Price", ascending=False).head(depth_limit)
            asks_df = asks_df.sort_values("Ask Price", ascending=True).head(depth_limit)

            c1, c2 = st.columns(2)
            with c1:
                st.caption("Bids")
                st.dataframe(bids_df, height=280, use_container_width=True)
            with c2:
                st.caption("Asks")
                st.dataframe(asks_df, height=280, use_container_width=True)

        st.markdown("---")
