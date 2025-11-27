// Copyright (c) Acconeer AB, 2020-2023
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "acc_config.h"
#include "acc_definitions_a121.h"
#include "acc_definitions_common.h"
#include "acc_hal_definitions_a121.h"
#include "acc_hal_integration_a121.h"
#include "acc_integration.h"
#include "acc_processing.h"
#include "acc_rss_a121.h"
#include "acc_sensor.h"

#include "acc_version.h"
#include "math.h"
#include "print_data_config.h"
#include "processed_data.h"
#include "fifo_buff.h"

#include "fdcan.h"
#include "gpio.h"

// Include generated lookup tables from sensor comparison tool
#include "lookup_table.h"          // Position-distance lookup table
#include "error_correction_table.h" // Error correction lookup table


/** \example example_service.c
 * @brief This is an example on how the Service API can be used
 * @n
 * The example executes as follows:
 *   - Create a configuration
 *   - Create a processing instance using the previously created configuration
 *   - Create a sensor instance
 *   - Prepare a sensor
 *   - Perform a sensor measurement and read out the data
 *   - Process the measurement
 *   - Check 'calibration_needed' indication
 *   - Destroy the sensor instance
 *   - Destroy the processing instance
 *   - Destroy the configuration
 */

#define SENSOR_ID          (1U)
#define SENSOR_TIMEOUT_MS  (1000U)
#define MAX_DATA_ENTRY_LEN (15U) // "-32000+-32000i" + zero termination

extern FDCAN_HandleTypeDef hfdcan1;

static void set_config(acc_config_t *config, PrintDataConfig *print_data_config);


static bool do_sensor_calibration_and_prepare(acc_sensor_t *sensor, acc_config_t *config, void *buffer, uint32_t buffer_size);


uint32_t run_simple_threshold_algo(acc_int16_complex_t *data, uint16_t data_length, PrintDataConfig *print_data_config, uint16_t temp, ProcessedData *proc_data);

uint32_t run_delay_n_compare_algo(acc_int16_complex_t *data, uint16_t data_length, PrintDataConfig *print_data_config, uint16_t temp);

static void cleanup(acc_config_t *config, acc_processing_t *processing,
                    acc_sensor_t *sensor, void *buffer);

// Helper function to check if lookup tables are available and valid
static bool lookup_tables_available(void);

// Enhanced distance correction using generated lookup tables
static float apply_distance_correction(float raw_distance_mm);

int acc_service(int argc, char *argv[], PrintDataConfig *print_data_config);


