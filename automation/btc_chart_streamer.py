#!/usr/bin/env python3
"""ChloeOS Autonomous Live Bitcoin Chart Streamer (Cloud Worker Edition).

Polls real-time Binance BTC/USDT market data & 1-minute candlesticks,
renders a live dark-mode visual financial display, and streams directly
to Livepush RTMP ingest at 720p 25fps with constant GOP & audio carrier.
"""

import os
import sys
import time
import json
import shutil
import signal
import threading
import subprocess
import urllib.request
from datetime import datetime, timezone

RSVG_BIN = shutil.which("rsvg-convert") or "/usr/bin/rsvg-convert"
STATE_FILE = "/tmp/btc_state.json"

market_lock = threading.Lock()
market_data = {
    "price": 77800.0,
    "change": 0.0,
    "high": 78000.0,
    "low": 76000.0,
    "volume": 20000.0,
    "candles": [],
    "last_update": time.time(),
    "frames_sent": 0
}

running = True

def handle_signal(sig, frame):
    global running
    print(f"\n[STREAM-WORKER] Received signal {sig}. Initiating graceful shutdown...", flush=True)
    running = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

def fetch_market_loop():
    global running
    while running:
        try:
            # 1. Ticker 24h
            t_url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
            req = urllib.request.Request(t_url, headers={"User-Agent": "Mozilla/5.0 (ChloeOS Cloud)"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                t_json = json.loads(resp.read().decode())
                p = float(t_json["lastPrice"])
                ch = float(t_json["priceChangePercent"])
                hi = float(t_json["highPrice"])
                lo = float(t_json["lowPrice"])
                vol = float(t_json["volume"])

            # 2. Klines (1m candles, 35 count)
            k_url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=35"
            req2 = urllib.request.Request(k_url, headers={"User-Agent": "Mozilla/5.0 (ChloeOS Cloud)"})
            with urllib.request.urlopen(req2, timeout=5) as resp2:
                k_json = json.loads(resp2.read().decode())
                candles = []
                for k in k_json:
                    candles.append({
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4])
                    })

            with market_lock:
                market_data["price"] = p
                market_data["change"] = ch
                market_data["high"] = hi
                market_data["low"] = lo
                market_data["volume"] = vol
                market_data["candles"] = candles
                market_data["last_update"] = time.time()

            try:
                with open(STATE_FILE, "w") as sf:
                    json.dump({
                        "price": p,
                        "change": ch,
                        "high": hi,
                        "low": lo,
                        "volume": vol,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "frames_sent": market_data["frames_sent"]
                    }, sf)
            except Exception:
                pass

        except Exception as e:
            pass
        time.sleep(1.5)

