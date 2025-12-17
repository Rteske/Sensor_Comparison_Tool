import datetime
from sensor import Sensor
import os
import time
import csv
import sys
import numpy as np
import openpyxl
import matplotlib.pyplot as plt
import struct

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

        # Diagnostic data tracking
        self.error_log = []
        self.error_codes = []
        self.error_counts = []
        self.error_timestamps = []
        self.total_errors = 0
        self.last_error_code = 0
        self.error_history = []
        
        # Error code name mapping
        self.error_names = {
            0: "NONE",
            1: "CONFIG_CREATE",
            2: "PROCESSING_CREATE",
            3: "BUFFER_SIZE",
            4: "BUFFER_ALLOC",
            5: "SENSOR_CREATE",
            6: "CALIBRATION",
            7: "MEASURE",
            8: "INTERRUPT_TIMEOUT",
            9: "SENSOR_READ",
            10: "RECALIBRATION",
            11: "CAN_SEND",
            12: "ALGO_ERROR_EXCEEDED_MAX_DISTANCE",
        }
        
        # Performance timing data
        self.timer_names = {
            0: "TOTAL_FRAME",
            1: "SENSOR_MEASURE",
            2: "SENSOR_READ",
            3: "PROCESSING_EXECUTE",
            4: "CALIBRATION",
            5: "THRESHOLD_ALGO",
            6: "FIFO_AVERAGING",
            7: "CAN_TRANSMIT",
            8: "AMPLITUDE_CALC",
            9: "THRESHOLD_CHECK",
            10: "INTERPOLATION",
            11: "LUT_LOOKUP",
        }
        
        self.performance_data = {timer_id: {'avg': [], 'max': [], 'min': [], 'timestamps': []} 
                                  for timer_id in range(12)}

        self.wb = openpyxl.load_workbook(self.template_filepath)
        self.ws = self.wb["RAW_DATA"]

        # Temporary storage to correlate diagnostic frames
        self._pending_diag = {}

        self.init_instruments()

    def get_error_name(self, error_code):
        """Convert error code to human-readable name"""
        return self.error_names.get(error_code, f"UNKNOWN({error_code})")

    def log_diagnostic_data(self, error_code, error_count, error_timestamp_ms):
        """Log diagnostic error data from CAN messages"""
        self.error_codes.append(error_code)
        self.error_counts.append(error_count)
        self.error_timestamps.append(time.time())
        
        error_entry = {
            'code': error_code,
            'name': self.get_error_name(error_code),
            'count': error_count,
            'device_timestamp_ms': error_timestamp_ms,
            'system_timestamp': time.time()
        }
        self.error_log.append(error_entry)
        
        print(f"[DIAGNOSTIC] Error detected: {self.get_error_name(error_code)} (Code {error_code}), Count: {error_count}")

    def get_data(self):
        # Read any available frame and handle telemetry or diagnostic frames
        frame_type, payload = self.sensor.read_frame(timeout_s=0.05)
        if frame_type is None:
            return

        ts = time.time()
        # Telemetry distance frame (type 0x10): distance(4)|temp(2)|encoder(4)
        if frame_type == 0x10 and payload and len(payload) >= 10:
            distance_raw = struct.unpack('>I', payload[0:4])[0]
            temp_raw = struct.unpack('>H', payload[4:6])[0]
            encoder_raw = int.from_bytes(payload[6:10], byteorder='big', signed=True)

            distance = distance_raw / 10.0
            temp = float(temp_raw)
            linec = float(encoder_raw) * 0.01

            measurement_delta = abs(linec - distance)
            self.sensor_distances.append(distance)
            self.sensor_timestamps.append(ts)
            self.linear_encoder_positions.append(linec)
            self.measurement_deltas.append(measurement_delta)

            print(f"Delta: {measurement_delta}, Linear Encoder: {linec}, Distance: {distance}")
            self.write2file([distance, temp, linec, measurement_delta, ts])

        # Amplitude telemetry (type 0x11) - currently ignored but could be stored
        elif frame_type == 0x11 and payload and len(payload) >= 8:
            # optional: parse and log amplitude
            pass

        # Diagnostic frames
        elif frame_type == 0xA0 and payload and len(payload) >= 8:
            # error_code(4), error_count(4)
            error_code = struct.unpack('>I', payload[0:4])[0]
            error_count = struct.unpack('>I', payload[4:8])[0]
            # store until timestamp arrives
            self._pending_diag['code'] = error_code
            self._pending_diag['count'] = error_count

        elif frame_type == 0xA1 and payload and len(payload) >= 4:
            # error timestamp (ms)
            error_timestamp_ms = struct.unpack('>I', payload[0:4])[0]
            # if we have a pending code/count, log it
            code = self._pending_diag.get('code')
            count = self._pending_diag.get('count')
            if code is not None and count is not None:
                self.log_diagnostic_data(code, count, error_timestamp_ms)
                # clear pending
                self._pending_diag.pop('code', None)
                self._pending_diag.pop('count', None)

        elif frame_type == 0xA2 and payload and len(payload) >= 8:
            # total_errors(4), last_error(4)
            total_errors = struct.unpack('>I', payload[0:4])[0]
            last_error = struct.unpack('>I', payload[4:8])[0]
            self.total_errors = total_errors
            self.last_error_code = last_error
            print(f"[DIAG] TotalErrors: {total_errors} LastError: {last_error}")

        elif frame_type == 0xA3 and payload and len(payload) >= 5:
            # error history chunk: 4 errors + chunk id
            e1 = payload[0]
            e2 = payload[1]
            e3 = payload[2]
            e4 = payload[3]
            chunk = payload[4]
            self.error_history.extend([e1, e2, e3, e4])
            print(f"[DIAG] ErrorHistory Chunk {chunk}: [{e1},{e2},{e3},{e4}]")

        # Performance timing data (type 0xB0)
        elif frame_type == 0xB0 and payload and len(payload) >= 8:
            timer_id = payload[0]
            avg_us = (payload[1] << 8) | payload[2]
            max_us = (payload[3] << 8) | payload[4]
            min_us = (payload[5] << 8) | payload[6]
            count = payload[7]
            
            if timer_id < 12:
                self.performance_data[timer_id]['avg'].append(avg_us)
                self.performance_data[timer_id]['max'].append(max_us)
                self.performance_data[timer_id]['min'].append(min_us)
                self.performance_data[timer_id]['timestamps'].append(ts)
                
                timer_name = self.timer_names.get(timer_id, f"UNKNOWN_{timer_id}")
                print(f"[PERF] {timer_name}: avg={avg_us}us, max={max_us}us, min={min_us}us, count={count}")

        else:
            # unknown or unhandled frame types
            pass

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
        
        # Plot performance timing data
        self.plot_performance_timing()
    
    def plot_performance_timing(self):
        """Plot performance timing data for all timers"""
        # Check if any performance data was collected
        has_data = any(len(self.performance_data[tid]['avg']) > 0 for tid in range(12))
        if not has_data:
            print("No performance timing data collected for plotting.")
            return
        
        # Create subplots for different timer groups
        fig, axes = plt.subplots(3, 1, figsize=(14, 12))
        fig.suptitle('Performance Timing Analysis', fontsize=16)
        
        # Group 1: Main measurement loop timers (0-3)
        ax1 = axes[0]
        for timer_id in [0, 1, 2, 3]:  # TOTAL_FRAME, SENSOR_MEASURE, SENSOR_READ, PROCESSING_EXECUTE
            if len(self.performance_data[timer_id]['avg']) > 0:
                timer_name = self.timer_names[timer_id]
                avg_values = self.performance_data[timer_id]['avg']
                timestamps = self.performance_data[timer_id]['timestamps']
                start_time = timestamps[0] if timestamps else 0
                rel_times = [t - start_time for t in timestamps]
                ax1.plot(rel_times, avg_values, label=timer_name, marker='o', markersize=3)
        
        ax1.set_xlabel('Time (seconds)')
        ax1.set_ylabel('Execution Time (μs)')
        ax1.set_title('Main Measurement Loop Timers')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Group 2: Processing timers (4-7)
        ax2 = axes[1]
        for timer_id in [4, 5, 6, 7]:  # CALIBRATION, THRESHOLD_ALGO, FIFO_AVERAGING, CAN_TRANSMIT
            if len(self.performance_data[timer_id]['avg']) > 0:
                timer_name = self.timer_names[timer_id]
                avg_values = self.performance_data[timer_id]['avg']
                timestamps = self.performance_data[timer_id]['timestamps']
                start_time = timestamps[0] if timestamps else 0
                rel_times = [t - start_time for t in timestamps]
                ax2.plot(rel_times, avg_values, label=timer_name, marker='o', markersize=3)
        
        ax2.set_xlabel('Time (seconds)')
        ax2.set_ylabel('Execution Time (μs)')
        ax2.set_title('Processing & Communication Timers')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Group 3: Algorithm detail timers (8-11)
        ax3 = axes[2]
        for timer_id in [8, 9, 10, 11]:  # AMPLITUDE_CALC, THRESHOLD_CHECK, INTERPOLATION, LUT_LOOKUP
            if len(self.performance_data[timer_id]['avg']) > 0:
                timer_name = self.timer_names[timer_id]
                avg_values = self.performance_data[timer_id]['avg']
                timestamps = self.performance_data[timer_id]['timestamps']
                start_time = timestamps[0] if timestamps else 0
                rel_times = [t - start_time for t in timestamps]
                ax3.plot(rel_times, avg_values, label=timer_name, marker='o', markersize=3)
        
        ax3.set_xlabel('Time (seconds)')
        ax3.set_ylabel('Execution Time (μs)')
        ax3.set_title('Algorithm Detail Timers')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()
        
        # Create a summary bar chart showing average execution times
        fig2, ax = plt.subplots(figsize=(12, 6))
        
        timer_labels = []
        avg_times = []
        max_times = []
        min_times = []
        
        for timer_id in range(12):
            if len(self.performance_data[timer_id]['avg']) > 0:
                timer_labels.append(self.timer_names[timer_id])
                avg_times.append(np.mean(self.performance_data[timer_id]['avg']))
                max_times.append(np.max(self.performance_data[timer_id]['max']))
                min_times.append(np.min(self.performance_data[timer_id]['min']))
        
        if timer_labels:
            x = np.arange(len(timer_labels))
            width = 0.25
            
            ax.bar(x - width, min_times, width, label='Min', color='green', alpha=0.7)
            ax.bar(x, avg_times, width, label='Avg', color='blue', alpha=0.7)
            ax.bar(x + width, max_times, width, label='Max', color='red', alpha=0.7)
            
            ax.set_xlabel('Timer')
            ax.set_ylabel('Execution Time (μs)')
            ax.set_title('Performance Timing Summary (Min/Avg/Max)')
            ax.set_xticks(x)
            ax.set_xticklabels(timer_labels, rotation=45, ha='right')
            ax.legend()
            ax.grid(True, alpha=0.3, axis='y')
            
            plt.tight_layout()
            plt.show()
            
            # Print summary statistics
            print("\n" + "="*60)
            print("PERFORMANCE TIMING SUMMARY")
            print("="*60)
            for i, label in enumerate(timer_labels):
                print(f"{label:25} Min: {min_times[i]:8.2f}μs  Avg: {avg_times[i]:8.2f}μs  Max: {max_times[i]:8.2f}μs")
            print("="*60 + "\n")

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

    def print_diagnostic_summary(self):
        """Print summary of all diagnostic data collected during the session"""
        if self.error_log:
            print("\n" + "="*50)
            print("DIAGNOSTIC ERROR SUMMARY")
            print("="*50)
            print(f"Total errors detected: {len(self.error_log)}")
            print(f"Last error code: {self.last_error_code} ({self.get_error_name(self.last_error_code)})")
            print(f"Total error count: {self.total_errors}")
            
            # Count errors by type
            error_type_counts = {}
            for entry in self.error_log:
                name = entry['name']
                error_type_counts[name] = error_type_counts.get(name, 0) + 1
            
            print("\nError breakdown by type:")
            for error_name, count in sorted(error_type_counts.items()):
                print(f"  {error_name}: {count}")
            
            if self.error_history:
                non_zero_history = [self.get_error_name(e) for e in self.error_history if e != 0]
                if non_zero_history:
                    print(f"\nError history: {non_zero_history}")
            
            print("="*50 + "\n")
        else:
            print("\n[DIAGNOSTIC] No errors detected during this session.\n")

    def save_diagnostic_log(self):
        """Save diagnostic error log to CSV file"""
        if not self.error_log:
            return
        
        dt = datetime.datetime.now()
        time_string = dt.strftime("%H_%M_%S")
        diag_filepath = os.path.join(os.path.dirname(self.raw_data_filepath), f"diagnostics_{time_string}.csv")
        
        with open(diag_filepath, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Error Code", "Error Name", "Error Count", "Device Timestamp (ms)", "System Timestamp"])
            
            for entry in self.error_log:
                writer.writerow([
                    entry['code'],
                    entry['name'],
                    entry['count'],
                    entry['device_timestamp_ms'],
                    entry['system_timestamp']
                ])
        
        print(f"Diagnostic log saved: {diag_filepath}")
        return diag_filepath
    
    def save_performance_log(self):
        """Save performance timing data to CSV file"""
        has_data = any(len(self.performance_data[tid]['avg']) > 0 for tid in range(12))
        if not has_data:
            return
        
        dt = datetime.datetime.now()
        time_string = dt.strftime("%H_%M_%S")
        perf_filepath = os.path.join(os.path.dirname(self.raw_data_filepath), f"performance_{time_string}.csv")
        
        with open(perf_filepath, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Timer ID", "Timer Name", "Avg (us)", "Max (us)", "Min (us)", "System Timestamp"])
            
            for timer_id in range(12):
                if len(self.performance_data[timer_id]['avg']) > 0:
                    timer_name = self.timer_names[timer_id]
                    for i in range(len(self.performance_data[timer_id]['avg'])):
                        writer.writerow([
                            timer_id,
                            timer_name,
                            self.performance_data[timer_id]['avg'][i],
                            self.performance_data[timer_id]['max'][i],
                            self.performance_data[timer_id]['min'][i],
                            self.performance_data[timer_id]['timestamps'][i]
                        ])
        
        print(f"Performance log saved: {perf_filepath}")
        return perf_filepath

    def cleanup(self):
        if os.path.exists(self.raw_data_filepath):
            os.remove(self.raw_data_filepath)

if __name__ == "__main__":
    app = SensorComparison()

    total_time = 35

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
        
        # Print and save diagnostic information
        app.print_diagnostic_summary()
        app.save_diagnostic_log()
        app.save_performance_log()
        
        # Create lookup tables
        app.create_lookup_table()
        
        app.plot_results()
        app.cleanup()
        
    except KeyboardInterrupt:
        print("ALL DONE")
        sys.exit()