int acc_service(int argc, char *argv[], PrintDataConfig *print_data_config)
{
        (void)argc;
        (void)argv;
        acc_config_t              *config     = NULL;
        acc_processing_t          *processing = NULL;
        acc_sensor_t              *sensor     = NULL;
        void                      *buffer     = NULL;
        uint32_t                  buffer_size = 0;
        acc_processing_metadata_t proc_meta;
        acc_processing_result_t   proc_result;
        uint32_t timestamp = 0;
        uint32_t timestamp_delta = 0;
        int first_success = 0;
        int second_success = 1;


        FIFOBuffer lastHeldValues;
        initBuffer(&lastHeldValues);
//        printf("Acconeer software version %s\n", acc_version_get());

        const acc_hal_a121_t *hal = acc_hal_rss_integration_get_implementation();

        if (!acc_rss_hal_register(hal))
        {
                return EXIT_FAILURE;
        }

        config = acc_config_create();
        if (config == NULL)
        {
                printf("acc_config_create() failed\n");
                cleanup(config, processing, sensor, buffer);
                return EXIT_FAILURE;
        }

        set_config(config, print_data_config);

        // Print the configuration
//        acc_config_log(config);

        processing = acc_processing_create(config, &proc_meta);
        if (processing == NULL)
        {
                printf("acc_processing_create() failed\n");
                cleanup(config, processing, sensor, buffer);
                return EXIT_FAILURE;
        }

        if (!acc_rss_get_buffer_size(config, &buffer_size))
        {
                printf("acc_rss_get_buffer_size() failed\n");
                cleanup(config, processing, sensor, buffer);
                return EXIT_FAILURE;
        }

        buffer = acc_integration_mem_alloc(buffer_size);
        if (buffer == NULL)
        {
                printf("buffer allocation failed\n");
                cleanup(config, processing, sensor, buffer);
                return EXIT_FAILURE;
        }

        acc_hal_integration_sensor_supply_on(SENSOR_ID);
        acc_hal_integration_sensor_enable(SENSOR_ID);

        sensor = acc_sensor_create(SENSOR_ID);
        if (sensor == NULL)
        {
                printf("acc_sensor_create() failed\n");
                cleanup(config, processing, sensor, buffer);
                return EXIT_FAILURE;
        }

        if (!do_sensor_calibration_and_prepare(sensor, config, buffer, buffer_size))
        {
                printf("do_sensor_calibration_and_prepare() failed\n");
                acc_sensor_status(sensor);
                cleanup(config, processing, sensor, buffer);
                return EXIT_FAILURE;
        }

        // Check if lookup tables are available
        if (lookup_tables_available()) {
            printf("Lookup tables loaded successfully for distance correction\n");
        } else {
            printf("Warning: No lookup tables found, using raw sensor data\n");
        }

        float distance = 0.0;
        ProcessedData proc_data = {
			.divisor = 0,
			.first_threshold_x = 0,
			.first_threshold_y = 0,
			.max_amplitude = 0,
			.temp = 0,
			.threshold_crossed = 0,
			.selected_distance = 0
        };

        while (1) {
//			HAL_GPIO_WritePin(ALARM_LIGHT_GPIO_Port, ALARM_LIGHT_Pin, GPIO_PIN_SET);
		//	HAL_Delay(1);
//			HAL_GPIO_WritePin(ALARM_LIGHT_GPIO_Port, ALARM_LIGHT_Pin, GPIO_PIN_RESET);

    		if (!acc_sensor_measure(sensor))
    		{
    				printf("acc_sensor_measure failed\n");
    				acc_sensor_status(sensor);
    				cleanup(config, processing, sensor, buffer);
    				return EXIT_FAILURE;
    		}

    		if (!acc_hal_integration_wait_for_sensor_interrupt(SENSOR_ID, SENSOR_TIMEOUT_MS))
    		{
    				printf("Sensor interrupt timeout\n");
    				acc_sensor_status(sensor);
    				cleanup(config, processing, sensor, buffer);
    				return EXIT_FAILURE;
    		}

    		if (!acc_sensor_read(sensor, buffer, buffer_size))
    		{
    				printf("acc_sensor_read failed\n");
    				acc_sensor_status(sensor);
    				cleanup(config, processing, sensor, buffer);
    				return EXIT_FAILURE;
    		}

    		acc_processing_execute(processing, buffer, &proc_result);

//			HAL_GPIO_WritePin(ALARM_LIGHT_GPIO_Port, ALARM_LIGHT_Pin, GPIO_PIN_SET);
		//	HAL_Delay(3);
//			HAL_GPIO_WritePin(ALARM_LIGHT_GPIO_Port, ALARM_LIGHT_Pin, GPIO_PIN_RESET);

    		if (proc_result.calibration_needed)
    		{
    				printf("The current calibration is not valid for the current temperature.\n");
    				printf("The sensor needs to be re-calibrated.\n");

    				if (!do_sensor_calibration_and_prepare(sensor, config, buffer, buffer_size))
    				{
    						printf("do_sensor_calibration_and_prepare() failed\n");
    						acc_sensor_status(sensor);
    						cleanup(config, processing, sensor, buffer);
    						return EXIT_FAILURE;
    				}
    				printf("The sensor was successfully re-calibrated.\n");
    		}
    		else {
    			printf("sync\n");
//    			HAL_GPIO_TogglePin(ALARM_LIGHT_GPIO_Port, ALARM_LIGHT_Pin);
    			if (print_data_config->algo == 1) {
    				distance = run_simple_threshold_algo(proc_result.frame, proc_meta.frame_data_length, print_data_config, proc_result.temperature, &proc_data);
    			}
    			uint16_t temp = proc_result.temperature;

    			// START FIFO BUFFER AVERAGING
    			if (isFull(&lastHeldValues)) {
    				dequeue(&lastHeldValues);
    			}

    			enqueue(&lastHeldValues, distance);
    			uint32_t avg_distance;
    			if (print_data_config->avg_type == 1) {
    				avg_distance= getAverage(&lastHeldValues);
    			} else if (print_data_config->avg_type == 2) {
    				avg_distance = computeWeightedAvg(&lastHeldValues, print_data_config->wma_factor, print_data_config->wma_start);
    			} else {
    				avg_distance = distance;
    			}

    			// END FIFO

    			// COMMENT LINE BELOW TO ALLOW AVERAGING
   // 			uint32_t avg_distance = distance;

    			uint32_t first_threshold_y = (uint16_t)proc_data.first_threshold_y;
    			uint32_t max_amplitude = proc_data.max_amplitude;
    			uint32_t first_threshold_x = (uint16_t)proc_data.first_threshold_x * 10000;
    			uint16_t divisor = (uint16_t)proc_data.divisor;

     			uint8_t data[8];

    			data[0] = (max_amplitude >> 24) & 0xFF;
    			data[1] = (max_amplitude >> 16) & 0xFF;
    			data[2] = (max_amplitude >> 8) & 0xFF;
    			data[3] = max_amplitude & 0xFF;
    			data[4] = (first_threshold_y >> 24) & 0xFF;
    			data[5] = (first_threshold_y >> 16) & 0xFF;
    			data[6] = (first_threshold_y >> 8) & 0xFF;
    			data[7] = first_threshold_y & 0xFF;

    			int ret = MX_FDCAN1_Send(0x14, data);
    			if (ret == 0) {
    				printf("still failed after 10 times try");
    				first_success = 0;
    			} else {
    				first_success = 1;
    			}

    			HAL_Delay(1);

				data[0] = (avg_distance >> 24) & 0xFF;
				data[1] = (avg_distance >> 16) & 0xFF;
				data[2] = (avg_distance >> 8) & 0xFF;
				data[3] = avg_distance & 0xFF;
				data[4] = (divisor >> 8) & 0xFF;
				data[5] = divisor & 0xFF;
				data[6] = (temp >> 8) & 0xFF;
				data[7] = temp & 0xFF;

				ret = MX_FDCAN1_Send(0x13, data);
    			if (ret == 0) {
    				printf("still failed after 10 times try");
    				second_success = 0;
    			} else {
    				second_success = 1;
    			}
				HAL_Delay(2);

				if (first_success && second_success) {
		   			// calculate the time stamp
					uint32_t current_timestamp = HAL_GetTick();
					timestamp_delta = current_timestamp - timestamp;
					timestamp = current_timestamp;

					MX_TEST_LED_Toggle();
				}
    		}
        }

        cleanup(config, processing, sensor, buffer);
}


