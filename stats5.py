import time
import logging
import os
import sys
import clr
import ctypes
import re
from datetime import datetime
from library.lcd.lcd_comm import Orientation
from library.lcd.lcd_comm_rev_c import LcdCommRevC  # For 5″ monitor

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True
)

# ====== Display Settings ======
# In landscape mode, physical resolution is 800x480.
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 800
FONT_PATH = "res/fonts/jetbrains-mono/JetBrainsMono-Bold.ttf"
FONT_SIZE = 20
BG_COLOR = (0, 0, 0)          # Solid black background
CPU_COLOR = (255, 0, 0)       # Red for CPU (and RAM)
GPU_COLOR = (0, 128, 0)       # Dark green for GPU stats
TEXT_COLOR = (255, 255, 255)  # White text
UPDATE_INTERVAL = .5           # seconds
BACKGROUND_IMG = "background.png"

# Bar vertical offset (in pixels) to align bars with text.
BAR_OFFSET = 5

# ====== Setup LibreHardwareMonitor ======
clr.AddReference(os.path.join(os.getcwd(), 'external', 'LibreHardwareMonitor', 'LibreHardwareMonitorLib.dll'))
clr.AddReference(os.path.join(os.getcwd(), 'external', 'LibreHardwareMonitor', 'HidSharp.dll'))
from LibreHardwareMonitor import Hardware

handle = Hardware.Computer()
handle.IsCpuEnabled = True
handle.IsGpuEnabled = True
handle.IsMemoryEnabled = True
handle.IsMotherboardEnabled = True
handle.IsControllerEnabled = True
handle.IsNetworkEnabled = True
handle.IsStorageEnabled = True
handle.IsPsuEnabled = True
handle.Open()

# ====== Sensor Query Functions ======
def get_sensor_value(hw_list, hw_type, sensor_type, sensor_name, hw_name=None):
    for hw in hw_list:
        if hw.HardwareType == hw_type:
            if hw_name and (hw_name.lower() not in hw.Name.lower()):
                continue
            hw.Update()
            for sensor in hw.Sensors:
                if str(sensor.SensorType) == sensor_type and sensor.Name == sensor_name:
                    return sensor.Value
            for subhw in hw.SubHardware:
                subhw.Update()
                for sensor in subhw.Sensors:
                    if str(sensor.SensorType) == sensor_type and sensor.Name == sensor_name:
                        return sensor.Value
    return None

def get_hardware_name(hw_list, hw_type, skip_first=False):
    skipped = False
    for hw in hw_list:
        if hw.HardwareType == hw_type:
            if skip_first and not skipped:
                skipped = True
                continue
            return hw.Name
    return None

def truncate_first_word(name_str):
    parts = name_str.split()
    if len(parts) > 1:
        return " ".join(parts[1:])
    return name_str

# Store CPU name globally.
def initialize_hardware_names():
    global CPU_NAME
    hw_list = handle.Hardware
    cpu_full_name = get_hardware_name(hw_list, Hardware.HardwareType.Cpu) or "Unknown CPU"
    CPU_NAME = truncate_first_word(cpu_full_name)

# Get GPU stats for a given filter (e.g. "4090" or "1030")
def get_gpu_stats(hw_list, filter_str):
    stats = {}
    for hw in hw_list:
        if hw.HardwareType == Hardware.HardwareType.GpuNvidia and filter_str.lower() in hw.Name.lower():
            stats["name"] = hw.Name
            stats["util"] = get_sensor_value(hw_list, Hardware.HardwareType.GpuNvidia, "Load", "GPU Core", hw_name=filter_str) or 0.0
            stats["temp"] = get_sensor_value(hw_list, Hardware.HardwareType.GpuNvidia, "Temperature", "GPU Core", hw_name=filter_str) or 0.0
            stats["clock"] = get_sensor_value(hw_list, Hardware.HardwareType.GpuNvidia, "Clock", "GPU Core", hw_name=filter_str) or 0.0
            stats["mem_used"] = get_sensor_value(hw_list, Hardware.HardwareType.GpuNvidia, "SmallData", "GPU Memory Used", hw_name=filter_str) or 0.0
            stats["mem_total"] = get_sensor_value(hw_list, Hardware.HardwareType.GpuNvidia, "SmallData", "GPU Memory Total", hw_name=filter_str) or 1.0
            stats["mem_percent"] = (stats["mem_used"] / stats["mem_total"]) * 100
            return stats
    return None

