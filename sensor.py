import serial
import time

class Sensor:
    def __init__(self, COM_PORT="COM7"):
        self.ser = serial.Serial(COM_PORT, 250000)

    def read_data(self):
        start_data = self.ser.readline().decode("utf-8").strip()
        start_data = start_data.split("<>")
        return start_data

    def process_frame(self, data):
        try:
            strdist = data[0].split(":")
            strtemp = data[1].split(":")
            strline = data[2].split(":")

            if strdist[0] == "Distance":
                distance = float(strdist[1])
                temp = float(strtemp[1])
                linec = float(strline[1])
            elif data:
                distance = "NA"
                temp = "NA"
                linec = "NA"
        except:
            distance = "NA"
            temp = "NA"
            linec = "NA"
            print("FAIL")

        return distance, temp, linec

    def get_current_distance(self):
        data_string = self.read_data()
        distance, temp, linec = self.process_frame(data_string)
        if distance != "NA":
            package_recieved_time = time.time()
            return distance / 10 , temp, linec * .01 , package_recieved_time
        else:
            return "NA", "NA", "NA", "NA"
        
if __name__ == "__main__":
    sen = Sensor()
    counter = 1000
    try:
        while counter > 0:
            distance, temp, linec, recieve = sen.get_current_distance()
            print(distance, temp, linec, recieve)
    except KeyboardInterrupt:
        print('done')