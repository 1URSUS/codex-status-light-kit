#ifndef PINS_CONFIG_H
#define PINS_CONFIG_H

// NodeMCU ESP8266 default wiring.
// LED long leg -> GPIO pin through 220 ohm resistor; short leg -> GND.
#define PIN_RED D1     // GPIO5
#define PIN_YELLOW D2  // GPIO4
#define PIN_GREEN D7   // GPIO13, avoids boot mode pins

#endif