static void set_config(acc_config_t *config, PrintDataConfig *print_data_config)
{
    // Add configuration of the sensor here
    acc_config_sweeps_per_frame_set(config, print_data_config->sweeps_per_frame);
    acc_config_frame_rate_set(config, print_data_config->frame_rate);
    acc_config_start_point_set(config, print_data_config->start_point);
    acc_config_num_points_set(config, print_data_config->num_points);
    acc_config_step_length_set(config, print_data_config->step);
    acc_config_profile_set(config, print_data_config->profile);
    acc_config_receiver_gain_set(config, print_data_config->receiver_gain);
    acc_config_prf_set(config, print_data_config->prf);
    // Hardware Averaging must be set from 511-1
    acc_config_hwaas_set(config, print_data_config->ave);
    acc_config_phase_enhancement_set(config, true);
//    acc_config_enable_loopback_set(config, true);

}


static bool do_sensor_calibration_and_prepare(acc_sensor_t *sensor, acc_config_t *config, void *buffer, uint32_t buffer_size)
{
        bool             status       = false;
        bool             cal_complete = false;
        acc_cal_result_t cal_result;
        const uint16_t   calibration_retries = 1U;

        // Random disturbances may cause the calibration to fail. At failure, retry at least once.
        for (uint16_t i = 0; !status && (i <= calibration_retries); i++)
        {
                // Reset sensor before calibration by disabling/enabling it
                acc_hal_integration_sensor_disable(SENSOR_ID);
                acc_hal_integration_sensor_enable(SENSOR_ID);

                do
                {
                        status = acc_sensor_calibrate(sensor, &cal_complete, &cal_result, buffer, buffer_size);

                        if (status && !cal_complete)
                        {
                                status = acc_hal_integration_wait_for_sensor_interrupt(SENSOR_ID, SENSOR_TIMEOUT_MS);
                        }
                } while (status && !cal_complete);
        }

        if (status)
        {
                // Reset sensor after calibration by disabling/enabling it
                acc_hal_integration_sensor_disable(SENSOR_ID);
                acc_hal_integration_sensor_enable(SENSOR_ID);

                status = acc_sensor_prepare(sensor, config, &cal_result, buffer, buffer_size);
        }

        return status;
}

