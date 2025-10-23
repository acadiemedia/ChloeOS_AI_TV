import re
import os
import random
import time
from datetime import datetime, timedelta

# Configuration
CONTENT_REPO_PATH = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_PATH = os.path.join(CONTENT_REPO_PATH, "scripts")
METADATA_PATH = os.path.join(CONTENT_REPO_PATH, "metadata")

NOON_PULSE_TAG = "Noon Educational Pulse"
MIDNIGHT_PULSE_TAG = "Midnight Adult Pulse"

SEGMENT_DURATIONS = {
    "Animated Animal Comedy": timedelta(minutes=15),
    "AI Talk Show": timedelta(minutes=20),
    "Human Reflection Session": timedelta(minutes=10),
}

def load_content_plan(plan_filename="first_cycle_content_plan.md"):
    """Loads the content plan from the metadata directory."""
    plan_filepath = os.path.join(METADATA_PATH, plan_filename)
    if not os.path.exists(plan_filepath):
        print(f"Error: Content plan not found at {plan_filepath}")
        return None

    with open(plan_filepath, 'r') as f:
        content = f.read()

    # Simple parsing to extract segments for each pulse
    noon_pulse_content = []
    midnight_pulse_content = []

    current_pulse = None
    for line in content.split('\n'):
        if NOON_PULSE_TAG in line:
            current_pulse = NOON_PULSE_TAG
        elif MIDNIGHT_PULSE_TAG in line:
            current_pulse = MIDNIGHT_PULSE_TAG
        elif current_pulse and "Segment" in line:
            match = re.search(r'Segment \d+: (.*?)(?: - |$)', line)
            if match:
                segment_type = match.group(1).strip()
                if current_pulse == NOON_PULSE_TAG:
                    noon_pulse_content.append(segment_type)
                elif current_pulse == MIDNIGHT_PULSE_TAG:
                    midnight_pulse_content.append(segment_type)
    
    # Remove duplicates and maintain order
    noon_pulse_content = list(dict.fromkeys(noon_pulse_content))
    midnight_pulse_content = list(dict.fromkeys(midnight_pulse_content))

    return {
        NOON_PULSE_TAG: noon_pulse_content,
        MIDNIGHT_PULSE_TAG: midnight_pulse_content,
    }

def load_content_plan_with_titles(plan_filename="first_cycle_content_plan.md"):
    """Loads the content plan from the metadata directory, returning segment types and their example topics."""
    plan_filepath = os.path.join(METADATA_PATH, plan_filename)
    if not os.path.exists(plan_filepath):
        print(f"Error: Content plan not found at {plan_filepath}")
        return None

    with open(plan_filepath, 'r') as f:
        content = f.read()

    content_plan_with_topics = {
        NOON_PULSE_TAG: {},
        MIDNIGHT_PULSE_TAG: {},
    }

    current_pulse = None
    current_segment_type = None
    for line in content.split('\n'):
        if NOON_PULSE_TAG in line:
            current_pulse = NOON_PULSE_TAG
        elif MIDNIGHT_PULSE_TAG in line:
            current_pulse = MIDNIGHT_PULSE_TAG
        elif current_pulse and "### Segment" in line:
            match = re.search(r'Segment \d+: (.*?)(?: - |$)', line)
            if match:
                current_segment_type = match.group(1).strip()
                if current_pulse == NOON_PULSE_TAG:
                    if current_segment_type not in content_plan_with_topics[NOON_PULSE_TAG]:
                        content_plan_with_topics[NOON_PULSE_TAG][current_segment_type] = []
                elif current_pulse == MIDNIGHT_PULSE_TAG:
                    if current_segment_type not in content_plan_with_topics[MIDNIGHT_PULSE_TAG]:
                        content_plan_with_topics[MIDNIGHT_PULSE_TAG][current_segment_type] = []
        elif current_pulse and current_segment_type and "*   **Example Topics:**" in line:
            topics_str = line.split('**Example Topics:**')[1].strip()
            # Extract topics, handling quotes and commas
            # This regex now specifically looks for quoted strings or unquoted strings separated by commas
            topics = []
            for topic_tuple in re.findall(r'"(.*?)"|([^,]+)', topics_str):
                topic = (topic_tuple[0] or topic_tuple[1]).strip().strip('\"').strip('.').strip(',')
                if topic:
                    topics.append(topic)
            for topic in topics:
                if topic:
                    if current_pulse == NOON_PULSE_TAG:
                        content_plan_with_topics[NOON_PULSE_TAG][current_segment_type].append(topic)
                    elif current_pulse == MIDNIGHT_PULSE_TAG:
                        content_plan_with_topics[MIDNIGHT_PULSE_TAG][current_segment_type].append(topic)
    return content_plan_with_topics

