#include <Arduino.h>

#include <CANSAME5x.h>

CANSAME5x CAN;

// ===== CONFIGURATION =====
// Choose position sensor type:
// 0 = Linear Encoder (quadrature)
// 1 = String Potentiometer (analog)
#define POSITION_SENSOR_TYPE 1

// String potentiometer configuration

// OVERSAMPLING? FOR 16BIT
const int stringPotPin = A0;  // Analog input pin for string potentiometer
const float ADC_RES = 4095.0;  // 12-bit ADC (SAMD51)
const float STRING_POT_MAX_VOLTAGE = 3.3;  // VDD MICROPROCCESSOR REFRENCE VOLTAGE
const float STRING_POT_MAX_DISTANCE = 1500.0;  // Maximum distance in mm (adjust as needed)
const float STRING_POT_START_VOLTAGE = 1.25; // Voltage at 0 mm (adjust as needed)
const int STRING_POT_SAMPLES = 10; // Number of samples to average

// STM32 Current output
const int distancePin = A2
const float DISTANCE_START_VOLTAGE = 1.25

// Linear encoder configuration
const int encoderPinA = 15;  // Connect to the first output of encoder
const int encoderPinB = 14;  // Connect to the second output of encoder

volatile int encoderPos = 0;  // Variable to store encoder position (for linear encoder)

// Function to handle interrupt from encoderPinA (for linear encoder)
void updateEncoder() {
  boolean apos = digitalRead(encoderPinA);  // MSB = most significant bit
  boolean bpos = digitalRead(encoderPinB);  // LSB = least significant bit

  if(apos == bpos) encoderPos--;
  if(bpos != apos) encoderPos++;
}

// Function to read string potentiometer position in mm
float readStringPotPosition() {

  int adcValue = 0;
  for (int i = 0; i < STRING_POT_SAMPLES; i++) {
    adcValue += analogRead(stringPotPin);
    delay(1); // Small delay to allow ADC to settle
  }
  adcValue /= STRING_POT_SAMPLES;
  
  // Convert ADC reading to voltage
  float voltage = (adcValue / ADC_RES) * STRING_POT_MAX_VOLTAGE;
  
  // Convert voltage to distance (linear mapping)
  // Adjust this mapping based on your specific string potentiometer
  // float position = (voltage / STRING_POT_MAX_VOLTAGE) * STRING_POT_MAX_DISTANCE;

  float position = (voltage - STRING_POT_START_VOLTAGE) * 1000;
  
  return position;
}

float readDistanceOutput() {
  int adcValue = 0;
  for (int i = 0; i < STRING_POT_SAMPLES; i++) {
    adcValue += analogRead(distancePin);
    delay(1); // Small delay to allow ADC to settle
  }
  adcValue /= STRING_POT_SAMPLES;
  
  // Convert ADC reading to voltage
  float voltage = (adcValue / ADC_RES) * STRING_POT_MAX_VOLTAGE;
  
  // Convert voltage to distance (linear mapping)
  // Adjust this mapping based on your specific string potentiometer
  // float position = (voltage / STRING_POT_MAX_VOLTAGE) * STRING_POT_MAX_DISTANCE;

  float position = (voltage - DISTANCE_START_VOLTAGE) * 1000;
  
  return position;
}

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println("CAN Receiver");
  
  // Print selected sensor type
  if (POSITION_SENSOR_TYPE == 0) {
    Serial.println("Position Sensor: Linear Encoder (Quadrature)");
  } else {
    Serial.println("Position Sensor: String Potentiometer (Analog A0)");
  }

  pinMode(PIN_CAN_STANDBY, OUTPUT);
  digitalWrite(PIN_CAN_STANDBY, false); // turn off STANDBY
  pinMode(PIN_CAN_BOOSTEN, OUTPUT);
  digitalWrite(PIN_CAN_BOOSTEN, true); // turn on booster

  // start the CAN bus at 250 kbps
  if (!CAN.begin(500000)) {
    Serial.println("Starting CAN failed!");
    // while (1) delay(10);
  }
  Serial.println("Starting CAN!");

  // Setup based on selected position sensor type
  if (POSITION_SENSOR_TYPE == 0) {
    // Linear encoder setup
    pinMode(encoderPinA, INPUT_PULLUP);  // Set encoder pins as inputs
    pinMode(encoderPinB, INPUT_PULLUP);
    // Attach interrupt on a change of state on encoderPinA (to call updateEncoder function)
    attachInterrupt(digitalPinToInterrupt(encoderPinA), updateEncoder, CHANGE);
  } else {
    // String potentiometer setup
    pinMode(stringPotPin, INPUT);
    analogReadResolution(12);  // Set ADC to 12-bit resolution (SAMD51 capability)
  }
}