# Draw a GPU section starting at (x,y) for a given GPU's stats.
def draw_gpu_section(lcd, x, y, stats):
    # Fix GPU progress bar's right edge at x=780.
    bar_width = 300
    bar_x = 780 - bar_width
    # Header: display GPU name.
    lcd.DisplayText(stats["name"], x=x, y=y, font=FONT_PATH, font_size=20,
                    font_color=GPU_COLOR, background_color=BG_COLOR)
    y += 20
    # Utilization text: pad to 3 characters.
    util_str = f"Util: {int(stats['util']):3d}%"
    lcd.DisplayText(util_str, x=x, y=y, font=FONT_PATH, font_size=16,
                    font_color=GPU_COLOR, background_color=BG_COLOR)
    y += 20
    # Utilization progress bar.
    lcd.DisplayProgressBar(x=bar_x, y=y + BAR_OFFSET, width=bar_width, height=20,
                           min_value=0, max_value=100, value=int(stats["util"]),
                           bar_color=GPU_COLOR, bar_outline=True, background_color=BG_COLOR)
    y += 30
    # Temperature and clock on one line.
    temp_freq_str = f"Temp: {int(stats['temp']):2d}°C   Freq: {int(stats['clock']):4d}MHz"
    lcd.DisplayText(temp_freq_str, x=x, y=y, font=FONT_PATH, font_size=16,
                    font_color=GPU_COLOR, background_color=BG_COLOR)
    y += 20
    # Memory usage text: pad to 5 digits.
    mem_str = f"Mem: {int(stats['mem_used']):5d}MB/{int(stats['mem_total']):5d}MB"
    lcd.DisplayText(mem_str, x=x, y=y, font=FONT_PATH, font_size=16,
                    font_color=GPU_COLOR, background_color=BG_COLOR)
    y += 20
    # Memory usage progress bar.
    lcd.DisplayProgressBar(x=bar_x, y=y + BAR_OFFSET, width=bar_width, height=20,
                           min_value=0, max_value=100, value=int(stats["mem_percent"]),
                           bar_color=GPU_COLOR, bar_outline=True, background_color=BG_COLOR)
    y += 30
    return y

def get_sorted_core_loads(hw_list):
    core_loads = []
    for hw in hw_list:
        if hw.HardwareType == Hardware.HardwareType.Cpu:
            hw.Update()
            for sensor in hw.Sensors:
                if str(sensor.SensorType) == "Load" and "Core" in sensor.Name:
                    m = re.search(r'#(\d+)', sensor.Name)
                    core_index = int(m.group(1)) if m else 99
                    core_loads.append((core_index, sensor.Name, sensor.Value))
            for subhw in hw.SubHardware:
                subhw.Update()
                for sensor in subhw.Sensors:
                    if str(sensor.SensorType) == "Load" and "Core" in sensor.Name:
                        m = re.search(r'#(\d+)', sensor.Name)
                        core_index = int(m.group(1)) if m else 99
                        core_loads.append((core_index, sensor.Name, sensor.Value))
    core_loads.sort(key=lambda x: x[0])
    return core_loads

def initialize_display():
    lcd = LcdCommRevC(
        com_port="AUTO",
        display_width=DISPLAY_WIDTH,
        display_height=DISPLAY_HEIGHT
    )
    lcd.Reset()
    lcd.InitializeComm()
    lcd.SetBrightness(50)
    lcd.SetOrientation(Orientation.LANDSCAPE)
    logging.debug("Displaying initial background...")
    lcd.DisplayBitmap(BACKGROUND_IMG)
    logging.debug("Initial background displayed.")
    return lcd

def draw_static_text(lcd):
    # Left side: CPU header and CPU name.
    lcd.DisplayText("CPU Stats", x=10, y=10, font=FONT_PATH, font_size=22,
                    font_color=TEXT_COLOR, background_color=BG_COLOR)
    lcd.DisplayText(CPU_NAME, x=10, y=40, font=FONT_PATH, font_size=20,
                    font_color=CPU_COLOR, background_color=BG_COLOR)
    # Right side: GPU Stats header.
    lcd.DisplayText("GPU Stats", x=420, y=10, font=FONT_PATH, font_size=22,
                    font_color=TEXT_COLOR, background_color=BG_COLOR)