def render_svg(state, pulse):
    p = state["price"]
    ch = state["change"]
    hi = state["high"]
    lo = state["low"]
    vol = state["volume"]
    candles = state["candles"]

    color = "#00ffa3" if ch >= 0 else "#ff3b69"
    sign = "+" if ch >= 0 else ""
    pulse_opacity = "1.0" if pulse else "0.3"

    W, H = 1280, 720
    gx, gy, gw, gh = 70, 220, 1100, 440

    if candles:
        min_p = min(c["low"] for c in candles)
        max_p = max(c["high"] for c in candles)
    else:
        min_p, max_p = p * 0.995, p * 1.005
    p_range = max(max_p - min_p, 5.0)

    def to_y(val):
        return gy + gh - int((val - min_p) / p_range * gh)

    candle_svg = []
    if candles:
        step = gw / len(candles)
        bw = max(int(step * 0.65), 5)
        for i, c in enumerate(candles):
            cx = int(gx + i * step + step / 2)
            y_h = to_y(c["high"])
            y_l = to_y(c["low"])
            y_o = to_y(c["open"])
            y_c = to_y(c["close"])
            c_col = "#00ffa3" if c["close"] >= c["open"] else "#ff3b69"
            
            candle_svg.append(f'<line x1="{cx}" y1="{y_h}" x2="{cx}" y2="{y_l}" stroke="{c_col}" stroke-width="2" opacity="0.8" />')
            top_y = min(y_o, y_c)
            b_h = max(abs(y_c - y_o), 2)
            candle_svg.append(f'<rect x="{cx - bw//2}" y="{top_y}" width="{bw}" height="{b_h}" fill="{c_col}" rx="2" />')

    grid_svg = []
    for div in range(5):
        gp = min_p + (p_range * div / 4.0)
        gy_pos = to_y(gp)
        grid_svg.append(f'<line x1="{gx}" y1="{gy_pos}" x2="{gx+gw}" y2="{gy_pos}" stroke="#161c28" stroke-width="1" stroke-dasharray="4,4" />')
        grid_svg.append(f'<text x="{gx+gw+12}" y="{gy_pos+4}" fill="#54657e" font-family="monospace" font-size="12">${gp:,.1f}</text>')

    cur_y = to_y(p)
    cur_line = f'''<line x1="{gx}" y1="{cur_y}" x2="{gx+gw}" y2="{cur_y}" stroke="{color}" stroke-width="1.5" stroke-dasharray="6,4" opacity="0.95" />
<rect x="{gx+gw+5}" y="{cur_y-10}" width="95" height="20" fill="{color}" rx="3" />
<text x="{gx+gw+12}" y="{cur_y+4}" fill="#080a0f" font-family="monospace" font-size="12" font-weight="bold">${p:,.2f}</text>'''

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    svg = f'''<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0b0e14" />
      <stop offset="100%" stop-color="#05070a" />
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)" />
  
  <rect x="0" y="0" width="{W}" height="68" fill="#0d121b" />
  <line x1="0" y1="68" x2="{W}" y2="68" stroke="#1c2436" stroke-width="1" />
  
  <text x="40" y="43" fill="#ffffff" font-family="sans-serif" font-size="22" font-weight="bold" letter-spacing="1">CHLOE<tspan fill="#f7931a">OS</tspan> // BITCOIN LIVE RADAR <tspan fill="#f7931a">[BTC / USD]</tspan></text>
  
  <circle cx="{W-240}" cy="36" r="6" fill="#00ffa3" opacity="{pulse_opacity}" />
  <text x="{W-225}" y="41" fill="#00ffa3" font-family="sans-serif" font-size="13" font-weight="bold" letter-spacing="1">● LIVE STREAM</text>
  <text x="{W-40}" y="41" fill="#8899aa" font-family="monospace" font-size="13" text-anchor="end">{ts}</text>
  
  <g transform="translate(70, 95)">
    <rect x="0" y="2" width="32" height="32" rx="16" fill="#f7931a" />
    <text x="16" y="25" fill="#ffffff" font-family="sans-serif" font-size="20" font-weight="bold" text-anchor="middle">₿</text>
    
    <text x="42" y="24" fill="#ffffff" font-family="sans-serif" font-size="20" font-weight="bold" letter-spacing="1">BITCOIN</text>
    <rect x="145" y="6" width="95" height="24" rx="4" fill="#f7931a" opacity="0.2" />
    <text x="192" y="23" fill="#f7931a" font-family="monospace" font-size="14" font-weight="bold" text-anchor="middle">BTC / USD</text>
    <text x="252" y="23" fill="#71829e" font-family="monospace" font-size="13">• BINANCE SPOT • 1M REAL-TIME CANDLES</text>
    
    <text x="0" y="85" fill="#ffffff" font-family="monospace" font-size="52" font-weight="bold">${p:,.2f}</text>
    <text x="325" y="83" fill="#71829e" font-family="monospace" font-size="16">USD</text>
    
    <rect x="380" y="52" width="115" height="36" rx="6" fill="{color}" opacity="0.16" />
    <text x="437" y="76" fill="{color}" font-family="monospace" font-size="18" font-weight="bold" text-anchor="middle">{sign}{ch:.2f}%</text>
  </g>
  
  <g transform="translate(680, 125)">
    <text x="0" y="14" fill="#62728f" font-family="sans-serif" font-size="12">24H HIGH</text>
    <text x="0" y="40" fill="#ffffff" font-family="monospace" font-size="18" font-weight="bold">${hi:,.2f}</text>
    
    <text x="170" y="14" fill="#62728f" font-family="sans-serif" font-size="12">24H LOW</text>
    <text x="170" y="40" fill="#ffffff" font-family="monospace" font-size="18" font-weight="bold">${lo:,.2f}</text>
    
    <text x="340" y="14" fill="#62728f" font-family="sans-serif" font-size="12">24H VOLUME</text>
    <text x="340" y="40" fill="#ffffff" font-family="monospace" font-size="18" font-weight="bold">{vol:,.0f} BTC</text>
  </g>
  
  <rect x="{gx}" y="{gy}" width="{gw}" height="{gh}" fill="#080a0f" stroke="#1c2436" stroke-width="1" rx="4" />
  {"".join(grid_svg)}
  {"".join(candle_svg)}
  {cur_line}
  
  <line x1="0" y1="{H-35}" x2="{W}" y2="{H-35}" stroke="#1c2436" stroke-width="1" />
  <text x="40" y="{H-14}" fill="#54657e" font-family="sans-serif" font-size="12">ChloeOS Cloud Worker • Autonomous Broadcast Node</text>
  <text x="{W-40}" y="{H-14}" fill="#00ffa3" font-family="monospace" font-size="12" text-anchor="end">RTMP UPLINK • LIVEPUSH</text>
</svg>'''
    return svg

