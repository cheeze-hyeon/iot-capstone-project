# 알록 리필 스테이션 — 작업 일지

`README.md`(HOTO 저울 BLE 연동 작업기록)에 이어, 저울 연동 이후 진행한
"리필 스테이션 POS 키오스크 + 하드웨어 통합" 작업을 시간 순서로 정리한 작업 일지.

## 0. 시작 시점 상태

- `hoto.py` / `server.py`로 HOTO 저울 BLE 연동은 이미 완료된 상태 (README.md 참고)
- `server.py`가 `ws://localhost:8765`로 무게/안정여부를 브로드캐스트하는 것까지 동작 확인됨
- 목표: 이 무게 데이터를 활용해 "알록 POS" 리필 스테이션 키오스크를 완성

---

## 1. 5단계 리필 플로우 설계 및 1차 구현

처음 합의한 플로우:

1. 제품 선택
2. 용기 준비 (빈 용기를 저울에 올림, 빨간 LED = "준비 중")
3. 버튼으로 tare 측정 (버튼 누르면 용기 무게를 tare로 저장, LED 파란색)
4. 리필 (실시간 리필량 = 현재 무게 − tare)
5. 결제 (가격 = 리필량 × g당 단가)

### 하드웨어 (1차 구성)
- 아두이노 우노 + 빨간/파란 LED + 버튼(풀다운)
- 핀맵: D2 버튼, D8 빨간 LED, D9 파란 LED (이후 RFID 추가하면서 D7/D8/D9 배치가 재조정됨, 최종 핀맵은 ARCHITECTURE.md 참고)

### 소프트웨어
- `server.py`: 아두이노 시리얼(`pyserial`)을 별도 스레드(`arduino_loop`)로 읽어서 `BUTTON_PRESSED` 처리, `station_state`(IDLE/READY) 관리 후 WebSocket으로 통합 상태 브로드캐스트
- 아두이노 펌웨어: LED 제어 + 버튼 디바운스 + 시리얼 프로토콜(`LED:RED`/`LED:BLUE`, `BUTTON_PRESSED`)
- `pos.html` 최초 작성: 제품 선택 → 용기 준비 → 리필 → 결제 화면