def draw_dynamic_stats(lcd):
    hw_list = handle.Hardware

    # --- CPU Stats (Left Side) ---
    cpu_load = get_sensor_value(hw_list, Hardware.HardwareType.Cpu, "Load", "CPU Total") or 0.0
    cpu_temp = get_sensor_value(hw_list, Hardware.HardwareType.Cpu, "Temperature", "Core (Tctl/Tdie)")
    if cpu_temp is None:
        cpu_temp = get_sensor_value(hw_list, Hardware.HardwareType.Cpu, "Temperature", "Package") or 0.0
    cpu_freq = get_sensor_value(hw_list, Hardware.HardwareType.Cpu, "Clock", "Core #1") or 0.0

    y_cpu = 70
    # Total percentage: pad to 3 digits.
    lcd.DisplayText(f"Total: {int(cpu_load):3d}%", x=10, y=y_cpu, font=FONT_PATH, font_size=20,
                    font_color=CPU_COLOR, background_color=BG_COLOR)
    cpu_bar_width = 170
    cpu_bar_x = 320 - cpu_bar_width  # = 180.
    lcd.DisplayProgressBar(x=cpu_bar_x, y=y_cpu + BAR_OFFSET, width=cpu_bar_width, height=20,
                           min_value=0, max_value=100, value=int(cpu_load),
                           bar_color=CPU_COLOR, bar_outline=True, background_color=BG_COLOR)
    y_cpu += 30
    lcd.DisplayText(f"Temp: {int(cpu_temp):2d}°C   Freq: {int(cpu_freq):4d}MHz", x=10, y=y_cpu,
                    font=FONT_PATH, font_size=20, font_color=CPU_COLOR, background_color=BG_COLOR)
    y_cpu += 30
    core_loads = get_sorted_core_loads(hw_list)
    for core_index, sensor_name, load in core_loads:
        core_label = f"Core {core_index}:" if core_index != 99 else "Core (top):"
        lcd.DisplayText(core_label, x=10, y=y_cpu, font=FONT_PATH, font_size=18,
                        font_color=CPU_COLOR, background_color=BG_COLOR)
        lcd.DisplayProgressBar(x=cpu_bar_x, y=y_cpu + BAR_OFFSET, width=cpu_bar_width, height=15,
                               min_value=0, max_value=100, value=int(load),
                               bar_color=CPU_COLOR, bar_outline=True, background_color=BG_COLOR)
        lcd.DisplayText(f"{int(load):3d}%", x=330, y=y_cpu, font=FONT_PATH, font_size=18,
                        font_color=CPU_COLOR, background_color=BG_COLOR)
        y_cpu += 20

    # --- RAM Stats (Left Side, below CPU) ---
    mem_used = get_sensor_value(hw_list, Hardware.HardwareType.Memory, "Data", "Memory Used") or 0.0
    mem_avail = get_sensor_value(hw_list, Hardware.HardwareType.Memory, "Data", "Memory Available") or 0.0
    mem_total = mem_used + mem_avail
    mem_pct = (mem_used / mem_total) * 100 if mem_total > 0 else 0
    y_ram = y_cpu + 20
    lcd.DisplayText("RAM Stats", x=10, y=y_ram, font=FONT_PATH, font_size=22,
                    font_color=TEXT_COLOR, background_color=BG_COLOR)
    y_ram += 30
    # Convert values from GB to MB.
    mem_used_mb = int(round(mem_used * 1024))
    mem_total_mb = int(round(mem_total * 1024))
    # System RAM values: pad to 6 characters.
    lcd.DisplayText(f"{mem_used_mb:6d}MB / {mem_total_mb:6d}MB", x=10, y=y_ram, font=FONT_PATH, font_size=20,
                    font_color=CPU_COLOR, background_color=BG_COLOR)
    ram_bar_width = 140
    ram_bar_x = 420 - ram_bar_width  # = 280.
    lcd.DisplayProgressBar(x=ram_bar_x, y=y_ram + BAR_OFFSET, width=ram_bar_width, height=20,
                           min_value=0, max_value=100, value=int(mem_pct),
                           bar_color=CPU_COLOR, bar_outline=True, background_color=BG_COLOR)

    # --- GPU Stats (Right Side) ---
    gpu_x = 420  # left margin for GPU section.
    gpu_stats_4090 = get_gpu_stats(hw_list, "4090")
    if gpu_stats_4090 is not None:
        y_gpu1 = 40
        y_gpu1 = draw_gpu_section(lcd, gpu_x, y_gpu1, gpu_stats_4090)
    gpu_stats_1030 = get_gpu_stats(hw_list, "1030")
    if gpu_stats_1030 is not None:
        y_gpu2 = 180  # vertical gap.
        y_gpu2 = draw_gpu_section(lcd, gpu_x, y_gpu2, gpu_stats_1030)

    # --- Uptime and Clock (Centered at Bottom) ---
    now = datetime.now()
    clock_str = now.strftime("%a %m/%d/%Y %I:%M:%S %p")
    uptime_str = get_uptime_str()
    lcd.DisplayText(uptime_str, x=400, y=440, font=FONT_PATH, font_size=20,
                    font_color=TEXT_COLOR, background_color=BG_COLOR, anchor="mt")
    lcd.DisplayText(clock_str, x=400, y=460, font=FONT_PATH, font_size=20,
                    font_color=TEXT_COLOR, background_color=BG_COLOR, anchor="mt")

def get_uptime_str():
    uptime_ms = ctypes.windll.kernel32.GetTickCount64()
    uptime_sec = uptime_ms // 1000
    days = uptime_sec // 86400
    hours = (uptime_sec % 86400) // 3600
    minutes = (uptime_sec % 3600) // 60
    seconds = uptime_sec % 60
    return f"Uptime: {days}d {hours:02d}:{minutes:02d}:{seconds:02d}"

def main():
    initialize_hardware_names()
    lcd = initialize_display()
    draw_static_text(lcd)
    while True:
        draw_dynamic_stats(lcd)
        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    finally:
        handle.Close()