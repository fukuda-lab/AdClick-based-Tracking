#!/usr/bin/env python3
import subprocess
import platform
import os

system = platform.system()
import argparse

def launch_worker(base_cmd, script_dir, country, case):
    if system == "Darwin":  # macOS
        cmd_str = " ".join(base_cmd)
        cmd_str = f"cd {script_dir} && {cmd_str}; read"
        subprocess.Popen([
            "osascript", "-e",
            f'tell application "Terminal" to do script "{cmd_str}"'
        ])
    else:  # Linux
        log_file = os.path.join(script_dir, f"export_logs/Auth_{country}_{case}.log")
        xvfb_cmd = ["xvfb-run", "-a"] + base_cmd
        with open(log_file, "w") as f:
            subprocess.Popen(
                "cd " + script_dir + " && " + " ".join(xvfb_cmd),
                shell=True,
                stdout=f,
                stderr=f
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ExportData")
    ap.add_argument("--trackerdb", default="trackerdb_domains.csv")
    a = ap.parse_args()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_py = os.path.join(script_dir, "DP_ExportData.py")

    countries = ["JP", "US", "DE", "AU", "BR", "ZA"]
    cases = ["no-interaction","accept-all","reject-all"]

    for country in countries:
        for case in cases:
            base_cmd = [
                "python3", "-u", script_py,
                "--country", country,
                "--case", case,
                "--trackerdb", a.trackerdb,
                "--out", a.out,
            ]

            print(f"[INFO] Worker {country} - {case}")
            launch_worker(base_cmd, script_dir, country, case)


if __name__ == "__main__":
    main()