### 트러블슈팅 (1차)
- `pyserial` 미설치 → `pip3 install --user pyserial`
- 아두이노 업로드 시 포트 불일치(`/dev/cu.usbmodemXXXXX`) → Arduino IDE에서 포트 재선택
- 서버 재시작 시 `address already in use`(8765) → 좀비 프로세스 `kill -9`
- HOTO 저울 BLE 핸드셰이크는 완료되지만 weight 값이 STATE 로그에 안 찍히는 이슈 발견 (이후 RFID 작업으로 우선순위 밀려 보류, TROUBLESHOOTING.md #8에 기록)
- `http://localhost:8765`를 브라우저에서 직접 열면 안 되고 `pos.html`/`viewer.html`을 `file://`로 열어야 함을 안내

---

## 2. 결제 완료 후 탄소 절감량(CO2) 표시 추가

- 사용자 요청: 결제 완료 버튼을 누르면 "이번 리필로 얼마나 탄소를 줄였는지" 표시
- `pos.html`에 `PRODUCTS` 배열에 `co2PerGram` 필드 추가, 결제 후 "완료" 화면에서
  `리필량 × co2PerGram`을 g CO2 단위로 표시

---

## 3. 물리 버튼의 이중 역할 구현

- 셀프 피드백: "빈 용기 올려놓고 버튼을 누르는 플로우가 사라졌다" → 확인 결과,
  **실물 버튼**이 두 가지 역할(① 용기 무게 측정/tare, ② 리필 완료)을 모두 수행해야 한다는 요구사항이었음
- `server.py`의 `arduino_loop`에서 `station_state`에 따라 같은 `BUTTON_PRESSED` 신호를 다르게 해석하도록 분기:
  - `IDLE` 상태에서 누르면 → tare 측정, LED 파란색, 상태 → `READY`
  - `READY` 상태에서 누르면 → "리필 완료" 신호(`REFILL_DONE` 이벤트 브로드캐스트)
- `pos.html`에서 `REFILL_DONE` 이벤트를 받으면 화면의 "리필 완료" 버튼을 누른 것과 동일하게 처리

---

## 4. RFID(RC522) + 서보모터 + 부저 추가 — 회로/펌웨어 v2

사용자가 새 플로우 제시:

```
카드 태그(RFID, 띠로롱) → 회원 정보 인식 → 빨간 LED "용기 올려주세요"
→ 버튼(tare 측정) → 파란 LED + 서보모터 열림 → 리필 → 완료 시 부저 + 서보모터 닫힘
```

### 회로 변경
- 기존 LED 2개 + 버튼 + 서보 + 부저 구성에 RC522 RFID 리더(SPI) 추가
- RC522는 3.3V 전용 (5V 연결 시 손상 주의)
- 최종 핀맵: D2 버튼, D5 부저, D6 서보, D7 파란 LED, D8 빨간 LED, D9~D13 RC522 (RST/SDA/MOSI/MISO/SCK)

### 펌웨어 재작성
- 기존 `refill_station.ino` 삭제, 새 폴더 `refill_station_rfid/refill_station_rfid.ino`로 분리 작성
  (이전 업로드 스케치와 이름이 겹쳐서 Arduino IDE에서 혼동되는 문제 방지)
- `MFRC522`, `Servo` 라이브러리 사용
- 시리얼 프로토콜 확장:
  - PC → Arduino: `LED:RED`/`LED:BLUE`, `SERVO:OPEN`/`SERVO:CLOSE`, `BEEP` 추가
  - Arduino → PC: `CARD:<UID_HEX>` 추가 (RFID 태그 감지 시)

### 서버 상태 머신 확장
- `station_state`: `WAIT_CARD`(카드 태그 대기) → `IDLE`(용기+버튼 대기) → `READY`(리필 중) 3단계로 확장
- `CARD:` 수신 시 `WAIT_CARD → IDLE` 전환 + `CARD_TAGGED` 이벤트 브로드캐스트
- 버튼 눌림 시 `IDLE → READY`(서보 열림) / `READY`에서 다시 누르면 서보 닫힘 + `BEEP` + `REFILL_DONE`
- `reset_station()`: 다음 손님을 위해 `WAIT_CARD`로 복귀, 서보 닫힘

### pos.html 플로우 확장
- 화면에 `CARD`(카드 태그 대기) 단계 추가
- `CARD_TAGGED` / `REFILL_DONE` 이벤트 처리 로직 추가

### 트러블슈팅 (RFID 단계)
- 업로드 후 포트 번호가 `/dev/cu.usbmodem11101` ↔ `/dev/cu.usbmodem1101`로 계속 바뀌어서
  `server.py`의 `ARDUINO_PORT`를 여러 번 동기화해야 했음
- Arduino IDE의 **Serial Monitor**가 포트를 점유(`Resource busy`)해서 `server.py`가 연결 실패 →
  Serial Monitor 패널을 닫아야 해결됨 (`lsof`로 점유 프로세스 진단)
- 카드 태그 시 부저는 울리지만 화면이 안 넘어가는 문제 →
  `arduino_loop` 스레드가 `SerialException: device reports readiness to read but returned no data`로
  죽어버린 것이 원인. **재연결 로직**(예외 시 포트 닫고 3초 후 재시도)을 `arduino_loop`에 추가해서 해결

---

## 5. 카드 태그 → 환영 메시지 플로우로 순서 변경

- 사용자 요청: "카드 태그 먼저 → 태그되면 '{이름}님 환영합니다! 어떤 제품을 리필하시겠어요?' → 이후 동일"
- `pos.html`:
  - 초기 화면을 `CARD`(카드 태그 대기)로 변경
  - 카드 UID → 회원 이름 매핑용 `MEMBERS` 객체 추가 (예: `BB1CAA00` → "최주현", 미등록 시 "고객")
  - `CARD_TAGGED` 수신 시 `SELECT` 화면(환영 메시지 + 제품 그리드)으로 전환
  - 제품 선택 후에는 카드 재태그 없이 바로 `PLACE`(용기 준비)로 이동

---

## 6. LED/부저 디테일 개선

- **LED**: 카드를 태그하기 전(`WAIT_CARD`)에는 LED를 모두 꺼두고, 카드 인식 시 빨간 LED가 켜지도록 변경
  - 펌웨어에 `ledsOff()` / `LED:OFF` 명령 추가
  - `server.py`: 연결 직후·리셋 시 `LED:OFF`, 카드 태그 시 `LED:RED` 전송
- **부저**: 단순 톤(`tone(2000, ...)`) 대신 멜로디로 변경
  - 카드 태그: "띠-로롱" (G6 → C7)
  - 리필 완료: "도-미-솔" 경쾌한 3음 멜로디

---

## 7. UI/UX 개선 — 토스(Toss) 스타일 리디자인

- 사용자 요청: 이모지 제거 → 아이콘 라이브러리 사용, 토스 스타일 디자인, 전체적인 가독성/사용자 친화성 개선
- **아이콘**: 모든 이모지를 [Lucide](https://lucide.dev) 아이콘(CDN)으로 교체
  - 세탁 세제: `shirt` (처음엔 `washing-machine`을 썼다가 렌더링이 이상해서 교체)
  - 섬유 유연제: `wind`, 샴푸: `droplet`, 주방 세제: `utensils-crossed`
  - 카드 태그: `credit-card`, 완료/탄소: `leaf`, 타이틀: `recycle`
- **디자인 시스템**: 다크 테마 → 화이트/라이트그레이 배경, 토스 블루(`#3182F6`) 액센트,
  카드 둥근 모서리(1~1.5rem), 부드러운 그림자, 색상별 아이콘 배지
- **가독성/디렉션 개선**:
  - 모든 화면 상단에 **진행 단계 바**(`STEP n · 단계명 / 6` + 진행률 바) 추가 → 사용자가 항상 몇 단계인지 파악 가능
  - "용기 준비"/"리필" 화면에서 선택된 제품을 별도의 **칩(아이콘+이름)**으로 분리 표시
  - "{이름}님 환영합니다!"를 큰 제목으로, "어떤 제품을 리필하시겠어요?"를 보조 텍스트로 분리해 강조
  - 안내문(`guide`) 폰트 크기/색상 강화로 본문 가독성 향상

---

## 8. 문서화 및 제출 패키징

- `docs/USER_FLOW.md`: STEP 1~6 사용자 워크플로우 정리
- `docs/ARCHITECTURE.md`: 시스템 구성도, 핀맵, 시리얼/WebSocket 프로토콜, 상태 머신, BLE 연결 정보
- `docs/TROUBLESHOOTING.md`: 이번 작업에서 겪은 9가지 시행착오와 해결법 정리
- `docs/WORKLOG.md` (본 문서): 시간순 작업 일지
- 제출용 zip(`alok_refill_station.zip`) 생성: 실제 사용 중인 핵심 파일만 모아서 별도 복사
  - `server.py`, `hoto.py`, `pos.html`, `refill_station_rfid.ino` (폴더 없이 평탄화)