def get_available_scripts():
    """Scans the scripts directory and categorizes them by type based on the content plan's example topics."""
    scripts = {
        "Animated Animal Comedy": [],
        "AI Talk Show": [],
        "Human Reflection Session": [],
    }
    
    content_plan_with_topics = load_content_plan_with_titles()
    if not content_plan_with_topics:
        print("Error: Could not load content plan with topics for script categorization.")
        return scripts

    # Create a flattened mapping from example topic to segment type
    example_topic_to_segment_type = {}
    for pulse_type in [NOON_PULSE_TAG, MIDNIGHT_PULSE_TAG]:
        for segment_type, topics in content_plan_with_topics[pulse_type].items():
            for topic in topics:
                example_topic_to_segment_type[topic] = segment_type

    for filename in os.listdir(SCRIPTS_PATH):
        if filename.endswith(".md"):
            filepath = os.path.join(SCRIPTS_PATH, filename)
            with open(filepath, 'r') as f:
                first_line = f.readline().strip()
                title_match = re.match(r'# Script: (.*)', first_line)
                if title_match:
                    script_title = title_match.group(1).strip()
                    # Try to match the script title to an example topic
                    found_match = False
                    script_title_normalized = script_title.lower().strip()
                    for example_topic, segment_type in example_topic_to_segment_type.items():
                        example_topic_normalized = example_topic.lower().strip()
                        if script_title_normalized == example_topic_normalized:
                            scripts[segment_type].append(filepath)
                            found_match = True
                            break
                    if not found_match:
                        print(f"DEBUG: Script title normalized: '{script_title_normalized}' (len: {len(script_title_normalized)})")
                        print(f"DEBUG: Example topics normalized: {[t for t in example_topic_to_segment_type.keys()]}")
                        print(f"Warning: Script title '{script_title}' from {filename} not found in content plan example topics. Skipping.")
                else:
                    print(f"Warning: Could not extract title from {filename}. Skipping.")
    return scripts

def simulate_chloe_tv_cycle():
    """Simulates a 24-hour Chloe TV cycle."""
    content_plan_with_topics = load_content_plan_with_titles()
    if not content_plan_with_topics:
        return

    available_scripts = get_available_scripts()

    print("--- Starting Chloe TV 24-Hour Cycle Simulation ---")

    current_time = datetime.now()
    
    # Extract just the segment types for scheduling purposes
    noon_pulse_segments = list(content_plan_with_topics[NOON_PULSE_TAG].keys())
    midnight_pulse_segments = list(content_plan_with_topics[MIDNIGHT_PULSE_TAG].keys())
    
    for _ in range(2): # Simulate 2 rotations of the 3 segments to fill 6 hours
        random.shuffle(noon_pulse_segments) # Randomize order for variety
        for segment_type in noon_pulse_segments:
            if available_scripts[segment_type]:
                script_path = random.choice(available_scripts[segment_type])
                duration = SEGMENT_DURATIONS.get(segment_type, timedelta(minutes=10))
                print(f"  Playing: {segment_type} - {os.path.basename(script_path)} (Duration: {duration})")
            else:
                duration = SEGMENT_DURATIONS.get(segment_type, timedelta(minutes=10))
                print(f"  Warning: No scripts available for {segment_type} in {NOON_PULSE_TAG}. Simulating duration: {duration}")
            current_time += duration

    # Midnight Adult Pulse (12 hours for simulation purposes, actual is 6 hours of unique content)
    print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] Initiating {MIDNIGHT_PULSE_TAG}")
    midnight_pulse_segments = list(content_plan_with_topics[MIDNIGHT_PULSE_TAG].keys())

    for _ in range(2): # Simulate 2 rotations of the 3 segments to fill 6 hours
        random.shuffle(midnight_pulse_segments) # Randomize order for variety
        for segment_type in midnight_pulse_segments:
            if available_scripts[segment_type]:
                script_path = random.choice(available_scripts[segment_type])
                duration = SEGMENT_DURATIONS.get(segment_type, timedelta(minutes=10))
                print(f"  Playing: {segment_type} - {os.path.basename(script_path)} (Duration: {duration})")
            else:
                duration = SEGMENT_DURATIONS.get(segment_type, timedelta(minutes=10))
                print(f"  Warning: No scripts available for {segment_type} in {MIDNIGHT_PULSE_TAG}. Simulating duration: {duration}")
            current_time += duration

    print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] Chloe TV Cycle Simulation Complete.")

if __name__ == "__main__":
    simulate_chloe_tv_cycle()
