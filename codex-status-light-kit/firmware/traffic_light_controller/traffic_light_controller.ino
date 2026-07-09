#include <EEPROM.h>
#include "pins_config.h"

const unsigned long SERIAL_BAUD = 115200;
const unsigned long BLINK_INTERVAL_MS = 500;
const unsigned long COMPLETE_IDLE_AFTER_MS = 60000;
const unsigned long WAITING_IDLE_AFTER_MS = 300000;

enum TrafficState : uint8_t {
  IDLE = 0,
  THINKING = 1,
  WAITING_USER = 2,
  TASK_COMPLETE = 3,
  TASK_FAILED = 4,
  TOOL_ERROR = 5
};

TrafficState currentState = IDLE;
unsigned long lastCommandAt = 0;
unsigned long lastBlinkAt = 0;
bool blinkOn = false;

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.setTimeout(120);

  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_YELLOW, OUTPUT);
  pinMode(PIN_GREEN, OUTPUT);

  EEPROM.begin(16);
  uint8_t saved = EEPROM.read(0);
  if (saved <= TOOL_ERROR) {
    currentState = (TrafficState)saved;
  }

  applyState(currentState, true);
  Serial.println("Codex Status Light ready");
  Serial.println("Send JSON: {\"state\":\"THINKING\"}");
  Serial.println("Or send plain text: THINKING");
}

void loop() {
  readSerialCommand();
  handleTimeouts();
  handleBlink();
}

void readSerialCommand() {
  if (!Serial.available()) {
    return;
  }

  String input = Serial.readStringUntil('\n');
  input.trim();
  if (input.length() == 0) {
    return;
  }

  String state = extractState(input);
  if (state.length() == 0) {
    Serial.print("Cannot find state in: ");
    Serial.println(input);
    return;
  }

  handleStateName(state.c_str());
}

String extractState(String input) {
  input.trim();

  // Serial Monitor can send plain text like THINKING for quick testing.
  if (!input.startsWith("{")) {
    input.toUpperCase();
    return input;
  }

  int key = input.indexOf("\"state\"");
  if (key < 0) {
    key = input.indexOf("'state'");
  }
  if (key < 0) {
    return "";
  }

  int colon = input.indexOf(':', key);
  if (colon < 0) {
    return "";
  }

  int start = input.indexOf('"', colon + 1);
  char quote = '"';
  if (start < 0) {
    start = input.indexOf('\'', colon + 1);
    quote = '\'';
  }
  if (start < 0) {
    return "";
  }

  int end = input.indexOf(quote, start + 1);
  if (end < 0) {
    return "";
  }

  String state = input.substring(start + 1, end);
  state.trim();
  state.toUpperCase();
  return state;
}

void handleTimeouts() {
  unsigned long now = millis();
  if (currentState == TASK_COMPLETE && now - lastCommandAt > COMPLETE_IDLE_AFTER_MS) {
    applyState(IDLE, false);
  }
  if (currentState == WAITING_USER && now - lastCommandAt > WAITING_IDLE_AFTER_MS) {
    applyState(IDLE, false);
  }
}

void handleStateName(const char* state) {
  lastCommandAt = millis();

  if (strcmp(state, "IDLE") == 0) {
    applyState(IDLE, false);
  } else if (strcmp(state, "THINKING") == 0) {
    applyState(THINKING, false);
  } else if (strcmp(state, "WAITING_USER") == 0) {
    applyState(WAITING_USER, false);
  } else if (strcmp(state, "TASK_COMPLETE") == 0) {
    applyState(TASK_COMPLETE, false);
  } else if (strcmp(state, "TASK_FAILED") == 0) {
    applyState(TASK_FAILED, false);
  } else if (strcmp(state, "TOOL_ERROR") == 0) {
    applyState(TOOL_ERROR, false);
  } else {
    Serial.print("Unknown state: ");
    Serial.println(state);
    return;
  }

  Serial.print("State: ");
  Serial.println(state);
}

void applyState(TrafficState state, bool forceSave) {
  currentState = state;
  blinkOn = false;
  lastBlinkAt = millis();

  switch (state) {
    case IDLE:
      setLights(false, false, true);
      blinkOn = true;
      break;
    case THINKING:
      setLights(false, false, false);
      break;
    case WAITING_USER:
      setLights(true, false, false);
      break;
    case TASK_COMPLETE:
      setLights(false, false, true);
      break;
    case TASK_FAILED:
      setLights(true, false, false);
      break;
    case TOOL_ERROR:
      setLights(false, false, false);
      break;
  }

  if (forceSave || EEPROM.read(0) != (uint8_t)state) {
    EEPROM.write(0, (uint8_t)state);
    EEPROM.commit();
  }
}

void handleBlink() {
  unsigned long now = millis();
  if (now - lastBlinkAt < BLINK_INTERVAL_MS) {
    return;
  }

  lastBlinkAt = now;
  blinkOn = !blinkOn;

  if (currentState == IDLE) {
    digitalWrite(PIN_GREEN, blinkOn ? HIGH : LOW);
  } else if (currentState == THINKING) {
    digitalWrite(PIN_YELLOW, blinkOn ? HIGH : LOW);
  } else if (currentState == TOOL_ERROR) {
    digitalWrite(PIN_RED, blinkOn ? HIGH : LOW);
  }
}

void setLights(bool red, bool yellow, bool green) {
  digitalWrite(PIN_RED, red ? HIGH : LOW);
  digitalWrite(PIN_YELLOW, yellow ? HIGH : LOW);
  digitalWrite(PIN_GREEN, green ? HIGH : LOW);
}
