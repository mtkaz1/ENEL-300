/*
 * ENEL-300 ESP32 Bluetooth Classic (SPP) Motor Controller
 * Cytron MD10C R3 — one driver per motor, Sign-Magnitude mode
 * Tank steering, 2-wheel drive
 *
 * Compatible with ESP32 Arduino core 3.x
 *
 * ── MD10C R3 Wiring ─────────────────────────────────────────────
 *   Motor A (LEFT)
 *     ESP32 GPIO 25  →  MD10C_A  DIR
 *     ESP32 GPIO 27  →  MD10C_A  PWM
 *   Motor B (RIGHT)
 *     ESP32 GPIO 26  →  MD10C_B  DIR
 *     ESP32 GPIO 14  →  MD10C_B  PWM
 *   ESP32 GND        →  Both MD10C GND signal pins
 *   Motor battery    →  MD10C PWR+ / PWR-
 *
 *   Ultrasonic HC-SR04
 *     ESP32 GPIO 18  →  TRIG
 *     ESP32 GPIO 5   →  ECHO
 *
 *   Headlight
 *     ESP32 GPIO 23  →  Headlight positive
 *
 * ── Command Protocol (ASCII byte over Bluetooth SPP) ────────────
 *   'W' – forward        'S' – reverse
 *   'A' – spin left      'D' – spin right
 *   'Q' – stop           'U' – speed up
 *   'J' – speed down     'L' – headlight toggle
 *   'N' – position lock  'M' – single distance sense
 */

#include "BluetoothSerial.h"
#include "driver/gpio.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
  #error Bluetooth Classic is not enabled.
#endif

BluetoothSerial SerialBT;

// ── Pin definitions ─────────────────────────────────────────────
#define MOTOR_A_DIR   25
#define MOTOR_A_PWM   27

#define MOTOR_B_DIR   26
#define MOTOR_B_PWM   14

#define HEADLIGHT_PIN 23

#define ULTRASONIC_TRIG 18
#define ULTRASONIC_ECHO  5
#define OBSTACLE_CM     20

// ── PWM config ──────────────────────────────────────────────────
#define PWM_FREQ      1000
#define PWM_RES_BITS  8

// ── State ───────────────────────────────────────────────────────
int  currentSpeed  = 180;
bool headlightsOn  = false;
bool positionLock  = false;

// ── Motor helpers ────────────────────────────────────────────────
void setMotorA(int dir, int speed) {
  if (dir == 0) {
    ledcWrite(MOTOR_A_PWM, 0);
    digitalWrite(MOTOR_A_DIR, LOW);
  } else {
    digitalWrite(MOTOR_A_DIR, dir > 0 ? HIGH : LOW);
    ledcWrite(MOTOR_A_PWM, speed);
  }
}

void setMotorB(int dir, int speed) {
  if (dir == 0) {
    ledcWrite(MOTOR_B_PWM, 0);
    digitalWrite(MOTOR_B_DIR, LOW);
  } else {
    digitalWrite(MOTOR_B_DIR, dir > 0 ? HIGH : LOW);
    ledcWrite(MOTOR_B_PWM, speed);
  }
}

void stopMotors() {
  setMotorA(0, 0);
  setMotorB(0, 0);
}

void btLog(const char* msg) {
  Serial.println(msg);
  SerialBT.println(msg);
}

// ── Ultrasonic helper ───────────────────────────────────────────
long readDistanceCm() {
  digitalWrite(ULTRASONIC_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(ULTRASONIC_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIG, LOW);

  long dur = pulseIn(ULTRASONIC_ECHO, HIGH, 30000);

  Serial.print("RAW_DUR:");
  Serial.println(dur);

  if (dur == 0) return 0;

  return dur / 58;
}

// ── Command handler ──────────────────────────────────────────────
void handleCommand(char cmd) {
  bool isMovement = (cmd == 'W' || cmd == 'w' ||
                     cmd == 'S' || cmd == 's' ||
                     cmd == 'A' || cmd == 'a' ||
                     cmd == 'D' || cmd == 'd' ||
                     cmd == 'Q' || cmd == 'q');

  if (positionLock && isMovement) {
    btLog("STATUS:LOCKED");
    return;
  }

  switch (cmd) {
    case 'W': case 'w':
      setMotorA(1, currentSpeed);
      setMotorB(1, currentSpeed);
      btLog("STATUS:FWD");
      break;

    case 'S': case 's':
      setMotorA(-1, currentSpeed);
      setMotorB(-1, currentSpeed);
      btLog("STATUS:REV");
      break;

    case 'A': case 'a':
      setMotorA(-1, currentSpeed);
      setMotorB(1, currentSpeed);
      btLog("STATUS:LEFT");
      break;

    case 'D': case 'd':
      setMotorA(1, currentSpeed);
      setMotorB(-1, currentSpeed);
      btLog("STATUS:RIGHT");
      break;

    case 'Q': case 'q':
      stopMotors();
      btLog("STATUS:STOP");
      break;

    case 'U': case 'u':
      currentSpeed = min(255, currentSpeed + 10);
      {
        char buf[24];
        snprintf(buf, sizeof(buf), "STATUS:SPEED:%d", currentSpeed);
        btLog(buf);
      }
      break;

    case 'J': case 'j':
      currentSpeed = max(0, currentSpeed - 10);
      {
        char buf[24];
        snprintf(buf, sizeof(buf), "STATUS:SPEED:%d", currentSpeed);
        btLog(buf);
      }
      break;

    case 'L': case 'l':
      headlightsOn = !headlightsOn;
      digitalWrite(HEADLIGHT_PIN, headlightsOn ? HIGH : LOW);
      btLog(headlightsOn ? "STATUS:HL:ON" : "STATUS:HL:OFF");
      break;

    case 'N': case 'n':
      positionLock = !positionLock;
      if (positionLock) stopMotors();
      btLog(positionLock ? "STATUS:PL:ON" : "STATUS:PL:OFF");
      break;

    case 'M': case 'm':
      {
        long dist = readDistanceCm();
        char buf[32];
        if (dist == 0) {
          btLog("STATUS:DIST:OUT_OF_RANGE");
        } else {
          snprintf(buf, sizeof(buf), "STATUS:DIST:%ld cm", dist);
          btLog(buf);
          if (dist < OBSTACLE_CM) {
            stopMotors();
            btLog("STATUS:OBSTACLE");
          }
        }
      }
      break;

    default:
      break;
  }
}

// ── Setup ───────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  pinMode(HEADLIGHT_PIN, OUTPUT);
  digitalWrite(HEADLIGHT_PIN, LOW);

  pinMode(MOTOR_A_DIR, OUTPUT);
  pinMode(MOTOR_B_DIR, OUTPUT);
  pinMode(ULTRASONIC_TRIG, OUTPUT);
  pinMode(ULTRASONIC_ECHO, INPUT);

  digitalWrite(MOTOR_A_DIR, LOW);
  digitalWrite(MOTOR_B_DIR, LOW);
  digitalWrite(ULTRASONIC_TRIG, LOW);

  ledcAttach(MOTOR_A_PWM, PWM_FREQ, PWM_RES_BITS);
  ledcAttach(MOTOR_B_PWM, PWM_FREQ, PWM_RES_BITS);

  stopMotors();
  SerialBT.begin("4B1Y");
  Serial.println("Bluetooth SPP ready — advertising as '4B1Y'");
  Serial.println("Waiting for connection...");
}

// ── Loop ────────────────────────────────────────────────────────
void loop() {
  while (SerialBT.available()) {
    char cmd = (char)SerialBT.read();
    handleCommand(cmd);
  }

  delay(10);
}