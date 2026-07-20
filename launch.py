"""Launch DevRadar GUI - double-click this file!"""
import subprocess, sys, os, time

# Kill any old DevRadar process
try:
    subprocess.run(["taskkill", "/f", "/im", "python.exe"], 
                   capture_output=True, timeout=5)
    time.sleep(1)
except: pass

# Launch
script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.py")
pythonw = sys.executable.replace("python.exe", "pythonw.exe")
proc = subprocess.Popen(
    [pythonw, script],
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)
print(f"DevRadar started (PID: {proc.pid})")
print("Check your desktop for the DevRadar GUI window.")