uint32_t run_simple_threshold_algo(acc_int16_complex_t *data, uint16_t data_length, PrintDataConfig *print_data_config, uint16_t temp, ProcessedData *proc_data)
{
		float rf_factor_step = 0.0025 / print_data_config->rf_factor; // meters
	    float selected = 0;

	    uint16_t divisor = (-15 * temp) + 1600;
	    if (divisor < 0 ) {
	    	divisor = 1;
	    } else {
	    	divisor = round(divisor);
		}

	    int num_points = print_data_config->num_points;
	    int sweeps_per_frame = print_data_config->sweeps_per_frame;
		if (data_length == num_points * sweeps_per_frame) {
			uint32_t amplitudes[400] = {0};
			float distances[400] = {0};

			int first_threshold_index = 0;

			float first_threshold_x = 0;
			float first_threshold_y = 0;
			float first_below_threshold_x = 0;
			float first_below_threshold_y = 0;
			float threshold_crossed = 0;
			float max_amplitude = 0;

			// Loop unrolling and precomputation

			for (uint16_t sweep_index = 0; sweep_index < num_points; sweep_index++) {
				uint32_t amplitude = (data[sweep_index].real * data[sweep_index].real + data[sweep_index].imag * data[sweep_index].imag) / divisor;
			    amplitudes[sweep_index] = amplitude;
			    if (amplitude > max_amplitude) {
			    	max_amplitude = amplitude;
			    }

			    float distance = (sweep_index * rf_factor_step * print_data_config->step) + (print_data_config->start_point * rf_factor_step);
			    distances[sweep_index] = distance;
			    // First threshold check, make this outside the inner loop
			    float threshold = 0;

		        if ((distance >= print_data_config->x_intercepts[0]) && (distance <= print_data_config->x_intercepts[1]))
		        {
		            threshold = (distance * print_data_config->line1_slope) + print_data_config->y_inter_line1;
		        }
		        else if ((distance > print_data_config->x_intercepts[1]) && (distance <= print_data_config->x_intercepts[2]))
		        {
		            threshold = (distance * print_data_config->line2_slope) + print_data_config->y_inter_line2;
		        }
		        else if ((distance > print_data_config->x_intercepts[2]) && (distance <= print_data_config->x_intercepts[3]))
		        {
		            threshold = (distance * print_data_config->line3_slope) + print_data_config->y_inter_line3;
		        }

			    if (first_threshold_x == 0 && (amplitude - threshold) > 0) {
			        first_threshold_x = distance;
			        first_threshold_y = amplitude;
			        first_threshold_index = sweep_index;
			        threshold_crossed = threshold;

			        if (sweep_index > 0) {
			            first_below_threshold_x = distances[first_threshold_index - 1];
			            first_below_threshold_y = amplitudes[first_threshold_index - 1];
			        }
			        break;
			    }
			}

			if (first_threshold_index != 0)
			{
				selected = (first_below_threshold_x) + ((threshold_crossed - first_below_threshold_y )/ (first_threshold_y - first_below_threshold_y)) * (first_threshold_x - first_below_threshold_x);
				
				// Apply lookup table corrections using helper function
				float corrected_distance_mm = apply_distance_correction(selected * 1000); // Convert to mm
				selected = corrected_distance_mm / 1000; // Convert back to meters
				
				uint32_t distance = (uint32_t)(selected * 10000);

				proc_data->selected_distance = distance;
				proc_data->divisor = (uint16_t)(divisor);
				proc_data->first_threshold_x = (uint32_t)(first_threshold_x * 10000);
				proc_data->first_threshold_y = (uint32_t)(first_threshold_y);
				proc_data->max_amplitude = (uint32_t)(max_amplitude);

				return distance;
			}
		}
	return 0;
}

