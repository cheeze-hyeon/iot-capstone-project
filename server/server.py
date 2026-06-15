"""HOTO 저울 + 아두이노(LED/버튼) -> WebSocket 브로드캐스트 서버.

저울에 연결해서 무게를 읽고, ws://localhost:8765 로 연결한 모든 클라이언트에게
{"weight": 73.5, "stabilized": true, "state": "IDLE"|"READY", "tare": .., "refill": ..}
형태의 JSON을 실시간으로 보낸다.

아두이노 버튼을 누르면 현재 무게를 tare로 저장하고 상태를 READY로 바꾸며,
아두이노 LED를 빨강(IDLE) / 파랑(READY)으로 전환한다.
"""
import asyncio
import json
import logging
import os
import sys
import threading
import time

import serial
import websockets
from bleak import BleakScanner

from hoto import HotoScale

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("server")

MAC = "EC:4D:3E:DB:EA:F3"
TOKEN = bytes.fromhex("257f0168308a7c6002f2f6bc")

FE95 = "0000fe95-0000-1000-8000-00805f9b34fb"
TARGET_MAC_SUFFIX = "f3eadb3e4dec"

ARDUINO_PORT = "/dev/cu.usbmodem11101"
ARDUINO_BAUD = 9600

clients = set()

# 리필 상태
# WAIT_CARD(red, 카드 태그 대기) -> IDLE(red, 용기+버튼 대기) -> READY(blue, 리필 중)
station_state = "WAIT_CARD"
tare = None
last_weight = None
last_stabilized = False
last_connected = False
arduino_serial = None


async def broadcast(message: dict):
    if not clients:
        return
    data = json.dumps(message, ensure_ascii=False)
    await asyncio.gather(*(c.send(data) for c in list(clients)), return_exceptions=True)


async def broadcast_status():
    refill = (last_weight - tare) if (last_weight is not None and tare is not None) else None
    await broadcast({
        "connected": last_connected,
        "weight": last_weight,
        "stabilized": last_stabilized,
        "state": station_state,
        "tare": tare,
        "refill": refill,
    })


async def reset_station():
    """다음 손님을 위해 상태 초기화: 카드 태그 대기(WAIT_CARD)로 복귀."""
    global station_state, tare
    station_state = "WAIT_CARD"
    tare = None
    if arduino_serial is not None:
        arduino_serial.write(b"LED:OFF\n")
        arduino_serial.write(b"SERVO:CLOSE\n")
    log.info("리셋: state=WAIT_CARD")
    await broadcast_status()


def restart_process():
    """현재 프로세스를 동일한 인자로 재실행 (BLE 스캐너 등 전체 초기화)."""
    log.warning("프로세스 재시작: %s", sys.argv)
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def ws_handler(websocket):
    clients.add(websocket)
    log.info("client connected (%d total)", len(clients))
    await broadcast_status()
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue
            if data.get("action") == "reset":
                await reset_station()
            elif data.get("action") == "restart_server":
                log.warning("클라이언트 요청으로 서버 재시작")
                asyncio.get_event_loop().call_later(0.3, restart_process)
    finally:
        clients.discard(websocket)
        log.info("client disconnected (%d total)", len(clients))


async def scale_loop():
    loop = asyncio.get_running_loop()
    scale = HotoScale(MAC, TOKEN, idle_timeout=None)

    def on_state(state):
        global last_weight, last_stabilized, last_connected
        log.info("STATE: %s", state)
        last_weight = state.weight
        last_stabilized = state.stabilized
        last_connected = state.connected
        asyncio.run_coroutine_threadsafe(broadcast_status(), loop)

    scale.register_callback(on_state)

    def detection_cb(device, adv):
        sd = adv.service_data or {}
        raw = sd.get(FE95)
        if raw:
            log.info("FE95 adv from %s: %s", device.address, raw.hex())
        if raw and raw[5:11].hex() == TARGET_MAC_SUFFIX:
            log.info("scale advert matched, signaling available")
            scale.signal_available(device)

    scanner = BleakScanner(detection_callback=detection_cb)
    await scanner.start()
    await scale.async_start()

    try:
        await asyncio.Future()  # run forever
    finally:
        await scale.async_stop()
        await scanner.stop()


def arduino_loop(loop):
    global station_state, tare, arduino_serial

    while True:
        try:
            ser = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
        except serial.SerialException:
            log.warning("아두이노(%s) 연결 실패, 3초 후 재시도", ARDUINO_PORT)
            arduino_serial = None
            time.sleep(3)
            continue

        log.info("아두이노 연결됨 (%s)", ARDUINO_PORT)
        arduino_serial = ser
        ser.write(b"LED:OFF\n")

        try:
            while True:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                if line.startswith("CARD:"):
                    uid = line[len("CARD:"):]
                    if station_state == "WAIT_CARD":
                        station_state = "IDLE"
                        ser.write(b"LED:RED\n")
                        log.info("카드 태그: uid=%s, state=IDLE", uid)
                        asyncio.run_coroutine_threadsafe(broadcast({"event": "CARD_TAGGED", "uid": uid}), loop)
                        asyncio.run_coroutine_threadsafe(broadcast_status(), loop)
                    continue

                if line != "BUTTON_PRESSED":
                    continue

                if station_state == "IDLE":
                    tare = last_weight
                    station_state = "READY"
                    ser.write(b"LED:BLUE\n")
                    ser.write(b"SERVO:OPEN\n")
                    log.info("버튼 눌림: tare=%s, state=READY", tare)
                    asyncio.run_coroutine_threadsafe(broadcast_status(), loop)
                elif station_state == "READY":  # 리필 완료 신호
                    ser.write(b"SERVO:CLOSE\n")
                    ser.write(b"BEEP\n")
                    log.info("버튼 눌림: 리필 완료")
                    asyncio.run_coroutine_threadsafe(broadcast({"event": "REFILL_DONE"}), loop)
        except serial.SerialException:
            log.warning("아두이노 연결 끊김, 재연결 시도")
            arduino_serial = None
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(3)


async def main():
    loop = asyncio.get_running_loop()
    threading.Thread(target=arduino_loop, args=(loop,), daemon=True).start()

    async with websockets.serve(ws_handler, "localhost", 8765):
        log.info("WebSocket server listening on ws://localhost:8765")
        await scale_loop()


if __name__ == "__main__":
    asyncio.run(main())
