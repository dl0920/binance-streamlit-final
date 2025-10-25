import streamlit as st
from streamlit_autorefresh import st_autorefresh
from binance.spot import Spot
import pandas as pd
from collections import deque, defaultdict
from datetime import datetime

# -----------------------------
# 自動刷新（每秒）
# -----------------------------
st.set_page_config(page_title="Binance LOB Monitor", layout="wide")
st.title("📈 Binance 即時行情 / 訂單簿（每秒更新、上漲綠/下跌紅）")
st_autorefresh(interval=1000, key="auto-refresh")

# -----------------------------
# 側邊欄設定
# -----------------------------
with st.sidebar:
    st.header("⚙️ 設定")
    # ⚠️ 在雲端預設 Testnet，避免 451
    use_testnet = st.toggle("使用 Testnet（建議雲端開啟）", value=True,
                            help="雲端伺服器常被主網地區限制；Testnet 不會 451")
    default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    symbols = st.multiselect("選擇交易對（可多選）", options=default_symbols,
                             default=["BTCUSDT", "ETHUSDT"])
    depth_limit = st.selectbox("訂單簿階數（雙邊）", [5, 10, 20, 50, 100], index=2)
    history_len = st.slider("走勢保存點數（每秒一點）", min_value=30, max_value=600, value=180, step=30)

base_url = "https://testnet.binance.vision" if use_testnet else "https://api.binance.com"
st.caption(f"目前 API：{base_url}")

# -----------------------------
# 建立 Binance Client（只讀，不需要 key）
# -----------------------------
client = Spot(base_url=base_url)

# 狀態保存
if "history" not in st.session_state:
    st.session_state.history = defaultdict(lambda: deque(maxlen=history_len))
if "last_vals" not in st.session_state:
    st.session_state.last_vals = defaultdict(lambda: {"price": None, "mid": None, "bid": None, "ask": None})
# 如果改了 history_len，要同步 deque 的長度
for sym, dq in list(st.session_state.history.items()):
    if dq.maxlen != history_len:
        st.session_state.history[sym] = deque(dq, maxlen=history_len)

if not symbols:
    st.info("請從左側選擇至少一個交易對。")
    st.stop()

# -----------------------------
# 取數據（含清楚的錯誤訊息）
# -----------------------------
def fetch_ticker(symbol: str):
    return float(client.ticker_price(symbol)["price"])

def fetch_depth_best(symbol: str, limit: int):
    ob = client.depth(symbol, limit=limit)
    bids = ob.get("bids") or []
    asks = ob.get("asks") or []
    if not bids or not asks:
        return None
    bbp, bbs = float(bids[0][0]), float(bids[0][1])
    bap, bas = float(asks[0][0]), float(asks[0][1])
    spread = bap - bbp
    mid = (bap + bbp) / 2
    rel_bps = (spread / mid) * 10_000 if mid else 0.0
    return {
        "best_bid_price": bbp, "best_bid_size": bbs,
        "best_ask_price": bap, "best_ask_size": bas,
        "spread": spread, "mid": mid, "rel_spread_bps": rel_bps,
        "bids": bids, "asks": asks
    }

# 著色工具
def arrow_and_color(curr, prev):
    if prev is None:
        return "", "#BBB"
    if curr > prev:
        return "▲", "green"
    if curr < prev:
        return "▼", "red"
    return "→", "#888"

now = datetime.now()
st.caption(f"最後更新時間：{now.strftime('%Y-%m-%d %H:%M:%S')}")

for sym in symbols:
    with st.container():
        cols = st.columns([1.2, 1.4, 1.4])

        # 嘗試抓數據；如果 451 / 403 等，顯示清楚的錯誤
        try:
            price = fetch_ticker(sym)
            depth = fetch_depth_best(sym, depth_limit)
        except Exception as e:
            st.error(f"{sym} 取數據失敗：{e}\n(目前 base_url={base_url})")
            st.markdown("➡️ 如果你在雲端且看到 451/403，保持 **使用 Testnet** 開啟即可。")
            st.markdown("➡️ 若仍失敗，試試改用其他部署平台或改回本機 + Cloudflare tunnel。")
            st.markdown("---")
            continue

        if not depth:
            st.warning(f"{sym} 沒有取得到訂單簿資料。（base_url={base_url}）")
            st.markdown("---")
            continue

        # 讀前值 / 更新歷史
        last = st.session_state.last_vals[sym]
        prev_price, prev_mid = last["price"], last["mid"]
        prev_bid, prev_ask = last["bid"], last["ask"]

        st.session_state.history[sym].append({
            "ts": now, "price": price, "mid": depth["mid"],
            "bid": depth["best_bid_price"], "ask": depth["best_ask_price"]
        })
        last.update({"price": price, "mid": depth["mid"],
                     "bid": depth["best_bid_price"], "ask": depth["best_ask_price"]})

        # 左側 KPI（含漲綠跌紅）
        with cols[0]:
            st.subheader(sym)
            delta_p = None if prev_price is None else price - prev_price
            st.metric("最新價", f"{price:,.2f}", None if delta_p is None else f"{delta_p:+.2f}")

            delta_m = None if prev_mid is None else depth["mid"] - prev_mid
            st.metric("Mid", f"{depth['mid']:,.2f}", None if delta_m is None else f"{delta_m:+.2f}")

            k1, k2 = st.columns(2)
            k1.metric("Spread", f"{depth['spread']:,.4f}")
            k2.metric("相對價差", f"{depth['rel_spread_bps']:,.1f} bps")

            # Bid / Ask 顏色
            arw, col = arrow_and_color(depth["best_bid_price"], prev_bid)
            st.markdown(f"<b>最佳買一：</b> <span style='color:{col}'>{depth['best_bid_price']:,.2f} {arw}</span><br/>"
                        f"數量：{depth['best_bid_size']}", unsafe_allow_html=True)
            arw, col = arrow_and_color(depth["best_ask_price"], prev_ask)
            st.markdown(f"<b>最佳賣一：</b> <span style='color:{col}'>{depth['best_ask_price']:,.2f} {arw}</span><br/>"
                        f"數量：{depth['best_ask_size']}", unsafe_allow_html=True)

        # 中：走勢（mid）
        with cols[1]:
            st.markdown("**價格走勢（mid）**")
            df = pd.DataFrame(st.session_state.history[sym])
            if not df.empty:
                df = df.set_index("ts")
                st.line_chart(df[["mid"]])
            else:
                st.info("等待累積資料…")

        # 右：深度表
        with cols[2]:
            st.markdown(f"**訂單簿前 {depth_limit} 檔**")
            bids_df = pd.DataFrame(depth["bids"], columns=["Bid Price", "Bid Size"]).astype(float)
            asks_df = pd.DataFrame(depth["asks"], columns=["Ask Price", "Ask Size"]).astype(float)
            bids_df = bids_df.sort_values("Bid Price", ascending=False).head(depth_limit)
            asks_df = asks_df.sort_values("Ask Price", ascending=True).head(depth_limit)

            c1, c2 = st.columns(2)
            with c1:
                st.caption("Bids")
                st.dataframe(bids_df, height=260, use_container_width=True)
            with c2:
                st.caption("Asks")
                st.dataframe(asks_df, height=260, use_container_width=True)

        st.markdown("---")
