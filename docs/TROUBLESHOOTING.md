# 알록 리필 스테이션 — 시행착오 / 트러블슈팅 기록

개발 중 겪었던 문제와 해결 방법을 정리. 같은 문제가 재발하면 여기부터 확인.

## 1. `pyserial` 모듈 없음
- 증상: `server.py` 실행 시 `ModuleNotFoundError: No module named 'serial'`
- 해결: `pip3 install --user pyserial`

## 2. 아두이노 업로드 시 포트 오류
- 증상: `OS error: cannot open port /dev/cu.usbmodemXXXXX: No such file or directory`
- 원인: Arduino IDE의 `Tools > Port`에 설정된 포트 이름과 실제 연결된 포트가 다름
- 해결: `ls /dev/cu.*`로 실제 포트 확인 후 Arduino IDE에서 올바른 포트 선택
- **주의**: 펌웨어를 재업로드하거나 USB를 재연결하면 포트 번호(`/dev/cu.usbmodemXXXXX`)가 바뀔 수 있음 → `server.py`의 `ARDUINO_PORT`도 같이 업데이트해야 함

## 3. Arduino IDE Serial Monitor가 포트를 점유 (`Resource busy`)
- 증상: `server.py` 실행 시 `아두이노(...) 연결 실패` / 직접 테스트 시 `SerialException: ... Resource busy`
- 원인: Arduino IDE의 Serial Monitor 패널이 같은 포트를 열어두고 있음
- 진단: `lsof /dev/cu.usbmodemXXXXX` → `serial-monitor` 프로세스가 점유 중인지 확인
- 해결: Arduino IDE에서 Serial Monitor 패널/탭을 닫기 (또는 Arduino IDE 완전 종료 후 재실행)

## 4. 시리얼 포트 충돌: `address already in use` (8765)
- 증상: `server.py` 재시작 시 WebSocket 포트(8765) 충돌
- 원인: 이전에 백그라운드로 띄운 `server.py` 프로세스가 종료되지 않고 남아있음
- 해결: `pgrep -f server.py | xargs -r kill -9` 후 재시작

## 5. 아두이노 시리얼 스레드가 죽어서 카드/버튼 입력이 서버에 전달 안 됨
- 증상: RFID 카드를 태그하면 부저음은 들리는데(아두이노 자체 동작은 정상) 서버 로그에 `CARD:` 수신 기록이 없고 화면도 전환되지 않음
- 원인: USB 일시적 끊김 등으로 `arduino_loop` 스레드가
  ```
  SerialException: device reports readiness to read but returned no data
  (device disconnected or multiple access on port?)
  ```
  예외로 죽어버림. 이후 시리얼 포트는 여전히 열려있지만 아무도 읽지 않는 상태가 됨.
- 해결: `server.py`의 `arduino_loop`을 재연결 루프로 보강 — 시리얼 예외 발생 시 포트를 닫고 3초 후 재연결 시도. (현재 코드에 반영됨)

## 6. 아두이노 스케치 파일명 충돌
- 증상: Arduino IDE에서 업로드 시 이전에 올렸던 스케치와 이름이 겹쳐 혼동/실패
- 원인: Arduino IDE는 스케치 폴더명과 `.ino` 파일명이 같아야 하며, 동일 이름의 스케치가 여러 개 있으면 헷갈림
- 해결: 새 폴더 `refill_station_rfid/refill_station_rfid.ino`로 이름을 명확히 분리하고 기존 `refill_station.ino`는 삭제

## 7. 제품 아이콘이 이상하게 렌더링됨 (Lucide 아이콘)
- 증상: 세탁 세제 아이콘으로 `washing-machine`을 사용했으나 의도와 다른 모양으로 표시됨
- 해결: `shirt` 아이콘으로 교체

## 8. HOTO 저울 BLE 연결은 되지만 무게 값이 안 들어옴 (미해결/보류)
- 증상: BLE 핸드셰이크는 정상 완료(`login complete`, `connected=True`)되고 무게 characteristic notify도 구독되지만(151회 notify 수신, 복호화 실패 0건), `STATE:` 로그에 실제 weight 값이 찍히지 않음
- 상태: RFID/서보/부저 등 POS 플로우 작업으로 우선순위가 낮아져 추가 조사 보류. 향후 재현 시 `hoto.py`의 notify 콜백/복호화 경로부터 점검 필요
- 참고: 저울은 전원 버튼을 누르거나 무게가 바뀔 때 짧게만 BLE 광고(advertise)하므로, 광고 자체가 안 잡히는 경우 저울을 깨워줘야 함

## 9. `http://localhost:8765`를 브라우저에서 직접 열면 안 됨
- 증상: `Failed to open a WebSocket connection: invalid Connection header: keep-alive`
- 원인: 8765는 WebSocket 전용 포트라 일반 HTTP GET으로 열 수 없음
- 해결: `pos.html` (또는 `viewer.html`)을 `file://` 경로로 직접 열어서 사용 (예: `file:///Users/cz/Workspace/iot/hoto_driver/pos.html`)