def run_stream():
    global running
    endpoint = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].strip() else os.environ.get("RTMP_URL", "").strip()
    
    if not endpoint:
        print("[STREAM-WORKER] ERROR: No RTMP endpoint provided!", file=sys.stderr)
        print("Usage: python3 btc_chart_streamer.py <RTMP_URL> (or set RTMP_URL env variable)", file=sys.stderr)
        sys.exit(1)

    masked_url = endpoint
    if "/live/" in endpoint:
        parts = endpoint.split("/live/")
        masked_url = parts[0] + "/live/" + parts[1][:6] + "..." + parts[1][-4:]
    print(f"[STREAM-WORKER] Target RTMP: {masked_url}", flush=True)

    if not shutil.which(RSVG_BIN) and not os.path.exists(RSVG_BIN):
        print(f"[STREAM-WORKER] ERROR: rsvg-convert not found at {RSVG_BIN}!", file=sys.stderr)
        sys.exit(1)

    t = threading.Thread(target=fetch_market_loop, daemon=True)
    t.start()
    time.sleep(1.0)

    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner",
        "-f", "image2pipe", "-r", "1", "-i", "-",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-r", "25", "-g", "50", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-f", "flv", endpoint
    ]

    print("[STREAM-WORKER] Launching FFmpeg broadcast pipeline...", flush=True)
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    pulse = False
    last_log_time = time.time()
    try:
        while running and proc.poll() is None:
            t0 = time.time()
            pulse = not pulse
            
            with market_lock:
                state_copy = {
                    "price": market_data["price"],
                    "change": market_data["change"],
                    "high": market_data["high"],
                    "low": market_data["low"],
                    "volume": market_data["volume"],
                    "candles": list(market_data["candles"])
                }

            svg = render_svg(state_copy, pulse)
            
            p_conv = subprocess.run(
                [RSVG_BIN, "-f", "png", "-"],
                input=svg.encode("utf-8"),
                capture_output=True,
                check=True
            )
            png_bytes = p_conv.stdout

            proc.stdin.write(png_bytes)
            proc.stdin.flush()
            market_data["frames_sent"] += 1

            if time.time() - last_log_time >= 60:
                print(f"[STREAM-WORKER] Uptime active | BTC: ${state_copy['price']:,.2f} | Frames: {market_data['frames_sent']}", flush=True)
                last_log_time = time.time()

            elapsed = time.time() - t0
            sleep_time = max(1.0 - elapsed, 0.05)
            time.sleep(sleep_time)

    except Exception as e:
        print(f"[STREAM-WORKER] Loop exception: {e}", file=sys.stderr)
    finally:
        print("[STREAM-WORKER] Shutting down FFmpeg pipeline...", flush=True)
        running = False
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        print(f"[STREAM-WORKER] Shutdown complete. Total frames pushed: {market_data['frames_sent']}", flush=True)

if __name__ == "__main__":
    run_stream()
