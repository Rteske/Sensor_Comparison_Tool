import datetime
from sensor import Sensor
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
        with open(self.raw_data_filepath, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
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

    def create_lookup_table(self):
        """Create a lookup table in a .h file that maps linear encoder positions to sensor distances"""
        if not self.sensor_distances or not self.linear_encoder_positions:
            print("No data available for creating lookup table.")
            return
        
        # Create pairs of (linear_encoder_position, sensor_distance)
        data_pairs = list(zip(self.linear_encoder_positions, self.sensor_distances))
        
        # Sort by linear encoder position
        data_pairs.sort(key=lambda x: x[0])
        
        # Remove duplicates and average distances for same positions
        lookup_dict = {}
        for pos, dist in data_pairs:
            pos_rounded = round(pos, 2)  # Round to 2 decimal places
            if pos_rounded in lookup_dict:
                lookup_dict[pos_rounded].append(dist)
            else:
                lookup_dict[pos_rounded] = [dist]
        
        # Average the distances for each position
        averaged_lookup = {}
        for pos, distances in lookup_dict.items():
            averaged_lookup[pos] = sum(distances) / len(distances)
        
        # Generate .h file
        dt = datetime.datetime.now()
        time_string = dt.strftime("%H_%M_%S")
        h_filename = f"lookup_table_{time_string}.h"
        h_filepath = os.path.join(os.path.dirname(self.raw_data_filepath), h_filename)
        
        with open(h_filepath, 'w', encoding='utf-8') as h_file:
            h_file.write("// Sensor Distance Lookup Table\n")
            h_file.write("// Generated on: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            h_file.write("// Maps linear encoder positions (mm) to sensor distances (mm)\n\n")
            h_file.write("#ifndef LOOKUP_TABLE_H\n")
            h_file.write("#define LOOKUP_TABLE_H\n\n")
            
            sorted_positions = sorted(averaged_lookup.keys())
            table_size = len(sorted_positions)
            
            # Create arrays for positions and distances
            h_file.write("// Lookup table size\n")
            h_file.write("#define LOOKUP_TABLE_SIZE {}\n\n".format(table_size))
            
            h_file.write("// Position array (mm)\n")
            h_file.write("const float positions[LOOKUP_TABLE_SIZE] = {\n")
            for i, pos in enumerate(sorted_positions):
                comma = "," if i < len(sorted_positions) - 1 else ""
                h_file.write("    {:.2f}f{}\n".format(pos, comma))
            h_file.write("};\n\n")
            
            h_file.write("// Distance array (mm)\n")
            h_file.write("const float distances[LOOKUP_TABLE_SIZE] = {\n")
            for i, pos in enumerate(sorted_positions):
                dist = averaged_lookup[pos]
                comma = "," if i < len(sorted_positions) - 1 else ""
                h_file.write("    {:.2f}f{}\n".format(dist, comma))
            h_file.write("};\n\n")
            
            # Add helper functions
            h_file.write("// Function to get distance for a given position (exact match)\n")
            h_file.write("float getDistanceForPosition(float position) {\n")
            h_file.write("    for (int i = 0; i < LOOKUP_TABLE_SIZE; i++) {\n")
            h_file.write("        if (positions[i] == position) {\n")
            h_file.write("            return distances[i];\n")
            h_file.write("        }\n")
            h_file.write("    }\n")
            h_file.write("    return -1.0f; // Position not found\n")
            h_file.write("}\n\n")
            
            h_file.write("// Function to get nearest distance for a position (interpolated)\n")
            h_file.write("float getNearestDistance(float position) {\n")
            h_file.write("    if (LOOKUP_TABLE_SIZE == 0) return -1.0f;\n")
            h_file.write("    \n")
            h_file.write("    // Check for exact match first\n")
            h_file.write("    for (int i = 0; i < LOOKUP_TABLE_SIZE; i++) {\n")
            h_file.write("        if (positions[i] == position) {\n")
            h_file.write("            return distances[i];\n")
            h_file.write("        }\n")
            h_file.write("    }\n")
            h_file.write("    \n")
            h_file.write("    // Find the two closest points for interpolation\n")
            h_file.write("    if (position <= positions[0]) {\n")
            h_file.write("        return distances[0]; // Return first value\n")
            h_file.write("    }\n")
            h_file.write("    if (position >= positions[LOOKUP_TABLE_SIZE - 1]) {\n")
            h_file.write("        return distances[LOOKUP_TABLE_SIZE - 1]; // Return last value\n")
            h_file.write("    }\n")
            h_file.write("    \n")
            h_file.write("    // Linear interpolation between two points\n")
            h_file.write("    for (int i = 0; i < LOOKUP_TABLE_SIZE - 1; i++) {\n")
            h_file.write("        if (position > positions[i] && position < positions[i + 1]) {\n")
            h_file.write("            float x1 = positions[i];\n")
            h_file.write("            float y1 = distances[i];\n")
            h_file.write("            float x2 = positions[i + 1];\n")
            h_file.write("            float y2 = distances[i + 1];\n")
            h_file.write("            \n")
            h_file.write("            // Linear interpolation formula\n")
            h_file.write("            float interpolated = y1 + (y2 - y1) * (position - x1) / (x2 - x1);\n")
            h_file.write("            return interpolated;\n")
            h_file.write("        }\n")
            h_file.write("    }\n")
            h_file.write("    \n")
            h_file.write("    return -1.0f; // Should not reach here\n")
            h_file.write("}\n\n")
            
            h_file.write("// Function to get the closest position index in the lookup table\n")
            h_file.write("int getClosestPositionIndex(float position) {\n")
            h_file.write("    int closest_index = 0;\n")
            h_file.write("    float min_diff = (position > positions[0]) ? position - positions[0] : positions[0] - position;\n")
            h_file.write("    \n")
            h_file.write("    for (int i = 1; i < LOOKUP_TABLE_SIZE; i++) {\n")
            h_file.write("        float diff = (position > positions[i]) ? position - positions[i] : positions[i] - position;\n")
            h_file.write("        if (diff < min_diff) {\n")
            h_file.write("            min_diff = diff;\n")
            h_file.write("            closest_index = i;\n")
            h_file.write("        }\n")
            h_file.write("    }\n")
            h_file.write("    \n")
            h_file.write("    return closest_index;\n")
            h_file.write("}\n\n")
            
            h_file.write("// Function to get the nearest position given a distance (reverse lookup)\n")
            h_file.write("float getNearestPosition(float distance) {\n")
            h_file.write("    if (LOOKUP_TABLE_SIZE == 0) return -1.0f;\n")
            h_file.write("    \n")
            h_file.write("    // Check for exact match first\n")
            h_file.write("    for (int i = 0; i < LOOKUP_TABLE_SIZE; i++) {\n")
            h_file.write("        if (distances[i] == distance) {\n")
            h_file.write("            return positions[i];\n")
            h_file.write("        }\n")
            h_file.write("    }\n")
            h_file.write("    \n")
            h_file.write("    // Find the two closest distances for interpolation\n")
            h_file.write("    if (distance <= distances[0]) {\n")
            h_file.write("        return positions[0]; // Return first position\n")
            h_file.write("    }\n")
            h_file.write("    if (distance >= distances[LOOKUP_TABLE_SIZE - 1]) {\n")
            h_file.write("        return positions[LOOKUP_TABLE_SIZE - 1]; // Return last position\n")
            h_file.write("    }\n")
            h_file.write("    \n")
            h_file.write("    // Linear interpolation between two points using distance as input\n")
            h_file.write("    for (int i = 0; i < LOOKUP_TABLE_SIZE - 1; i++) {\n")
            h_file.write("        if (distance > distances[i] && distance < distances[i + 1]) {\n")
            h_file.write("            float x1 = distances[i];    // distance1\n")
            h_file.write("            float y1 = positions[i];    // position1\n")
            h_file.write("            float x2 = distances[i + 1]; // distance2\n")
            h_file.write("            float y2 = positions[i + 1]; // position2\n")
            h_file.write("            \n")
            h_file.write("            // Linear interpolation formula (reverse lookup)\n")
            h_file.write("            float interpolated = y1 + (y2 - y1) * (distance - x1) / (x2 - x1);\n")
            h_file.write("            return interpolated;\n")
            h_file.write("        }\n")
            h_file.write("    }\n")
            h_file.write("    \n")
            h_file.write("    return -1.0f; // Should not reach here\n")
            h_file.write("}\n\n")
            
            h_file.write("// Function to get the closest distance index in the lookup table (reverse search)\n")
            h_file.write("int getClosestDistanceIndex(float distance) {\n")
            h_file.write("    int closest_index = 0;\n")
            h_file.write("    float min_diff = (distance > distances[0]) ? distance - distances[0] : distances[0] - distance;\n")
            h_file.write("    \n")
            h_file.write("    for (int i = 1; i < LOOKUP_TABLE_SIZE; i++) {\n")
            h_file.write("        float diff = (distance > distances[i]) ? distance - distances[i] : distances[i] - distance;\n")
            h_file.write("        if (diff < min_diff) {\n")
            h_file.write("            min_diff = diff;\n")
            h_file.write("            closest_index = i;\n")
            h_file.write("        }\n")
            h_file.write("    }\n")
            h_file.write("    \n")
            h_file.write("    return closest_index;\n")
            h_file.write("}\n\n")
            
            h_file.write("#endif // LOOKUP_TABLE_H\n")
        
        print(f"Lookup table created: {h_filepath}")
        print(f"Table contains {len(averaged_lookup)} position-distance pairs")
        
        return h_filepath

    def create_error_correction_table(self, max_distance_mm=700):
        """Create an error correction lookup table similar to the commented errorLookupTable in your C code"""
        if not self.sensor_distances or not self.linear_encoder_positions:
            print("No data available for creating error correction table.")
            return
        
        # Create error correction array
        correction_table = [0.0] * max_distance_mm
        
        # Calculate error for each measurement
        for i, (actual_pos, measured_dist) in enumerate(zip(self.linear_encoder_positions, self.sensor_distances)):
            error = measured_dist - actual_pos  # Error = measured - actual
            # Convert to index (assuming mm resolution and starting from 0)
            index = int(round(actual_pos))
            if 0 <= index < max_distance_mm:
                correction_table[index] = error
        
        # Fill gaps with interpolation
        for i in range(1, len(correction_table) - 1):
            if correction_table[i] == 0.0:  # No data point
                # Find nearest non-zero values
                left_val = 0.0
                right_val = 0.0
                left_idx = -1
                right_idx = -1
                
                # Search left
                for j in range(i - 1, -1, -1):
                    if correction_table[j] != 0.0:
                        left_val = correction_table[j]
                        left_idx = j
                        break
                
                # Search right
                for j in range(i + 1, len(correction_table)):
                    if correction_table[j] != 0.0:
                        right_val = correction_table[j]
                        right_idx = j
                        break
                
                # Linear interpolation
                if left_idx >= 0 and right_idx >= 0:
                    distance = right_idx - left_idx
                    weight = (i - left_idx) / distance
                    correction_table[i] = left_val + weight * (right_val - left_val)
                elif left_idx >= 0:
                    correction_table[i] = left_val
                elif right_idx >= 0:
                    correction_table[i] = right_val
        
        # Generate .h file
        dt = datetime.datetime.now()
        time_string = dt.strftime("%H_%M_%S")
        h_filename = f"error_correction_table_{time_string}.h"
        h_filepath = os.path.join(os.path.dirname(self.raw_data_filepath), h_filename)
        
        with open(h_filepath, 'w', encoding='utf-8') as h_file:
            h_file.write("// Error Correction Lookup Table\n")
            h_file.write("// Generated on: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            h_file.write("// Provides correction factors for sensor readings\n\n")
            h_file.write("#ifndef ERROR_CORRECTION_TABLE_H\n")
            h_file.write("#define ERROR_CORRECTION_TABLE_H\n\n")
            
            h_file.write("// Error correction table size (mm resolution)\n")
            h_file.write("#define ERROR_TABLE_SIZE {}\n\n".format(max_distance_mm))
            
            h_file.write("// Error correction lookup table (index = distance in mm, value = correction in mm)\n")
            h_file.write("static const float errorLookupTable[ERROR_TABLE_SIZE] = {\n")
            
            # Write the array with 10 values per line for readability
            for i in range(0, len(correction_table), 10):
                h_file.write("    ")
                for j in range(min(10, len(correction_table) - i)):
                    idx = i + j
                    comma = "," if idx < len(correction_table) - 1 else ""
                    h_file.write("{:.5f}f{}".format(correction_table[idx], comma))
                    if j < min(9, len(correction_table) - i - 1):
                        h_file.write(", ")
                h_file.write("\n")
            
            h_file.write("};\n\n")
            
            # Add helper function
            h_file.write("// Function to get error correction for a given distance\n")
            h_file.write("float getErrorCorrection(float distance_mm) {\n")
            h_file.write("    int index = (int)(distance_mm + 0.5f); // Round to nearest mm\n")
            h_file.write("    if (index >= 0 && index < ERROR_TABLE_SIZE) {\n")
            h_file.write("        return errorLookupTable[index];\n")
            h_file.write("    }\n")
            h_file.write("    return 0.0f; // No correction available\n")
            h_file.write("}\n\n")
            
            h_file.write("// Function to apply correction to a measured distance\n")
            h_file.write("float applyCorrectedDistance(float measured_distance_mm) {\n")
            h_file.write("    float correction = getErrorCorrection(measured_distance_mm);\n")
            h_file.write("    return measured_distance_mm - correction; // Subtract error to get corrected value\n")
            h_file.write("}\n\n")
            
            h_file.write("#endif // ERROR_CORRECTION_TABLE_H\n")
        
        print(f"Error correction table created: {h_filepath}")
        print(f"Table contains {max_distance_mm} correction values")
        
        return h_filepath

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

        with open(app.raw_data_filepath, mode="r", encoding="utf-8") as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                new_row = [float(value) for value in row]
                app.ws.append(new_row)

        app.wb.save(app.excel_filepath)
        
        # Create lookup tables
        app.create_lookup_table()
        app.create_error_correction_table()
        
        app.plot_results()
        app.cleanup()
        
    except KeyboardInterrupt:
        print("ALL DONE")
        sys.exit()
