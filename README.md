# HOTO 스마트 저울 (QWCFC002) 무게 연동 - 작업 기록

## 목표
"알록 POS" 웹앱에서 HOTO 스마트 주방 저울의 무게를 자동으로 읽어와
리필 가격을 자동 계산하기 위한 5단계 계획:

1. Mi Home 페어링
2. BLE 패킷 분석
3. 무게 데이터 디코딩
4. 로컬 WebSocket 서버 구축
5. POS 웹에서 WebSocket으로 무게 수신 → 가격 계산

기기 정보:
- 모델: HOTO Smart Kitchen Scale (QWCFC002), BLE 4.0
- MIoT model: `hoto.k_scale.qwcfc2`
- MAC: `EC:4D:3E:DB:EA:F3`

---

## 시도했던 방법들 (막힌 길)

### 1. BLE 광고(advertisement) 직접 분석
- `bleak`로 스캔해서 MiBeacon(서비스 UUID `0xFE95`) 광고 데이터를 확인.
- frame_control 비트를 분석한 결과 `hasObject=0` → **광고에는 무게 데이터가 아예 없음**을 확인.
- 즉 이 저울은 평소엔 그냥 "나 여기 있다" 정도의 신호만 보내고, 실제 무게는 GATT 연결 후에만 전송됨.

### 2. Xiaomi Cloud(Mi 계정)에서 정보 추출
- `micloud` 라이브러리로 Mi 계정 로그인(2FA 포함) 성공.
- `device_list` API로 기기 정보 조회 → 디바이스가 offline 상태라 `get_user_device_data`(과거 측정 기록)는 비어있음.
- `/v2/device/blt_get_beaconkey` API로 **beaconkey** 추출 성공 (`8f7363422a7c0393dee4c4da7b1a1111`).
  - 이건 나중에 MiBeacon 광고 암호화 해독용으로 쓰려 했으나, 애초에 광고에 무게 데이터가 없어서 무용지물이었음.
- **결정적으로**, `device_list` raw 응답 안에 `"token": "257f0168308a7c6002f2f6bc"` 라는 **per-device token**이 있었음 → 이게 나중에 핵심 키가 됨.

### 3. 아이폰으로 BLE 패킷 스니핑 (PacketLogger)
- Mac에 BLE 안테나가 있긴 하지만, Mi Home 앱이 저울과 통신하는 실제 패킷을 보려면 아이폰이 필요.
- Xcode의 PacketLogger + iPhone Bluetooth 진단 프로파일 설치 후, USB로 연결해서 BTSnoop 캡처 성공.
- BTSnoop 파일을 직접 파싱하는 스크립트(`parse_btsnoop.py`)를 작성:
  - datalink type 1001(Unencapsulated HCI)은 HCI 패킷 타입 바이트가 없다는 점이 핵심 디버깅 포인트.
  - ATT(GATT) 프로토콜의 `Handle Value Notification`(opcode 0x1b) 패킷들을 추출.
  - handle `0x0021`에서 16바이트짜리 알림(2바이트 카운터 + 14바이트 암호문)이 반복적으로 오는 것을 확인.
- beaconkey로 AES 복호화를 시도했지만 실패 (다른 키 체계였음).
- 외부에서 받은 "0xE9FC 헤더 = 무게" 분석은 실제 캡처 데이터와 대조한 결과 **사실이 아님(환각)**으로 판명, 폐기.

### 4. 기존 리버스엔지니어링 활용 (돌파구)
- GitHub `n0n3m4/hoto_kitchen_ha` (Home Assistant 커스텀 통합)을 발견.
- README에 따르면 이 저울은 **Xiaomi "mible secure-login" 핸드셰이크**를 사용하며,
  핸드셰이크에 "per-device token"(12바이트)이 필요함 — 바로 위에서 Cloud에서 뽑아둔 `token` 값과 일치!

---

## 최종 동작 원리

### 핸드셰이크 (mible secure-login)
1. 두 개의 GATT characteristic으로 제어 메시지 교환
   - UPNP UUID: `00000010-0000-1000-8000-00805f9b34fb`
   - AVDTP UUID: `00000019-0000-1000-8000-00805f9b34fb`
2. wake/sync 시퀀스 전송 → 로그인 요청
3. 내 쪽 랜덤값(16바이트)과 저울의 랜덤값(16바이트)을 교환
4. `HKDF-SHA256(token, salt=내랜덤+상대랜덤, info=b"mible-login-info")` 로 40바이트를 뽑아 4개로 분할:
   - `dev_key`(16B), `app_key`(16B), `dev_iv`(4B), `app_iv`(4B)
