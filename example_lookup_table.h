// Sensor Distance Lookup Table
// Generated on: 2025-11-26 10:30:45
// Maps linear encoder positions (mm) to sensor distances (mm)

#ifndef LOOKUP_TABLE_H
#define LOOKUP_TABLE_H

// Lookup table size
#define LOOKUP_TABLE_SIZE 5

// Position array (mm)
const float positions[LOOKUP_TABLE_SIZE] = {
    10.50f,
    20.75f,
    30.25f,
    40.00f,
    50.15f
};

// Distance array (mm)
const float distances[LOOKUP_TABLE_SIZE] = {
    10.45f,
    20.78f,
    30.22f,
    40.03f,
    50.12f
};

// Function to get distance for a given position (exact match)
float getDistanceForPosition(float position) {
    for (int i = 0; i < LOOKUP_TABLE_SIZE; i++) {
        if (positions[i] == position) {
            return distances[i];
        }
    }
    return -1.0f; // Position not found
}

// Function to get nearest distance for a position (interpolated)
float getNearestDistance(float position) {
    if (LOOKUP_TABLE_SIZE == 0) return -1.0f;
    
    // Check for exact match first
    for (int i = 0; i < LOOKUP_TABLE_SIZE; i++) {
        if (positions[i] == position) {
            return distances[i];
        }
    }
    
    // Find the two closest points for interpolation
    if (position <= positions[0]) {
        return distances[0]; // Return first value
    }
    if (position >= positions[LOOKUP_TABLE_SIZE - 1]) {
        return distances[LOOKUP_TABLE_SIZE - 1]; // Return last value
    }
    
    // Linear interpolation between two points
    for (int i = 0; i < LOOKUP_TABLE_SIZE - 1; i++) {
        if (position > positions[i] && position < positions[i + 1]) {
            float x1 = positions[i];
            float y1 = distances[i];
            float x2 = positions[i + 1];
            float y2 = distances[i + 1];
            
            // Linear interpolation formula
            float interpolated = y1 + (y2 - y1) * (position - x1) / (x2 - x1);
            return interpolated;
        }
    }
    
    return -1.0f; // Should not reach here
}

// Function to get the closest position index in the lookup table
int getClosestPositionIndex(float position) {
    int closest_index = 0;
    float min_diff = (position > positions[0]) ? position - positions[0] : positions[0] - position;
    
    for (int i = 1; i < LOOKUP_TABLE_SIZE; i++) {
        float diff = (position > positions[i]) ? position - positions[i] : positions[i] - position;
        if (diff < min_diff) {
            min_diff = diff;
            closest_index = i;
        }
    }
    
    return closest_index;
}

#endif // LOOKUP_TABLE_H