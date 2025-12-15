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

    // Reconstruct the values from the received bytes
    if (index >= 8) {
      switch(packetId) {
        // Distance telemetry data
        case 0x13: {
          unsigned long distance = ((unsigned long)data[0] << 24) |
                                    ((unsigned long)data[1] << 16) |
                                    ((unsigned long)data[2] << 8) |
                                    (unsigned long)data[3];
          unsigned long divisor = ((unsigned long)data[4] << 8) |
                                   (unsigned long)data[5];
          unsigned long temp = ((unsigned long)data[6] << 8) |
                                (unsigned long)data[7];

          Serial.print("Distance:");
          Serial.print(distance);
          Serial.print("<>Divisor:");
          Serial.print(divisor);
          Serial.print("<>Temp:");
          Serial.print(temp);
          Serial.print("<>ENCODER:");
          Serial.println(encoderPos);
          break;
        }
        
        // Amplitude telemetry data
        case 0x14: {
          unsigned long max_amplitude = ((unsigned long)data[0] << 24) |
                                         ((unsigned long)data[1] << 16) |
                                         ((unsigned long)data[2] << 8) |
                                         (unsigned long)data[3];
          unsigned long first_threshold_y = ((unsigned long)data[4] << 24) |
                                             ((unsigned long)data[5] << 16) |
                                             ((unsigned long)data[6] << 8) |
                                             (unsigned long)data[7];

          Serial.print("MaxAmp:");
          Serial.print(max_amplitude);
          Serial.print("<>ThresholdY:");
          Serial.println(first_threshold_y);
          break;
        }
        
        // Device-Specific Diagnostics: Error Code & Count
        case 0x600: {
          unsigned long error_code = ((unsigned long)data[0] << 24) |
                                      ((unsigned long)data[1] << 16) |
                                      ((unsigned long)data[2] << 8) |
                                      (unsigned long)data[3];
          unsigned long error_count = ((unsigned long)data[4] << 24) |
                                       ((unsigned long)data[5] << 16) |
                                       ((unsigned long)data[6] << 8) |
                                       (unsigned long)data[7];

          Serial.print("[DIAG] ErrorCode:");
          Serial.print(error_code);
          Serial.print(" Count:");
          Serial.println(error_count);
          break;
        }
        
        // Device-Specific Diagnostics: Error Timestamp
        case 0x601: {
          unsigned long timestamp = ((unsigned long)data[0] << 24) |
                                     ((unsigned long)data[1] << 16) |
                                     ((unsigned long)data[2] << 8) |
                                     (unsigned long)data[3];

          Serial.print("[DIAG] ErrorTimestamp:");
          Serial.print(timestamp);
          Serial.println(" ms");
          break;
        }
        
        // Device-Specific Diagnostics: Error Statistics
        case 0x602: {
          unsigned long total_errors = ((unsigned long)data[0] << 24) |
                                        ((unsigned long)data[1] << 16) |
                                        ((unsigned long)data[2] << 8) |
                                        (unsigned long)data[3];
          unsigned long last_error = ((unsigned long)data[4] << 24) |
                                      ((unsigned long)data[5] << 16) |
                                      ((unsigned long)data[6] << 8) |
                                      (unsigned long)data[7];

          Serial.print("[DIAG] TotalErrors:");
          Serial.print(total_errors);
          Serial.print(" LastError:");
          Serial.println(last_error);
          break;
        }
        
        // Device-Specific Diagnostics: Error History
        case 0x603: {
          unsigned int error1 = data[0];
          unsigned int error2 = data[1];
          unsigned int error3 = data[2];
          unsigned int error4 = data[3];
          unsigned int chunk = data[4];

          Serial.print("[DIAG] ErrorHistory Chunk ");
          Serial.print(chunk);
          Serial.print(": [");
          Serial.print(error1);
          Serial.print(",");
          Serial.print(error2);
          Serial.print(",");
          Serial.print(error3);
          Serial.print(",");
          Serial.print(error4);
          Serial.println("]");
          break;
        }
        
        default:
          Serial.print("Unknown CAN ID: 0x");
          Serial.println(packetId, HEX);
          break;
      }
    }
  }
}