uint32_t run_delay_n_compare_algo(acc_int16_complex_t *data, uint16_t data_length, PrintDataConfig *print_data_config, uint16_t temp) {
    float selected = 9999999;
    int selected_amplitude = 9999999;

    uint16_t divisor = (-15 * temp) + 1600;
    if (divisor < 0 ) {
    	divisor = 1;
    } else {
    	divisor = round(divisor);
	}

    if (data_length == print_data_config->num_points * print_data_config->sweeps_per_frame) {
        float amplitudes[400] = {0};
        float distances[400] = {0};

        int first_threshold_index = 0;

        uint16_t num_points = print_data_config->num_points; // Cache this

        int found_threshold_crossing = 0;

        for (uint16_t sweep_index = 0; sweep_index < num_points; sweep_index++) {
            float amplitude = ((data[sweep_index].real * data[sweep_index].real) + (data[sweep_index].imag * data[sweep_index].imag)) / divisor;
//            if (amplitude > 650000) {
//            	amplitude = 999999;
//            }
            amplitudes[sweep_index] = amplitude;
            float distance = (sweep_index * 0.0025f) + (print_data_config->start * 0.0025f);
            distances[sweep_index] = distance;

            float threshold = 0;

            if ((distance >= print_data_config->x_intercepts[0]) && (distance <= print_data_config->x_intercepts[1])) {
                threshold = (distance * print_data_config->line1_slope) + print_data_config->y_inter_line1;
            } else if ((distance >= print_data_config->x_intercepts[1]) && (distance <= print_data_config->x_intercepts[2])) {
                threshold = (distance * print_data_config->line2_slope) + print_data_config->y_inter_line2;
            }

            if ((amplitude - threshold) > 0 && found_threshold_crossing == 0) {
                found_threshold_crossing = 1;
                first_threshold_index = sweep_index;
            }
        }

        int max_amplitude_index = 0;
        float max_amplitude = 0;

        if (found_threshold_crossing && ((distances[first_threshold_index] >= print_data_config->x_intercepts[1]) && (distances[first_threshold_index] <= print_data_config->x_intercepts[2]))) {
        	max_amplitude = amplitudes[first_threshold_index];

            for (uint16_t i = first_threshold_index; i < first_threshold_index + print_data_config->peak_search_range && i < num_points; i++) {
                if (amplitudes[i] > max_amplitude) {
                    max_amplitude = amplitudes[i];
                    max_amplitude_index = i;
                }
            }

//            float max_amplitude_distance = distances[max_amplitude_index];
            float new_threshold = max_amplitude / print_data_config->threshold_divisor;

            float new_threshold_crossing_x = 0.0f;
            uint16_t new_threshold_crossing_index = 0;

            int range_start = 0;
            if (first_threshold_index >= 25) {
            	range_start = first_threshold_index - 25;
            }

			for (uint16_t i = range_start; i < max_amplitude_index; i++) {
				if (amplitudes[i] >new_threshold && new_threshold_crossing_index == 0) {
					new_threshold_crossing_index = i;
					break;
				}
			}

            float slope = (float)(amplitudes[new_threshold_crossing_index] - amplitudes[new_threshold_crossing_index - 1]) / (distances[new_threshold_crossing_index] - distances[new_threshold_crossing_index - 1]);
            float y_intercept = -((slope * distances[new_threshold_crossing_index]) - amplitudes[new_threshold_crossing_index]);

            selected = (new_threshold - y_intercept) / slope;
            selected_amplitude = new_threshold;
        } else if (found_threshold_crossing && ((distances[first_threshold_index] >= print_data_config->x_intercepts[0]) && (distances[first_threshold_index] < print_data_config->x_intercepts[1]))) {
//            for (uint16_t i = print_data_config->x_intercepts[0]; i < print_data_config->x_intercepts[1]; i++) {
//                if (amplitudes[i] > max_amplitude) {
//                    max_amplitude = amplitudes[i];
//                    max_amplitude_index = i;
//                }
//            }


            selected = distances[max_amplitude_index];
            selected_amplitude = max_amplitude;
        }
    }

    selected = selected / print_data_config->rf_factor;
    uint32_t distance = (uint32_t)(selected * 1000);

    return distance;

}


