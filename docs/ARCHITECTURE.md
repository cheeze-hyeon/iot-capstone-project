# 알록 리필 스테이션 — 기술 구성도

## 시스템 구성

```
┌──────────────┐  BLE (HKDF/AES-CCM)  ┌──────────────────┐
│ HOTO 스마트저울 │ ────────────────────▶ │                  │
└──────────────┘                       │                  │   WebSocket    ┌──────────────┐
                                        │   server.py      │ ──────────────▶│  pos.html     │
┌──────────────┐  USB Serial (9600bps) │  (Python)        │  ws://localhost │  (브라우저 키오스크) │
│  Arduino Uno  │ ────────────────────▶ │                  │      :8765      │              │
│  (LED/버튼/    │ ◀──────────────────── │                  │                └──────────────┘
│   RFID/서보/   │                       └──────────────────┘
│   부저)        │
└──────────────┘
```

- **HOTO 스마트저울**: BLE로 무게 데이터를 전송. `hoto.py`의 `HotoScale` 클래스가 핸드셰이크/복호화 담당.
- **Arduino Uno**: LED 2개, 버튼, RC522 RFID 리더, 서보모터, 부저를 제어. `refill_station_rfid/refill_station_rfid.ino`.
- **server.py**: BLE 저울 + 아두이노 시리얼을 동시에 처리하며, 통합 상태를 WebSocket으로 브로드캐스트.
- **pos.html**: 키오스크 UI. WebSocket으로 서버에 연결, 상태에 따라 화면 전환.

## 파일 구조

| 파일 | 역할 |
|---|---|
| `server/server.py` | 메인 서버: BLE 스캐너/저울 드라이버 + 아두이노 시리얼 + WebSocket 서버 |
| `server/hoto.py` | HOTO 저울 BLE 프로토콜 구현 (핸드셰이크, 무게 파싱, 복호화) |
| `server/const.py` | UUID, HKDF info 등 상수 (`hoto.py` 의존성) |
| `server/run.py` | 저울 단독 연결 테스트 스크립트 |
| `server/test_client.py` | WebSocket 메시지 확인용 디버그 클라이언트 |
| `firmware/refill_station_rfid/refill_station_rfid.ino` | 아두이노 펌웨어 |
| `web/pos.html` | 키오스크 프론트엔드 (제품 선택~결제~완료 화면) |
| `web/viewer.html` | 단순 디버그용 뷰어 (저울 무게/상태 표시) |

## 아두이노 핀맵

| 핀 | 역할 |
|---|---|
| D2  | 버튼 (풀다운, 누르면 HIGH) |
| D5  | 부저 |
| D6  | 서보 신호 |
| D7  | 파란 LED (220Ω) |
| D8  | 빨간 LED (220Ω) |
| D9  | RC522 RST |
| D10 | RC522 SDA (SS) |
| D11 | RC522 MOSI (하드웨어 SPI) |
| D12 | RC522 MISO (하드웨어 SPI) |
| D13 | RC522 SCK (하드웨어 SPI) |

RC522는 **3.3V 전용** (5V 연결 시 손상).

## 시리얼 프로토콜 (PC ↔ Arduino, 9600 baud)

### PC → Arduino
| 명령 | 동작 |
|---|---|
| `LED:OFF` | LED 모두 꺼짐 |
| `LED:RED` | 빨간 LED 켜짐 (파란 LED 꺼짐) |
| `LED:BLUE` | 파란 LED 켜짐 (빨간 LED 꺼짐) |
| `SERVO:OPEN` | 서보를 OPEN 각도(90°)로 이동 — 디스펜서 게이트 오픈 |
| `SERVO:CLOSE` | 서보를 CLOSED 각도(0°)로 이동 — 게이트 클로즈 |
| `BEEP` | "도-미-솔" 완료 효과음(beepDone) 재생 |

### Arduino → PC
| 메시지 | 의미 |
|---|---|
| `BUTTON_PRESSED` | 물리 버튼이 눌림 (디바운스 50ms) |
| `CARD:<UID_HEX>` | RFID 카드 태그 감지, "띠-로롱" 효과음(beepCardTag) 자동 재생 |

## 서버 상태 머신 (`station_state`)

```
WAIT_CARD ──(CARD: 수신)──▶ IDLE ──(BUTTON_PRESSED)──▶ READY ──(BUTTON_PRESSED)──▶ (CHECKOUT, 클라이언트 상태)
   ▲                                                                                       │
   └──────────────────────────── reset (pos.html "처음으로") ───────────────────────────┘
```

| 상태 | LED | 서보 | 의미 |
|---|---|---|---|
| `WAIT_CARD` | 꺼짐 | CLOSE | 카드 태그 대기 |
| `IDLE` | 빨강 | CLOSE | 카드 인식됨, 용기+버튼 대기 (tare 측정 전) |
| `READY` | 파랑 | OPEN | 리필 중 (tare 측정 후, 버튼 다시 누르면 완료) |

## WebSocket 메시지 형식 (`ws://localhost:8765`)

### 서버 → 클라이언트: 상태 브로드캐스트 (`broadcast_status`)
```json
{
  "connected": true,
  "weight": 123.4,
  "stabilized": true,
  "state": "IDLE",
  "tare": null,
  "refill": null
}
```
- `connected`: 저울 BLE 연결 여부
- `weight`: 현재 저울 무게(g)
- `stabilized`: 무게 안정 여부
- `state`: `WAIT_CARD` / `IDLE` / `READY`
- `tare`: 버튼으로 측정한 용기 무게(g)
- `refill`: `weight - tare` (READY 상태에서만 의미 있음)

### 서버 → 클라이언트: 이벤트
```json
{ "event": "CARD_TAGGED", "uid": "BB1CAA00" }
{ "event": "REFILL_DONE" }
```

### 클라이언트 → 서버
```json
{ "action": "reset" }
```
- 다음 손님을 위해 `station_state`를 `WAIT_CARD`로 리셋, LED 꺼짐, 서보 CLOSE

## pos.html 클라이언트 상태

- `screen`: `CARD` → `SELECT` → `PLACE` → `REFILL` → `CHECKOUT` → `DONE` (클라이언트 전용 화면 상태)
- `product`: 선택된 제품 (`PRODUCTS` 배열의 항목, 가격/CO2 정보 포함)
- `memberName`: `MEMBERS[uid]` 조회 결과 (없으면 "고객")
- `finalRefill`: `REFILL_DONE` 시점에 캡처한 리필량(g) — 결제/완료 화면에서 사용
- `latest`: 서버로부터 받은 최신 상태 브로드캐스트 (무게/상태/리필량 등)

## BLE 저울 연결 정보

- MAC: `EC:4D:3E:DB:EA:F3`
- TOKEN: `257f0168308a7c6002f2f6bc`
- 서비스 UUID `0000fe95-...` 광고에서 MAC suffix(`f3eadb3e4dec`)를 매칭해 연결 트리거 (`BleakScanner` detection callback)
- 핸드셰이크/복호화 로직은 `hoto.py` 참고 (수정 금지 — 기존 리버스엔지니어링 결과)