// Helper: send compact framed binary message over Serial
// Frame: [0x7E][type][len][payload...][chk]
void sendFrame(uint8_t type, const uint8_t* payload, uint8_t len) {
  uint8_t chk = type ^ len;
  Serial.write(0x7E);
  Serial.write(type);
  Serial.write(len);
  for (uint8_t i = 0; i < len; i++) {
    Serial.write(payload[i]);
    chk ^= payload[i];
  }
  Serial.write(chk);
}

// Helper: split 32-bit into 4 bytes (big-endian)
void u32ToBytes(unsigned long v, uint8_t* out) {
  out[0] = (v >> 24) & 0xFF;
  out[1] = (v >> 16) & 0xFF;
  out[2] = (v >> 8) & 0xFF;
  out[3] = v & 0xFF;
}

void loop() {
  // TESTING FOR THE STRING POT
  // long positionValue;
  // if (POSITION_SENSOR_TYPE == 0) {
  // // Linear encoder - use encoder position (counts)
  // positionValue = encoderPos;
  // } else {
  // // String potentiometer - convert mm to counts (*100 for two decimal places)
  // float stringPotPos = readStringPotPosition();
  // positionValue = (long)(stringPotPos * 100.0);
  // }
  // uint32_t distance = 0;

  // uint8_t payload[10];
  // u32ToBytes(distance, payload);
  // // payload[4] = (temp >> 8) & 0xFF;
  // // payload[5] = temp & 0xFF;
  // // positionValue as 32-bit
  // payload[6] = (positionValue >> 24) & 0xFF;
  // payload[7] = (positionValue >> 16) & 0xFF;
  // payload[8] = (positionValue >> 8) & 0xFF;
  // payload[9] = positionValue & 0xFF;
  // // type 0x10 = telemetry distance
  // sendFrame(0x10, payload, 10);


  int packetSize = CAN.parsePacket();

  if (packetSize) {
    // Packet received (binary framing used for output)
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

          // Get position based on selected sensor type
          long positionValue;
          long distanceOutput;
          if (POSITION_SENSOR_TYPE == 0) {
            // Linear encoder - use encoder position (counts)
            positionValue = encoderPos;
          } else {
            // String potentiometer - convert mm to counts (*100 for two decimal places)
            float stringPotPos = readStringPotPosition();
            distanceOutput = readDistanceOutput()
            positionValue = (long)(stringPotPos);
          }

          // Pack: distance (4), temp (2), positionValue (4), distanceOutput (4)
          uint8_t payload[14];
          u32ToBytes(distance, payload);
          payload[4] = (temp >> 8) & 0xFF;
          payload[5] = temp & 0xFF;
          // positionValue as 32-bit
          payload[6] = (positionValue >> 24) & 0xFF;
          payload[7] = (positionValue >> 16) & 0xFF;
          payload[8] = (positionValue >> 8) & 0xFF;
          payload[9] = positionValue & 0xFF;
          // distanceOutput
          payload[10] = (distanceOutput >> 24) & 0xFF;
          payload[11] = (distanceOutput >> 16) & 0xFF;
          payload[12] = (distanceOutput >> 8) & 0xFF;
          payload[13] = distanceOutput & 0xFF;
          
          // type 0x10 = telemetry distance
          sendFrame(0x10, payload, 10);
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

          // Pack: max_amplitude (4), first_threshold_y (4)
          uint8_t payloadA[8];
          u32ToBytes(max_amplitude, payloadA);
          u32ToBytes(first_threshold_y, payloadA + 4);
          // type 0x11 = telemetry amplitude
          sendFrame(0x11, payloadA, 8);
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

          // Pack: error_code (4), error_count (4)
          uint8_t payloadE[8];
          u32ToBytes(error_code, payloadE);
          u32ToBytes(error_count, payloadE + 4);
          // type 0xA0 = diag error code + count
          sendFrame(0xA0, payloadE, 8);
          break;
        }
        
        // Device-Specific Diagnostics: Error Timestamp
        case 0x601: {
          unsigned long timestamp = ((unsigned long)data[0] << 24) |
                                     ((unsigned long)data[1] << 16) |
                                     ((unsigned long)data[2] << 8) |
                                     (unsigned long)data[3];

          // Pack: timestamp (4)
          uint8_t payloadT[4];
          u32ToBytes(timestamp, payloadT);
          // type 0xA1 = diag timestamp
          sendFrame(0xA1, payloadT, 4);
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

          // Pack: total_errors (4), last_error (4)
          uint8_t payloadS[8];
          u32ToBytes(total_errors, payloadS);
          u32ToBytes(last_error, payloadS + 4);
          // type 0xA2 = diag stats
          sendFrame(0xA2, payloadS, 8);
          break;
        }
        
        // Device-Specific Diagnostics: Error History
        case 0x603: {
          unsigned int error1 = data[0];
          unsigned int error2 = data[1];
          unsigned int error3 = data[2];
          unsigned int error4 = data[3];
          unsigned int chunk = data[4];

          // Pack: error1,error2,error3,error4,chunk (5 bytes)
          uint8_t payloadH[5];
          payloadH[0] = error1 & 0xFF;
          payloadH[1] = error2 & 0xFF;
          payloadH[2] = error3 & 0xFF;
          payloadH[3] = error4 & 0xFF;
          payloadH[4] = chunk & 0xFF;
          // type 0xA3 = diag history chunk
          sendFrame(0xA3, payloadH, 5);
          break;
        }
        
        // Performance Timing Data
        case 0x700: {
          unsigned int timer_id = data[0];
          unsigned long avg_us = ((unsigned long)data[1] << 8) | (unsigned long)data[2];
          unsigned long max_us = ((unsigned long)data[3] << 8) | (unsigned long)data[4];
          unsigned long min_us = ((unsigned long)data[5] << 8) | (unsigned long)data[6];
          unsigned int count = data[7];

          // Pack: timer_id(1), avg_us(2), max_us(2), min_us(2), count(1) = 8 bytes
          uint8_t payloadP[8];
          payloadP[0] = timer_id & 0xFF;
          payloadP[1] = (avg_us >> 8) & 0xFF;
          payloadP[2] = avg_us & 0xFF;
          payloadP[3] = (max_us >> 8) & 0xFF;
          payloadP[4] = max_us & 0xFF;
          payloadP[5] = (min_us >> 8) & 0xFF;
          payloadP[6] = min_us & 0xFF;
          payloadP[7] = count & 0xFF;
          // type 0xB0 = performance timing
          sendFrame(0xB0, payloadP, 8);
          break;
        }
        
        default:
          // Send unknown ID frame (type 0xAF) with 4-byte id payload
          {
            uint8_t payloadU[4];
            payloadU[0] = (packetId >> 24) & 0xFF;
            payloadU[1] = (packetId >> 16) & 0xFF;
            payloadU[2] = (packetId >> 8) & 0xFF;
            payloadU[3] = packetId & 0xFF;
            sendFrame(0xAF, payloadU, 4);
          }
          break;
      }
    }
  }
}

