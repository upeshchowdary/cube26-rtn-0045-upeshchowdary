import subprocess
import os

def cleanup():
    # Use wmic or PowerShell to get process id and commandline
    cmd = 'powershell "Get-WmiObject Win32_Process -Filter \\"name=\'node.exe\'\\" | Select-Object ProcessId, CommandLine | Format-List"'
    out = subprocess.check_output(cmd, shell=True, text=True, errors="ignore")
    blocks = out.split("\n\n")
    for b in blocks:
        pid = None
        cline = ""
        for line in b.splitlines():
            line = line.strip()
            if line.startswith("ProcessId"):
                pid = line.split(":", 1)[-1].strip()
            elif line.startswith("CommandLine"):
                cline = line.split(":", 1)[-1].strip()
        if pid and cline:
            # Check if this node is vite or our test
            if any(k in cline.lower() for k in ["vite", "dev_server", "test_connected", "test_full_ui", "puppeteer"]):
                print(f"Terminating orphaned node PID {pid}: {cline[:80]}")
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)

if __name__ == "__main__":
    cleanup()
