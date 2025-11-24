#include <Arduino.h>

#include <CANSAME5x.h>

CANSAME5x CAN;

// Define the pins connected to the quadrature encoder outputs
const int encoderPinA = 15;  // Connect to the first output of encoder
const int encoderPinB = 14;  // Connect to the second output of encoder

volatile int encoderPos = 0;  // Variable to store encoder position

// Function to handle interrupt from encoderPinA
void updateEncoder() {
  boolean apos = digitalRead(encoderPinA);  // MSB = most significant bit
  boolean bpos = digitalRead(encoderPinB);  // LSB = least significant bit

  if(apos == bpos) encoderPos--;
  if(bpos != apos) encoderPos++;
}

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println("CAN Receiver");

  pinMode(PIN_CAN_STANDBY, OUTPUT);
  digitalWrite(PIN_CAN_STANDBY, false); // turn off STANDBY
  pinMode(PIN_CAN_BOOSTEN, OUTPUT);
  digitalWrite(PIN_CAN_BOOSTEN, true); // turn on booster

  // start the CAN bus at 250 kbps
  if (!CAN.begin(500000)) {
    Serial.println("Starting CAN failed!");
    while (1) delay(10);
  }
  Serial.println("Starting CAN!");

  pinMode(encoderPinA, INPUT_PULLUP);  // Set encoder pins as inputs
  pinMode(encoderPinB, INPUT_PULLUP);
  // Attach interrupt on a change of state on encoderPinA (to call updateEncoder function)
  attachInterrupt(digitalPinToInterrupt(encoderPinA), updateEncoder, CHANGE);  
}

void loop() {
  int packetSize = CAN.parsePacket();

  if (packetSize) {
    Serial.println("Recieved Packet");
    Serial.println();
    uint32_t packetId = CAN.packetId();
    
    int data[8];
    int index = 0;
    while (CAN.available()) {
      if (index < 8) {
        data[index++] = CAN.read();
      } else {
        CAN.read(); // discard if more than 8 bytes
      }
    }

    // Reconstruct the amplitude value from the first 4 bytes
    if (index >= 8) {
      switch(packetId) {
        // Ensure at least 8 bytes were received
        case 0x13: {
          unsigned long distance = ((unsigned long)data[0] << 24) |
                                    ((unsigned long)data[1] << 16) |
                                    ((unsigned long)data[2] << 8) |
                                    (unsigned long)data[3];
          unsigned long temp = ((unsigned long)data[6] << 8) |
                                    (unsigned long)data[7];
                

          // Calculate the time interval between received messages

          Serial.print("Distance:");
          Serial.print(distance);
          Serial.print("<>Temp:");
          Serial.print(temp);
          Serial.print("<>ENCODER:");
          Serial.println(encoderPos);
        }
      }
    }
  }
}

