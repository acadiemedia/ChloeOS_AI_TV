#!/usr/bin/env python3
"""ChloeOS Autonomous Live Bitcoin Chart Streamer (Cloud Worker Edition).

Polls real-time Coinbase / Kraken market data & 1-minute candlesticks,
renders a live dark-mode visual financial display with volume sub-bars,
and streams directly to Livepush RTMP ingest at 720p 25fps.
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
    "price": 0.0,
    "change": 0.0,
    "high": 0.0,
    "low": 0.0,
    "volume": 0.0,
    "candles": [],
    "source": "INITIALIZING",
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

def fetch_coinbase():
    # 1. 24h Stats
    u_stats = "https://api.exchange.coinbase.com/products/BTC-USD/stats"
    req_s = urllib.request.Request(u_stats, headers={"User-Agent": "ChloeOS/Cloud"})
    with urllib.request.urlopen(req_s, timeout=4) as resp:
        stats = json.loads(resp.read().decode())
        last_p = float(stats["last"])
        open_p = float(stats["open"])
        high_p = float(stats["high"])
        low_p = float(stats["low"])
        vol_p = float(stats["volume"])
        change_pct = ((last_p - open_p) / open_p) * 100.0 if open_p > 0 else 0.0

    # 2. 1-minute Candlesticks (granularity=60)
    u_candles = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"
    req_c = urllib.request.Request(u_candles, headers={"User-Agent": "ChloeOS/Cloud"})
    with urllib.request.urlopen(req_c, timeout=4) as resp2:
        raw_c = json.loads(resp2.read().decode())
        # raw: [time, low, high, open, close, volume] (newest first)
        c_slice = raw_c[:35][::-1]  # reverse to chronological (oldest to newest)
        candles = []
        for c in c_slice:
            candles.append({
                "time": int(c[0]),
                "low": float(c[1]),
                "high": float(c[2]),
                "open": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5])
            })

    return {
        "price": last_p,
        "change": change_pct,
        "high": high_p,
        "low": low_p,
        "volume": vol_p,
        "candles": candles,
        "source": "COINBASE SPOT"
    }

def fetch_kraken():
    # Fallback to Kraken if Coinbase fails
    u_ticker = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"
    req_t = urllib.request.Request(u_ticker, headers={"User-Agent": "ChloeOS/Cloud"})
    with urllib.request.urlopen(req_t, timeout=4) as resp:
        data_t = json.loads(resp.read().decode())["result"]["XXBTZUSD"]
        last_p = float(data_t["c"][0])
        high_p = float(data_t["h"][1])
        low_p = float(data_t["l"][1])
        vol_p = float(data_t["v"][1])
        open_p = float(data_t["o"])
        change_pct = ((last_p - open_p) / open_p) * 100.0 if open_p > 0 else 0.0

    u_ohlc = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1"
    req_o = urllib.request.Request(u_ohlc, headers={"User-Agent": "ChloeOS/Cloud"})
    with urllib.request.urlopen(req_o, timeout=4) as resp2:
        raw_k = json.loads(resp2.read().decode())["result"]["XXBTZUSD"]
        c_slice = raw_k[-35:]
        candles = []
        for c in c_slice:
            candles.append({
                "time": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[6])
            })

    return {
        "price": last_p,
        "change": change_pct,
        "high": high_p,
        "low": low_p,
        "volume": vol_p,
        "candles": candles,
        "source": "KRAKEN SPOT"
    }

def fetch_market_loop():
    global running
    first_fetch = True
    while running:
        fetched = None
        # 1. Try Coinbase
        try:
            fetched = fetch_coinbase()
        except Exception as e1:
            # 2. Fallback to Kraken
            try:
                fetched = fetch_kraken()
            except Exception as e2:
                print(f"[STREAM-WORKER] Data fetch failed. Coinbase: {e1} | Kraken: {e2}", file=sys.stderr)

        if fetched:
            with market_lock:
                market_data["price"] = fetched["price"]
                market_data["change"] = fetched["change"]
                market_data["high"] = fetched["high"]
                market_data["low"] = fetched["low"]
                market_data["volume"] = fetched["volume"]
                market_data["candles"] = fetched["candles"]
                market_data["source"] = fetched["source"]
                market_data["last_update"] = time.time()

            if first_fetch:
                print(f"[STREAM-WORKER] Initial Market Sync: ${fetched['price']:,.2f} | {len(fetched['candles'])} candles | Source: {fetched['source']}", flush=True)
                first_fetch = False

            try:
                with open(STATE_FILE, "w") as sf:
                    json.dump({
                        "price": fetched["price"],
                        "change": fetched["change"],
                        "high": fetched["high"],
                        "low": fetched["low"],
                        "volume": fetched["volume"],
                        "candles_count": len(fetched["candles"]),
                        "source": fetched["source"],
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "frames_sent": market_data["frames_sent"]
                    }, sf)
            except Exception:
                pass

        time.sleep(1.5)

def get_current_track_info(manifest, elapsed_sec):
    if not manifest:
        return "CHLOEOS ORIGINAL SOUNDTRACK", "", ""
    total_duration = sum(t.get("duration", 180.0) for t in manifest)
    if total_duration <= 0:
        return "CHLOEOS ORIGINAL SOUNDTRACK", "", ""
    
    current_time = elapsed_sec % total_duration
    accum = 0.0
    for t in manifest:
        d = t.get("duration", 180.0)
        if accum + d > current_time:
            track_pos = current_time - accum
            pos_m, pos_s = divmod(int(track_pos), 60)
            len_m, len_s = divmod(int(d), 60)
            return t["title"], f"{pos_m:02d}:{pos_s:02d}", f"{len_m:02d}:{len_s:02d}"
        accum += d
    return manifest[0]["title"], "00:00", "00:00"

def render_svg(state, pulse, track_title="", track_pos="", track_len=""):
    p = state["price"]
    ch = state["change"]
    hi = state["high"]
    lo = state["low"]
    vol = state["volume"]
    candles = state["candles"]
    src = state.get("source", "COINBASE SPOT")

    color = "#00ffa3" if ch >= 0 else "#ff3b69"
    sign = "+" if ch >= 0 else ""
    pulse_opacity = "1.0" if pulse else "0.3"

    W, H = 1280, 720
    gx, gy, gw, gh = 70, 215, 1100, 435

    if candles:
        min_p = min(c["low"] for c in candles)
        max_p = max(c["high"] for c in candles)
        max_vol = max((c.get("volume", 0) for c in candles), default=1.0)
    else:
        min_p = p * 0.998 if p > 0 else 70000.0
        max_p = p * 1.002 if p > 0 else 71000.0
        max_vol = 1.0

    p_range = max(max_p - min_p, 8.0)
    # Add 8% vertical padding so wicks don't touch edges
    chart_min = min_p - (p_range * 0.05)
    chart_max = max_p + (p_range * 0.05)
    chart_range = chart_max - chart_min

    def to_y(val):
        return gy + gh - int((val - chart_min) / chart_range * gh)

    candle_svg = []
    volume_svg = []
    time_axis_svg = []
    if candles:
        step = gw / len(candles)
        bw = max(int(step * 0.62), 4)
        for i, c in enumerate(candles):
            cx = int(gx + i * step + step / 2)
            y_h = to_y(c["high"])
            y_l = to_y(c["low"])
            y_o = to_y(c["open"])
            y_c = to_y(c["close"])
            c_col = "#00ffa3" if c["close"] >= c["open"] else "#ff3b69"
            
            # Wicks
            candle_svg.append(f'<line x1="{cx}" y1="{y_h}" x2="{cx}" y2="{y_l}" stroke="{c_col}" stroke-width="2" opacity="0.85" />')
            
            # Candle Body
            top_y = min(y_o, y_c)
            b_h = max(abs(y_c - y_o), 3)
            candle_svg.append(f'<rect x="{cx - bw//2}" y="{top_y}" width="{bw}" height="{b_h}" fill="{c_col}" rx="2" />')

            # Volume sub-bar at bottom of chart
            if max_vol > 0:
                v_h = max(int((c.get("volume", 0) / max_vol) * 55), 2)
                v_y = gy + gh - v_h
                volume_svg.append(f'<rect x="{cx - bw//2}" y="{v_y}" width="{bw}" height="{v_h}" fill="{c_col}" opacity="0.22" rx="1" />')

            # Time scale ticks & labels along bottom axis
            if i % 5 == 0 or i == len(candles) - 1:
                t_val = c.get("time", time.time())
                t_str = datetime.fromtimestamp(t_val, tz=timezone.utc).strftime("%H:%M")
                time_axis_svg.append(f'<line x1="{cx}" y1="{gy}" x2="{cx}" y2="{gy+gh}" stroke="#141923" stroke-width="1" stroke-dasharray="3,3" />')
                time_axis_svg.append(f'<line x1="{cx}" y1="{gy+gh}" x2="{cx}" y2="{gy+gh+5}" stroke="#2e3d56" stroke-width="1" />')
                time_axis_svg.append(f'<text x="{cx}" y="{gy+gh+18}" fill="#6b7d99" font-family="monospace" font-size="11" text-anchor="middle">{t_str}</text>')

    grid_svg = []
    for div in range(5):
        gp = chart_min + (chart_range * div / 4.0)
        gy_pos = to_y(gp)
        grid_svg.append(f'<line x1="{gx}" y1="{gy_pos}" x2="{gx+gw}" y2="{gy_pos}" stroke="#161c28" stroke-width="1" stroke-dasharray="4,4" />')
        grid_svg.append(f'<text x="{gx+gw+12}" y="{gy_pos+4}" fill="#54657e" font-family="monospace" font-size="12">${gp:,.1f}</text>')

    cur_y = to_y(p) if p > 0 else gy + gh // 2
    cur_line = f'''<line x1="{gx}" y1="{cur_y}" x2="{gx+gw}" y2="{cur_y}" stroke="{color}" stroke-width="1.5" stroke-dasharray="6,4" opacity="0.95" />
<rect x="{gx+gw+5}" y="{cur_y-10}" width="95" height="20" fill="{color}" rx="3" />
<text x="{gx+gw+12}" y="{cur_y+4}" fill="#080a0f" font-family="monospace" font-size="12" font-weight="bold">${p:,.2f}</text>'''

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if track_title:
        if track_pos and track_len:
            audio_display = f'<text x="40" y="{H-10}" fill="#00ffa3" font-family="sans-serif" font-size="12" font-weight="bold">♫ NOW PLAYING: <tspan fill="#ffffff">{track_title}</tspan> <tspan fill="#71829e">[{track_pos} / {track_len}]</tspan></text>'
        else:
            audio_display = f'<text x="40" y="{H-10}" fill="#00ffa3" font-family="sans-serif" font-size="12" font-weight="bold">♫ NOW PLAYING: <tspan fill="#ffffff">{track_title}</tspan></text>'
    else:
        audio_display = f'<text x="40" y="{H-10}" fill="#00ffa3" font-family="sans-serif" font-size="12">♫ CHLOEOS RADIO // COMPLETE ORIGINAL SOUNDTRACK [33 TRACKS]</text>'

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
  
  <text x="40" y="42" fill="#ffffff" font-family="sans-serif" font-size="20" font-weight="bold" letter-spacing="1">CHLOE<tspan fill="#f7931a">OS</tspan> // BITCOIN LIVE RADAR <tspan fill="#f7931a">[BTC / USD]</tspan></text>
  
  <g transform="translate({W-380}, 22)">
    <rect x="0" y="0" width="115" height="26" rx="13" fill="#00ffa3" opacity="0.12" stroke="#00ffa3" stroke-width="1" />
    <circle cx="16" cy="13" r="4" fill="#00ffa3" opacity="{pulse_opacity}" />
    <text x="28" y="17" fill="#00ffa3" font-family="sans-serif" font-size="11" font-weight="bold" letter-spacing="1">LIVE STREAM</text>
  </g>
  
  <text x="{W-40}" y="40" fill="#8899aa" font-family="monospace" font-size="13" text-anchor="end">{ts}</text>
  
  <g transform="translate(70, 95)">
    <rect x="0" y="2" width="32" height="32" rx="16" fill="#f7931a" />
    <text x="16" y="25" fill="#ffffff" font-family="sans-serif" font-size="20" font-weight="bold" text-anchor="middle">₿</text>
    
    <text x="42" y="24" fill="#ffffff" font-family="sans-serif" font-size="20" font-weight="bold" letter-spacing="1">BITCOIN</text>
    <rect x="145" y="6" width="95" height="24" rx="4" fill="#f7931a" opacity="0.2" />
    <text x="192" y="23" fill="#f7931a" font-family="monospace" font-size="14" font-weight="bold" text-anchor="middle">BTC / USD</text>
    <text x="252" y="23" fill="#71829e" font-family="monospace" font-size="13">• {src} • 1M REAL-TIME CANDLES</text>
    
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
  {"".join(time_axis_svg)}
  {"".join(volume_svg)}
  {"".join(candle_svg)}
  {cur_line}
  
  <line x1="0" y1="{H-28}" x2="{W}" y2="{H-28}" stroke="#1c2436" stroke-width="1" />
  {audio_display}
  <text x="{W-40}" y="{H-10}" fill="#00ffa3" font-family="monospace" font-size="12" text-anchor="end">RTMP UPLINK • LIVEPUSH</text>
</svg>'''
    return svg

def run_stream():
    global running
    endpoint = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].strip() else os.environ.get("RTMP_URL", "").strip()
    
    if not endpoint:
        print("[STREAM-WORKER] ERROR: No RTMP endpoint provided!", file=sys.stderr)
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

    # Wait up to 5s for first market payload
    print("[STREAM-WORKER] Awaiting initial market data...", flush=True)
    for _ in range(25):
        with market_lock:
            if market_data["price"] > 0:
                break
    audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
    playlist_path = os.path.join(audio_dir, "playlist.txt")
    manifest_path = os.path.join(audio_dir, "manifest.json")
    mp3_files = sorted([f for f in os.listdir(audio_dir) if f.lower().endswith(".mp3")]) if os.path.exists(audio_dir) else []

    audio_manifest = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as mf:
                audio_manifest = json.load(mf)
            print(f"[STREAM-WORKER] Audio Engine: Loaded track metadata for {len(audio_manifest)} songs.", flush=True)
        except Exception as e:
            print(f"[STREAM-WORKER] Audio manifest warning: {e}", file=sys.stderr)

    if mp3_files:
        try:
            with open(playlist_path, "w") as pf:
                for m in mp3_files:
                    full_p = os.path.abspath(os.path.join(audio_dir, m))
                    pf.write(f"file '{full_p}'\n")
            print(f"[STREAM-WORKER] Audio Engine: Loaded {len(mp3_files)} original soundtrack files into playlist.", flush=True)
            audio_inputs = [
                "-stream_loop", "-1",
                "-f", "concat",
                "-safe", "0",
                "-i", playlist_path
            ]
        except Exception as e:
            print(f"[STREAM-WORKER] Playlist error: {e}. Falling back to silence.", file=sys.stderr)
            audio_inputs = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    else:
        print("[STREAM-WORKER] No local audio found. Using synthetic carrier.", flush=True)
        audio_inputs = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner",
        "-f", "image2pipe", "-r", "1", "-i", "-",
        *audio_inputs,
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-r", "25", "-g", "50", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-f", "flv", endpoint
    ]

    print("[STREAM-WORKER] Launching FFmpeg broadcast pipeline...", flush=True)
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    pulse = False
    last_log_time = time.time()
    stream_start_time = time.time()
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
                    "candles": list(market_data["candles"]),
                    "source": market_data["source"]
                }

            elapsed_audio = time.time() - stream_start_time
            track_title, track_pos, track_len = get_current_track_info(audio_manifest, elapsed_audio)

            svg = render_svg(state_copy, pulse, track_title, track_pos, track_len)
            
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
                print(f"[STREAM-WORKER] Active | {state_copy['source']} | BTC: ${state_copy['price']:,.2f} | Candles: {len(state_copy['candles'])} | Frames: {market_data['frames_sent']}", flush=True)
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
