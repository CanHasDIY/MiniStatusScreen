import time
import logging
import os
import sys
import re
from datetime import datetime, timedelta
import psutil
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# ====== Display Settings ======
# In landscape mode, physical resolution is 800x480.
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 480
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
BG_COLOR = (0, 0, 0)          # Solid black background
CPU_COLOR = (255, 0, 0)       # Red for CPU (and RAM)
GPU_COLOR = (0, 128, 0)       # Dark green for GPU stats
TEXT_COLOR = (255, 255, 255)  # White text
UPDATE_INTERVAL = 0.5         # seconds
BACKGROUND_IMG = "background.png"
OUTPUT_DIR = "lcd_output"     # Directory to save frames if no LCD is connected

# Bar vertical offset (in pixels) to align bars with text.
BAR_OFFSET = 1

# ====== LCD Communication Class ======
class LcdDisplay:
    def __init__(self, display_width=320, display_height=480):
        self.width = display_width
        self.height = display_height
        self.image = Image.new('RGB', (self.width, self.height), BG_COLOR)
        self.draw = ImageDraw.Draw(self.image)
        self.fonts = {}
        self.frame_count = 0
        
        # Create output directory for frames if it doesn't exist
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
            
        # Try to detect available LCD drivers
        self.lcd_type = self._detect_lcd_type()
        if self.lcd_type:
            logging.info(f"Detected LCD type: {self.lcd_type}")
        else:
            logging.warning("No LCD hardware detected, will save frames to files")
        
    def _detect_lcd_type(self):
        """Try to detect available LCD hardware"""
        # Check for common Linux LCD drivers and interfaces
        try:
            # Check for FB devices (framebuffer)
            if os.path.exists('/dev/fb0') or os.path.exists('/dev/fb1'):
                return "framebuffer"
                
            # Check if this is running on a system with X11
            if 'DISPLAY' in os.environ:
                return "x11"
                
            # Check for specific hardware
            import subprocess
            i2c_out = subprocess.run(['i2cdetect', '-l'], capture_output=True, text=True)
            if "No such file or directory" not in i2c_out.stderr:
                return "i2c"
                
        except Exception as e:
            logging.warning(f"Error detecting LCD hardware: {e}")
            
        return None
        
    def _get_font(self, font_path, size):
        key = f"{font_path}_{size}"
        if key not in self.fonts:
            try:
                self.fonts[key] = ImageFont.truetype(font_path, size)
            except OSError:
                # Fallback to default font if specified one not found
                logging.warning(f"Font {font_path} not found, using default")
                self.fonts[key] = ImageFont.load_default()
        return self.fonts[key]
    
    def Reset(self):
        # Reset the display
        logging.debug("Resetting display")
        self.image = Image.new('RGB', (self.width, self.height), BG_COLOR)
        self.draw = ImageDraw.Draw(self.image)
        self.frame_count = 0
        # Hardware reset would go here if we had actual hardware
        
    def SetBrightness(self, level):
        # Set LCD brightness level (0-100)
        logging.debug(f"Setting brightness to {level}%")
        # Implementation depends on LCD hardware
        
    def DisplayBitmap(self, image_path):
        try:
            if os.path.exists(image_path):
                bg = Image.open(image_path).convert('RGB')
                bg = bg.resize((self.width, self.height))
                self.image = bg.copy()
                self.draw = ImageDraw.Draw(self.image)
                self._update_display()
                logging.debug(f"Displayed bitmap: {image_path}")
            else:
                logging.warning(f"Image file not found: {image_path}")
        except Exception as e:
            logging.error(f"Failed to display bitmap: {str(e)}")
            
    def DisplayText(self, text, x, y, font, font_size, font_color, background_color, anchor="lt"):
        try:
            font_obj = self._get_font(font, font_size)
            
            # Handle text anchoring
            if anchor == "mt":  # Middle top
                text_width = self.draw.textlength(text, font=font_obj)
                x = x - (text_width // 2)
                
            self.draw.text((x, y), text, font=font_obj, fill=font_color)
        except Exception as e:
            logging.error(f"Failed to display text: {str(e)}")
            
    def DisplayProgressBar(self, x, y, width, height, min_value, max_value, value, bar_color, bar_outline=True, background_color=BG_COLOR):
        try:
            # Draw background
            self.draw.rectangle([(x, y), (x + width, y + height)], fill=background_color)
            
            # Calculate bar width based on value
            range_value = max_value - min_value
            if range_value <= 0:
                bar_width = 0
            else:
                bar_width = int((value - min_value) / range_value * width)
                
            # Draw the filled portion
            if bar_width > 0:
                self.draw.rectangle([(x, y), (x + bar_width, y + height)], fill=bar_color)
                
            # Draw outline
            if bar_outline:
                self.draw.rectangle([(x, y), (x + width, y + height)], outline=TEXT_COLOR)
        except Exception as e:
            logging.error(f"Failed to display progress bar: {str(e)}")
            
    def _update_display(self):
        """Update the physical display or save image to file"""
        if self.lcd_type == "framebuffer":
            # Example for framebuffer devices
            try:
                fb_device = '/dev/fb0'  # or '/dev/fb1'
                with open(fb_device, 'wb') as fb:
                    fb.write(self.image.tobytes())
            except Exception as e:
                logging.error(f"Failed to write to framebuffer: {e}")
                
        elif self.lcd_type == "x11":
            # If running in X11 environment, display image in a window
            try:
                self.image.show()  # This will open a new window each time
            except:
                self._save_frame()
                
        else:
            # Save to file if no LCD hardware is available
            self._save_frame()
            
    def _save_frame(self):
        """Save current frame to file"""
        filename = os.path.join(OUTPUT_DIR, f"frame_{self.frame_count:04d}.png")
        self.image.save(filename)
        logging.debug(f"Saved frame to {filename}")
        self.frame_count += 1
        
    def InitializeComm(self):
        logging.debug("Initializing display communication")
        # Already handled in __init__
        pass

    def SetOrientation(self, orientation):
        logging.debug(f"Setting orientation: {orientation}")
        pass

# ====== Sensor Query Functions ======
def get_cpu_info():
    """Get CPU name and basic info"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('model name'):
                    return line.split(':')[1].strip()
        return "Unknown CPU"
    except Exception as e:
        logging.error(f"Failed to get CPU info: {str(e)}")
        return "CPU Info Error"

def get_cpu_stats():
    """Get CPU usage, temperature and frequency"""
    stats = {}
    
    # CPU load
    stats["util"] = psutil.cpu_percent(interval=0.1)
    
    # CPU frequency
    freq_info = psutil.cpu_freq()
    if freq_info:
        stats["clock"] = freq_info.current
    else:
        # Alternative method
        try:
            with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq', 'r') as f:
                stats["clock"] = float(f.read().strip()) / 1000  # Convert kHz to MHz
        except:
            stats["clock"] = 0.0
    
    # CPU temperature - method varies by system
    stats["temp"] = 0.0
    try:
        # Try generic Linux thermal zone first
        temps = []
        thermal_zones = os.listdir('/sys/class/thermal/')
        for zone in thermal_zones:
            if zone.startswith('thermal_zone'):
                try:
                    with open(f'/sys/class/thermal/{zone}/temp', 'r') as f:
                        temp = float(f.read().strip()) / 1000.0  # Convert from millidegrees
                        temps.append(temp)
                except:
                    pass
                    
        if temps:
            stats["temp"] = max(temps)  # Use the highest temperature
        
        # If that fails, try lm-sensors
        if stats["temp"] == 0.0:
            try:
                sensors_output = subprocess.check_output(['sensors'], text=True)
                # Look for lines like "Core 0: +45.0°C"
                temp_matches = re.findall(r'Core \d+:\s+\+(\d+\.\d+)°C', sensors_output)
                if temp_matches:
                    stats["temp"] = max(float(t) for t in temp_matches)
            except:
                pass
    except Exception as e:
        logging.error(f"Failed to get CPU temperature: {str(e)}")
    
    return stats

def get_core_loads():
    """Get per-core CPU loads"""
    core_loads = []
    per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
    for i, load in enumerate(per_cpu):
        core_loads.append((i, f"Core #{i}", load))
    return core_loads

def get_ram_stats():
    """Get RAM usage information"""
    stats = {}
    mem = psutil.virtual_memory()
    stats["total"] = mem.total / (1024 * 1024)  # Convert to MB
    stats["used"] = mem.used / (1024 * 1024)    # Convert to MB
    stats["percent"] = mem.percent
    return stats

def get_gpu_stats():
    """Get GPU information for NVIDIA or AMD GPUs"""
    stats = {"name": "No GPU detected", "util": 0.0, "temp": 0.0, "clock": 0.0, 
             "mem_used": 0.0, "mem_total": 1.0, "mem_percent": 0.0}
    
    # Try NVIDIA GPU (using nvidia-smi)
    try:
        output = subprocess.check_output(['nvidia-smi', '--query-gpu=name,utilization.gpu,temperature.gpu,clocks.current.graphics,memory.used,memory.total', '--format=csv,noheader,nounits']).decode('utf-8').strip()
        values = output.split(', ')
        if len(values) >= 6:
            stats["name"] = values[0]
            stats["util"] = float(values[1])
            stats["temp"] = float(values[2])
            stats["clock"] = float(values[3])
            stats["mem_used"] = float(values[4])
            stats["mem_total"] = float(values[5])
            stats["mem_percent"] = (stats["mem_used"] / stats["mem_total"]) * 100
            return stats
    except Exception as e:
        logging.debug(f"Failed to get NVIDIA GPU stats: {e}")
    
    # Try AMD GPU (using rocm-smi)
    try:
        # Get GPU name
        name_output = subprocess.check_output(['rocm-smi', '--showproductname']).decode('utf-8')
        name_match = re.search(r'GPU\[\d+\]:\s+(.*)', name_output)
        if name_match:
            stats["name"] = name_match.group(1).strip()
        
        # Get GPU utilization
        util_output = subprocess.check_output(['rocm-smi', '--showuse']).decode('utf-8')
        util_match = re.search(r'GPU\[\d+\]:\s+(\d+)%', util_output)
        if util_match:
            stats["util"] = float(util_match.group(1))
        
        # Get GPU temperature
        temp_output = subprocess.check_output(['rocm-smi', '--showtemp']).decode('utf-8')
        temp_match = re.search(r'GPU\[\d+\]:\s+(\d+\.?\d*)c', temp_output)
        if temp_match:
            stats["temp"] = float(temp_match.group(1))
        
        # Get GPU clock
        clock_output = subprocess.check_output(['rocm-smi', '--showclocks']).decode('utf-8')
        clock_match = re.search(r'GPU\[\d+\]:\s+(\d+)Mhz', clock_output)
        if clock_match:
            stats["clock"] = float(clock_match.group(1))
        
        # Get VRAM usage - this is more complex for AMD
        # For simplicity, we'll use placeholder values if not available
        stats["mem_percent"] = stats["util"]  # Approximate with GPU utilization
        
        return stats
    except Exception as e:
        logging.debug(f"Failed to get AMD GPU stats: {e}")
    
    # Try Intel GPU
    try:
        # Intel GPU info can be found in sysfs or using intel_gpu_top
        intels = [i for i in os.listdir('/sys/class/drm/') if i.startswith('card')]
        if intels:
            stats["name"] = "Intel GPU"
            # Most stats will be placeholder as Intel doesn't expose them easily without extra tools
            stats["util"] = 0.0
            stats["mem_percent"] = 0.0
            
            # Try to get GPU frequency if available
            try:
                with open('/sys/class/drm/card0/gt_cur_freq_mhz', 'r') as f:
                    stats["clock"] = float(f.read().strip())
            except:
                stats["clock"] = 0.0
                
            return stats
    except Exception as e:
        logging.debug(f"Failed to get Intel GPU stats: {e}")
    
    return stats

def get_uptime_str():
    """Get system uptime as a formatted string"""
    with open('/proc/uptime', 'r') as f:
        uptime_seconds = float(f.readline().split()[0])
    
    uptime_sec = int(uptime_seconds)
    days = uptime_sec // 86400
    hours = (uptime_sec % 86400) // 3600
    minutes = (uptime_sec % 3600) // 60
    seconds = uptime_sec % 60
    
    return f"Uptime: {days}d {hours:02d}:{minutes:02d}:{seconds:02d}"

# ====== Display Functions ======
def draw_gpu_section(lcd, x, y, stats):
    """Draw a GPU section starting at (x,y) for a given GPU's stats."""
    # Fix GPU progress bar's right edge at x=780.
    bar_width = 150
    bar_x = 360 - bar_width
    # Header: display GPU name.
    lcd.DisplayText(stats["name"], x=x, y=y, font=FONT_PATH, font_size=12,
                    font_color=GPU_COLOR, background_color=BG_COLOR)
    y += 20
    # Utilization text: pad to 3 characters.
    util_str = f"Util: {int(stats['util']):3d}%"
    lcd.DisplayText(util_str, x=x, y=y, font=FONT_PATH, font_size=10,
                    font_color=GPU_COLOR, background_color=BG_COLOR)
    y += 20
    # Utilization progress bar.
    lcd.DisplayProgressBar(x=bar_x, y=y + BAR_OFFSET, width=bar_width, height=20,
                           min_value=0, max_value=100, value=int(stats["util"]),
                           bar_color=GPU_COLOR, bar_outline=True, background_color=BG_COLOR)
    y += 20
    # Temperature and clock on one line.
    temp_freq_str = f"Temp: {int(stats['temp']):2d}°C   Freq: {int(stats['clock']):4d}MHz"
    lcd.DisplayText(temp_freq_str, x=x, y=y, font=FONT_PATH, font_size=10,
                    font_color=GPU_COLOR, background_color=BG_COLOR)
    y += 20
    # Memory usage text: pad to 5 digits.
    mem_str = f"Mem: {int(stats['mem_used']):5d}MB/{int(stats['mem_total']):5d}MB"
    lcd.DisplayText(mem_str, x=x, y=y, font=FONT_PATH, font_size=10,
                    font_color=GPU_COLOR, background_color=BG_COLOR)
    y += 20
    # Memory usage progress bar.
    lcd.DisplayProgressBar(x=bar_x, y=y + BAR_OFFSET, width=bar_width, height=20,
                           min_value=0, max_value=100, value=int(stats["mem_percent"]),
                           bar_color=GPU_COLOR, bar_outline=True, background_color=BG_COLOR)
    y += 10
    return y

def draw_static_text(lcd, cpu_name):
    """Draw static text elements on the display"""
    # Left side: CPU header and CPU name.
    lcd.DisplayText("CPU Stats", x=1, y=1, font=FONT_PATH, font_size=12,
                    font_color=TEXT_COLOR, background_color=BG_COLOR)
    lcd.DisplayText(cpu_name, x=1, y=15, font=FONT_PATH, font_size=10,
                    font_color=CPU_COLOR, background_color=BG_COLOR)
    # Right side: GPU Stats header.
    lcd.DisplayText("GPU Stats", x=220, y=1, font=FONT_PATH, font_size=12,
                    font_color=TEXT_COLOR, background_color=BG_COLOR)

def draw_dynamic_stats(lcd, cpu_name):
    """Draw dynamic system statistics on the display"""
    # --- CPU Stats (Left Side) ---
    cpu_stats = get_cpu_stats()
    cpu_load = cpu_stats["util"]
    cpu_temp = cpu_stats["temp"]
    cpu_freq = cpu_stats["clock"]

    y_cpu = 35
    # Total percentage: pad to 3 digits.
    lcd.DisplayText(f"Total: {int(cpu_load):3d}%", x=5, y=y_cpu, font=FONT_PATH, font_size=10,
                    font_color=CPU_COLOR, background_color=BG_COLOR)
    cpu_bar_width = 70
    cpu_bar_x = 120 - cpu_bar_width
    lcd.DisplayProgressBar(x=cpu_bar_x, y=y_cpu + BAR_OFFSET, width=cpu_bar_width, height=5,
                           min_value=0, max_value=100, value=int(cpu_load),
                           bar_color=CPU_COLOR, bar_outline=True, background_color=BG_COLOR)
    y_cpu += 15
    lcd.DisplayText(f"Temp: {int(cpu_temp):2d}°C   Freq: {int(cpu_freq):4d}MHz", x=5, y=y_cpu,
                    font=FONT_PATH, font_size=10, font_color=CPU_COLOR, background_color=BG_COLOR)
    y_cpu += 15
    
    # Individual CPU cores
    core_loads = get_core_loads()
    for core_index, sensor_name, load in core_loads:
        core_label = f"Core {core_index}:"
        lcd.DisplayText(core_label, x=10, y=y_cpu, font=FONT_PATH, font_size=8,
                        font_color=CPU_COLOR, background_color=BG_COLOR)
        lcd.DisplayProgressBar(x=cpu_bar_x, y=y_cpu + BAR_OFFSET, width=cpu_bar_width, height=5,
                               min_value=0, max_value=100, value=int(load),
                               bar_color=CPU_COLOR, bar_outline=True, background_color=BG_COLOR)
        lcd.DisplayText(f"{int(load):3d}%", x=120, y=y_cpu, font=FONT_PATH, font_size=10,
                        font_color=CPU_COLOR, background_color=BG_COLOR)
        y_cpu += 10

    # --- RAM Stats (Left Side, below CPU) ---
    ram_stats = get_ram_stats()
    y_ram = y_cpu + 10
    lcd.DisplayText("RAM Stats", x=10, y=y_ram, font=FONT_PATH, font_size=12,
                    font_color=TEXT_COLOR, background_color=BG_COLOR)
    y_ram += 15
    mem_used_mb = int(ram_stats["used"])
    mem_total_mb = int(ram_stats["total"])
    # System RAM values: pad to 6 characters.
    lcd.DisplayText(f"{mem_used_mb:6d}MB / {mem_total_mb:6d}MB", x=1, y=y_ram, font=FONT_PATH, font_size=10,
                    font_color=CPU_COLOR, background_color=BG_COLOR)
    ram_bar_width = 100
    lcd.DisplayProgressBar(x=10, y=y_ram + 15, width=ram_bar_width, height=8,
                           min_value=0, max_value=100, value=int(ram_stats["percent"]),
                           bar_color=CPU_COLOR, bar_outline=True, background_color=BG_COLOR)

    # --- GPU Stats (Right Side) ---
    gpu_x = 220  # left margin for GPU section.
    gpu_stats = get_gpu_stats()
    if gpu_stats["name"] != "No GPU detected":
        y_gpu = 20
        draw_gpu_section(lcd, gpu_x, y_gpu, gpu_stats)

    # --- Uptime and Clock (Centered at Bottom) ---
    now = datetime.now()
    clock_str = now.strftime("%a %m/%d/%Y %I:%M:%S %p")
    uptime_str = get_uptime_str()
    lcd.DisplayText(uptime_str, x=400, y=280, font=FONT_PATH, font_size=10,
                    font_color=TEXT_COLOR, background_color=BG_COLOR, anchor="mt")
    lcd.DisplayText(clock_str, x=400, y=300, font=FONT_PATH, font_size=10,
                    font_color=TEXT_COLOR, background_color=BG_COLOR, anchor="mt")
                    
    # Update the display after all elements are drawn
    lcd._update_display()

def main():
    # Get CPU name
    cpu_full_name = get_cpu_info()
    cpu_name = cpu_full_name.split(' ', 1)[1] if len(cpu_full_name.split(' ', 1)) > 1 else cpu_full_name
    
    # Initialize display
    lcd = LcdDisplay(display_width=DISPLAY_WIDTH, display_height=DISPLAY_HEIGHT)
    lcd.Reset()
    lcd.InitializeComm()
    lcd.SetBrightness(50)
    lcd.SetOrientation("LANDSCAPE")
    
    logging.debug("Displaying initial background...")
    try:
        lcd.DisplayBitmap(BACKGROUND_IMG)
    except:
        logging.warning(f"Could not load background image {BACKGROUND_IMG}, using blank background")
    
    # Draw static elements
    draw_static_text(lcd, cpu_name)
    
    # Main loop
    logging.info("Starting main monitoring loop")
    try:
        while True:
            draw_dynamic_stats(lcd, cpu_name)
            time.sleep(UPDATE_INTERVAL)
    except KeyboardInterrupt:
        logging.info("Monitoring stopped by user")
    except Exception as e:
        logging.error(f"Error in main loop: {str(e)}")
    finally:
        logging.info("Cleaning up")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        sys.exit(1)