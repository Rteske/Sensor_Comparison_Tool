import threading
import datetime
from sensor import Sensor
from threading import Thread
import os
import time
import csv
import sys
import numpy as np
import openpyxl
import matplotlib.pyplot as plt

class SensorComparison:
    def __init__(self):
        self.session_start = datetime.datetime.now()
        
        dt = datetime.datetime.now()
        date_string = dt.strftime("%d_%m_%Y")
        time_string = dt.strftime("%H_%M_%S")
        dir_name = os.getcwd() + f"/data/{date_string}"
        os.makedirs(dir_name, exist_ok=True)

        self.raw_data_filepath = dir_name + f"/{time_string}.csv"
        dir_name = os.path.dirname(__file__)

        self.template_filepath = os.path.join(dir_name, "template_senor_comp_v4.xlsx")
        self.excel_filepath = dir_name + f"/TDS_{time_string}.xlsx"

        self.sensor_distances = []
        self.sensor_timestamps = []
        self.linear_encoder_positions = []
        self.measurement_deltas = []

        self.wb = openpyxl.load_workbook(self.template_filepath)
        self.ws = self.wb["RAW_DATA"]

        self.init_instruments()

    def get_data(self):
        distance, temp, linec, distance_timestamp = self.sensor.get_current_distance()
        if distance != "NA":
            measurement_delta = abs(linec - distance)
            self.sensor_distances.append(distance)
            self.sensor_timestamps.append(distance_timestamp)
            self.linear_encoder_positions.append(linec)
            self.measurement_deltas.append(measurement_delta)
            
            print(f"Delta: {measurement_delta}, Linear Encoder: {linec}, Distance: {distance}")
            self.write2file([distance, temp, linec, measurement_delta, distance_timestamp])

    def write2file(self, array):
        with open(self.raw_data_filepath, mode="a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(array)
    def init_instruments(self):
        self.sensor = Sensor()

    def plot_results(self):
        if not self.sensor_timestamps:
            print("No data collected for plotting.")
            return


        # Convert timestamps to relative time
        start_time = self.sensor_timestamps[0]
        relative_timestamps = [t - start_time for t in self.sensor_timestamps]


        
        plt.figure(figsize=(10, 5))
        plt.plot(relative_timestamps, self.sensor_distances, label="Sensor Distance", marker="o")
        plt.plot(relative_timestamps, self.linear_encoder_positions, label="Linear Encoder", marker="x")
        plt.xlabel("Time (seconds)")
        plt.ylabel("Distance (MM)")
        plt.title("Distance vs Time")
        plt.legend()
        plt.grid()
        plt.show()

        plt.figure(figsize=(10, 5))
        plt.scatter(self.linear_encoder_positions, self.measurement_deltas, label="Delta", color='r', marker=".")
        plt.xlabel("Linear Encoder (MM)")
        plt.ylabel("Measurement Delta (MM)")
        plt.title("Delta vs Linear Encoder")
        plt.grid()
        plt.show()

    def cleanup(self):
        if os.path.exists(self.raw_data_filepath):
            os.remove(self.raw_data_filepath)

if __name__ == "__main__":
    app = SensorComparison()



    total_time = 32

    t_start = time.time()


    try:
        while t_start + total_time > time.time():
            app.get_data()

        print("SAVING DATA TO WORKBOOK AND CLEANING UP")

        with open(app.raw_data_filepath, mode="r") as f:
            reader = csv.reader(f)
            for row in reader:
                new_row = [float(value) for value in row]
                app.ws.append(new_row)

        app.wb.save(app.excel_filepath)
        app.plot_results()
        app.cleanup()
        
    except KeyboardInterrupt:
        print("ALL DONE")
        sys.exit()