5. 서로 HMAC-SHA256으로 인증값 교환 (우리 환경에선 device 쪽 HMAC mismatch 경고가 떴지만, 로그인 자체는 통과됨)
6. 로그인 완료 → 무게 characteristic 구독 시작
   - WEIGHT UUID: `0000010-2006-56c6-22e7-46f696d2e696d` (문자열 그대로 사용, UUID 파싱 시 자동 정규화됨)

### 무게 데이터 디코딩
- 알림 패킷 = `2바이트 카운터(LE) + AES-CCM 암호문(태그 4바이트)`
- `nonce = dev_iv + 0x00000000 + counter(4바이트, LE)`
- `AES-CCM(dev_key, tag_length=4).decrypt(nonce, ciphertext, None)` → 평문
- 평문 형식:
  - byte[3]: `7` = 측정 중(불안정), `8` = 안정화됨
  - byte[5..6]: 무게 raw값 (LE, 0.1g 단위)
  - byte[7]의 `0x10` 비트: 음수 부호

---

## 폴더 구조

```
hoto_driver/
├── server/   # 파이썬 서버 + BLE 드라이버
├── web/      # 브라우저 프론트엔드
├── firmware/ # 아두이노 펌웨어
└── docs/     # 문서
```

| 파일 | 역할 |
|---|---|
| `server/hoto.py` | 핵심 드라이버. BLE 연결, 핸드셰이크, 무게 복호화를 담당하는 `HotoScale` 클래스 (n0n3m4/hoto_kitchen_ha 에서 가져옴) |
| `server/const.py` | UUID, HKDF info 등 상수 |
| `server/server.py` | 저울에 연결 → 무게 변화를 `ws://localhost:8765`로 실시간 브로드캐스트하는 WebSocket 서버 |
| `web/viewer.html` | 브라우저에서 WebSocket으로 받은 무게를 큰 글씨로 보여주는 테스트 페이지 |
| `server/run.py` | (1회성 테스트용) 저울에 연결해서 콘솔에 무게를 출력하는 스크립트 |

### 사용한 기기별 비밀값
- MAC: `EC:4D:3E:DB:EA:F3`
- Token: `257f0168308a7c6002f2f6bc` (Mi Cloud `device_list`에서 추출)

### 실행 방법
```bash
cd hoto_driver/server
python3 -u server.py
```
- 저울을 깨우면(전원 on / 무게 변화) 자동으로 BLE 연결 + 로그인 + 무게 스트리밍 시작.
- `web/viewer.html`을 브라우저로 열면 실시간 무게 표시.
- 연결되면 `idle_timeout=None` 설정으로 인해 계속 연결 유지됨 (자동으로 끊지 않음).

---

## 노트북을 껐다 켰을 때 (재연결 방법)

필요한 패키지(`bleak`, `bleak_retry_connector`, `cryptography`, `websockets`)는
`pip3 install`로 사용자 site-packages에 설치되어 있어서, **재부팅해도 다시 설치할 필요는 없음**.
다시 해야 할 건 아래 두 가지뿐:

1. **서버 실행**
   ```bash
   cd /Users/cz/Workspace/iot/hoto_driver/server
   python3 -u server.py &
   ```
   (백그라운드로 띄우려면 끝에 `&`, 로그 보려면 `> /tmp/hoto_server.log 2>&1 &`)

2. **저울 깨우기**
   - 저울은 평소 광고를 안 하다가, 전원 버튼을 누르거나 위에 무게가 올라가는 순간에만
     잠깐(수 초~수십 초) BLE 광고를 시작함.
   - 서버가 그 광고를 잡으면 자동으로 연결 → 로그인 → 무게 스트리밍이 시작됨.
   - 한 번에 안 잡히면 서버를 띄운 직후 저울을 한두 번 더 켰다 끄거나 물건을 올렸다 내리면 됨.

3. **브라우저에서 확인**
   - `web/viewer.html`을 열면 `ws://localhost:8765`에 자동 연결되고, 끊겨도 1초마다 재연결을 시도함.

> 참고: MAC(`EC:4D:3E:DB:EA:F3`)과 token(`257f0168308a7c6002f2f6bc`)은 `server/server.py` 안에
> 하드코딩되어 있어서 별도 로그인/인증 절차는 필요 없음. (단, Mi Home 앱에서 기기를 삭제하고
> 다시 페어링하면 token이 바뀌므로 다시 추출해야 함)

---

## 다음 단계 (미완료)
1. `server/server.py`의 WebSocket 메시지를 "알록 POS" 웹앱에서 구독
2. 받은 무게(g) 기준으로 리필 가격 자동 계산 로직 추가
3. (선택) 저울이 광고 안 할 때를 대비한 재연결/안정성 처리, idle timeout 설정 등
