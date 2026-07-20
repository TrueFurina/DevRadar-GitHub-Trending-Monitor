import os, sys
pythonw = sys.executable.replace("python.exe", "pythonw.exe")
print(f"python: {sys.executable}")
print(f"pythonw exists: {os.path.exists(pythonw)}")
