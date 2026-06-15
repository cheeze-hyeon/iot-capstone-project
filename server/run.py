"""HOTO 스마트 저울 - 독립 실행 스크립트.

Mi Cloud에서 얻은 device token으로 mible secure-login handshake를 수행하고
무게 데이터를 실시간으로 출력한다.

사용법:
    python3 run.py <MAC주소> <TOKEN_HEX>
"""
import asyncio
import logging
import sys

from bleak import BleakScanner

from hoto import HotoScale

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

FE95 = "0000fe95-0000-1000-8000-00805f9b34fb"
# EC:4D:3E:DB:EA:F3 -> reversed byte order as it appears in the FE95 service data
TARGET_MAC_SUFFIX = "f3eadb3e4dec"


async def main():
    mac = sys.argv[1]
    token = bytes.fromhex(sys.argv[2])

    found = {}

    def cb(device, adv):
        sd = adv.service_data or {}
        raw = sd.get(FE95)
        if raw and raw[5:11].hex() == TARGET_MAC_SUFFIX:
            found["device"] = device

    print(f"{mac} 스캔 중... 저울을 건드려서 깨워주세요. (최대 60초)")
    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    for _ in range(60):
        if "device" in found:
            break
        await asyncio.sleep(1)
    await scanner.stop()

    device = found.get("device")
    if device is None:
        print("기기를 찾지 못했습니다.")
        return

    print(f"기기 발견: {device.address}")
    scale = HotoScale(device.address, token, idle_timeout=None)
    scale.register_callback(lambda s: print("STATE:", s))

    scale.signal_available(device)
    await scale.async_start()
    try:
        await asyncio.sleep(120)
    finally:
        await scale.async_stop()


if __name__ == "__main__":
    asyncio.run(main())
