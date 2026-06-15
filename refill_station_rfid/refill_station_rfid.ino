// 리필 스테이션 컨트롤러 v2: LED(빨강/파랑) + 버튼 + RC522 RFID + 서보 + 부저
//
// 핀맵
//   D2  버튼 (풀다운, 누르면 HIGH)
//   D5  부저
//   D6  서보 신호
//   D7  파란 LED (220Ω)
//   D8  빨간 LED (220Ω)
//   D9  RC522 RST
//   D10 RC522 SDA(SS)
//   D11 RC522 MOSI (하드웨어 SPI)
//   D12 RC522 MISO (하드웨어 SPI)
//   D13 RC522 SCK  (하드웨어 SPI)
//   RC522 3.3V 전용 (5V 연결 금지)
//
// 시리얼 프로토콜 (9600 baud)
//   PC -> Arduino: "LED:OFF" / "LED:RED" / "LED:BLUE" / "SERVO:OPEN" / "SERVO:CLOSE" / "BEEP"
//   Arduino -> PC: "BUTTON_PRESSED" / "CARD:<UID_HEX>"

#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>

const int PIN_LED_RED = 8;
const int PIN_LED_BLUE = 7;
const int PIN_BUTTON = 2;
const int PIN_BUZZER = 5;
const int PIN_SERVO = 6;
const int PIN_RFID_RST = 9;
const int PIN_RFID_SS = 10;

const int SERVO_CLOSED_ANGLE = 0;
const int SERVO_OPEN_ANGLE = 90;

const unsigned long DEBOUNCE_MS = 50;

MFRC522 rfid(PIN_RFID_SS, PIN_RFID_RST);
Servo servo;

int lastRawState = LOW;
int stableState = LOW;
unsigned long lastChangeTime = 0;

const int NOTE_C6 = 1047;
const int NOTE_E6 = 1319;
const int NOTE_G6 = 1568;
const int NOTE_C7 = 2093;

void setLed(bool red) {
  digitalWrite(PIN_LED_RED, red ? HIGH : LOW);
  digitalWrite(PIN_LED_BLUE, red ? LOW : HIGH);
}

void ledsOff() {
  digitalWrite(PIN_LED_RED, LOW);
  digitalWrite(PIN_LED_BLUE, LOW);
}

// 카드 태그: "띠-로롱"
void beepCardTag() {
  tone(PIN_BUZZER, NOTE_G6, 90);
  delay(100);
  tone(PIN_BUZZER, NOTE_C7, 160);
  delay(170);
  noTone(PIN_BUZZER);
}

// 리필 완료: 도-미-솔 경쾌한 효과음
void beepDone() {
  tone(PIN_BUZZER, NOTE_C6, 90);
  delay(100);
  tone(PIN_BUZZER, NOTE_E6, 90);
  delay(100);
  tone(PIN_BUZZER, NOTE_G6, 200);
  delay(210);
  noTone(PIN_BUZZER);
}

void setup() {
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_LED_BLUE, OUTPUT);
  pinMode(PIN_BUTTON, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  servo.attach(PIN_SERVO);
  servo.write(SERVO_CLOSED_ANGLE);

  SPI.begin();
  rfid.PCD_Init();

  Serial.begin(9600);
  ledsOff(); // 시작 상태: 카드 태그 전에는 LED 꺼짐
}

void loop() {
  // 버튼 디바운스 + 눌림 감지 (LOW -> HIGH 전환 시 1회 전송)
  int raw = digitalRead(PIN_BUTTON);
  if (raw != lastRawState) {
    lastChangeTime = millis();
    lastRawState = raw;
  }
  if ((millis() - lastChangeTime) > DEBOUNCE_MS && raw != stableState) {
    stableState = raw;
    if (stableState == HIGH) {
      Serial.println("BUTTON_PRESSED");
    }
  }

  // RFID 카드 태그 감지
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    Serial.print("CARD:");
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) Serial.print("0");
      Serial.print(rfid.uid.uidByte[i], HEX);
    }
    Serial.println();
    beepCardTag(); // 띠로롱 피드백
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }

  // PC로부터 명령 수신
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line == "LED:OFF") {
      ledsOff();
    } else if (line == "LED:RED") {
      setLed(true);
    } else if (line == "LED:BLUE") {
      setLed(false);
    } else if (line == "SERVO:OPEN") {
      servo.write(SERVO_OPEN_ANGLE);
    } else if (line == "SERVO:CLOSE") {
      servo.write(SERVO_CLOSED_ANGLE);
    } else if (line == "BEEP") {
      beepDone();
    }
  }
}
