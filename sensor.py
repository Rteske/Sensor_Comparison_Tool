import serial
import time
import struct


class Sensor:
    def __init__(self, COM_PORT="COM5", baudrate=115200, timeout=0.2):
        # Match Arduino Serial.begin(115200)
        self.ser = serial.Serial(COM_PORT, baudrate, timeout=timeout)

    def _read_byte(self, timeout_s=0.5):
        # read a single byte with a small timeout
        start = time.time()
        while True:
            b = self.ser.read(1)
            if b:
                return b[0]
            if (time.time() - start) > timeout_s:
                return None

    def read_frame(self, timeout_s=0.5):
        """Read one framed message: [0x7E][type][len][payload...][chk]
        Returns (type:int, payload:bytes) or (None, None) on timeout or bad checksum.
        """
        start_time = time.time()
        # find start byte
        while True:
            b = self._read_byte(timeout_s)
            if b is None:
                return None, None
            if b == 0x7E:
                break
            # continue until start found or timeout
            if (time.time() - start_time) > timeout_s:
                return None, None

        # read type and len
        t = self._read_byte(timeout_s)
        if t is None:
            return None, None
        l = self._read_byte(timeout_s)
        if l is None:
            return None, None

        payload = bytearray()
        remaining = l
        while remaining > 0:
            b = self._read_byte(timeout_s)
            if b is None:
                return None, None
            payload.append(b)
            remaining -= 1

        chk = self._read_byte(timeout_s)
        if chk is None:
            return None, None

        # verify checksum (type ^ len ^ payload_bytes...)
        c = t ^ l
        for pb in payload:
            c ^= pb

        if c != chk:
            # bad checksum
            return None, None

        return t, bytes(payload)

    def get_current_distance(self, timeout_s=0.2):
        """Convenience wrapper: return telemetry frame if available.

        Returns (distance, temp, encoder, timestamp) or ("NA", "NA", "NA", "NA").
        """
        t, payload = self.read_frame(timeout_s=timeout_s)
        if t is None:
            return "NA", "NA", "NA", "NA"

        if t == 0x10 and payload and len(payload) >= 10:
            # distance (4), temp (2), encoder (4) -- big-endian
            distance_raw = struct.unpack('>I', payload[0:4])[0]
            temp_raw = struct.unpack('>H', payload[4:6])[0]
            encoder_raw = int.from_bytes(payload[6:10], byteorder='big', signed=True)
            package_recieved_time = time.time()
            # keep compatibility with previous scaling
            return distance_raw / 10.0, float(temp_raw), float(encoder_raw) * 0.01, package_recieved_time

        # For non-telemetry frames, return NA and let caller call read_frame()
        return "NA", "NA", "NA", "NA"


if __name__ == "__main__":
    sen = Sensor()
    try:
        while True:
            t, payload = sen.read_frame(timeout_s=1.0)
            print('FRAME:', t, payload)
    except KeyboardInterrupt:
        print('done')