static void cleanup(acc_config_t *config, acc_processing_t *processing,
                    acc_sensor_t *sensor, void *buffer)
{
        acc_hal_integration_sensor_disable(SENSOR_ID);
        acc_hal_integration_sensor_supply_off(SENSOR_ID);

        if (sensor != NULL)
        {
                acc_sensor_destroy(sensor);
        }

        if (processing != NULL)
        {
                acc_processing_destroy(processing);
        }

        if (config != NULL)
        {
                acc_config_destroy(config);
        }

        if (buffer != NULL)
        {
                acc_integration_mem_free(buffer);
        }
}

// Helper function to check if lookup tables are available and valid
static bool lookup_tables_available(void) {
#ifdef LOOKUP_TABLE_SIZE
    return (LOOKUP_TABLE_SIZE > 0);
#else
    return false;
#endif
}

// Enhanced distance correction using generated lookup tables
static float apply_distance_correction(float raw_distance_mm) {
    if (!lookup_tables_available()) {
        // No lookup tables available, return raw distance
        return raw_distance_mm;
    }
    
#ifdef ERROR_TABLE_SIZE
    // Apply error correction first
    float corrected_distance = applyCorrectedDistance(raw_distance_mm);
    
    // Optionally validate with position-distance lookup
    #ifdef LOOKUP_TABLE_SIZE
    float lookup_distance = getNearestDistance(corrected_distance);
    if (lookup_distance > 0) {
        // Use lookup result if significantly different and valid
        float difference = (lookup_distance > corrected_distance) ? 
                          lookup_distance - corrected_distance : 
                          corrected_distance - lookup_distance;
        
        // If lookup and correction differ by more than 2mm, prefer lookup
        if (difference > 2.0f) {
            return lookup_distance;
        }
    }
    #endif
    
    return corrected_distance;
#else
    // Only position-distance lookup available
    #ifdef LOOKUP_TABLE_SIZE
    float lookup_distance = getNearestDistance(raw_distance_mm);
    return (lookup_distance > 0) ? lookup_distance : raw_distance_mm;
    #else
    return raw_distance_mm;
    #endif
#endif
}
