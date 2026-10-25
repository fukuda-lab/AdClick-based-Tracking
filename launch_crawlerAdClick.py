#!/usr/bin/env python3
import argparse
import subprocess
import platform
import os
import time

system = platform.system()


def main():
    parser = argparse.ArgumentParser(description="Launch parallel crawlers")
    parser.add_argument("--workers", type=int, required=True, help="Number of workers")
    parser.add_argument("--country", required=True, help="Country code")

    parser.add_argument("--ssTikTok", help="Profile Tiktok")
    parser.add_argument("--ssTwitter", help="Profile Twitter")
    parser.add_argument("--ssFacebook", help="Profile Facebook")
    parser.add_argument("--ssAuto", action="store_true")
    parser.add_argument("--trainProfile", help="Profile without login")

    # passthrough params
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--autoRun", type=int, default=1, help="Run auto (default: 1)")
    parser.add_argument("--round", type=int, default=1, help="Num of round")
    parser.add_argument("--timeoutMins", type=int, default=5, help="Page visit (mins)")
    parser.add_argument("--pause", type=int, help="Pause time (s).")
    parser.add_argument("--timeout", type=int, default=30)

    args = parser.parse_args()
    workers = args.workers
    ssAuto = args.ssAuto

    ssTikTok = None
    ssFacebook = None
    ssTwitter = None
    profile = None

    if ssAuto:
        ssTikTok = f"{args.country}/TikTok_{args.country}.json"
        ssFacebook = f"{args.country}/Facebook_{args.country}.json"
        ssTwitter = f"{args.country}/Twitter_{args.country}.json"
        profile = f"T10_{args.country}"

    else:
        profile = args.trainProfile
        ssTikTok = args.ssTikTok
        ssFacebook = args.ssFacebook
        ssTwitter = args.ssTwitter

    if ssTikTok is None or ssFacebook is None or ssTwitter is None or profile is None:
        print("Error! Missing session profile")
        return
        

    sites_example  = [
        "https://nytimes.com",
        "https://cnn.com",
        "https://theguardian.com",
        "https://weather.com",
        "https://bbc.com"
    ]


    script_dir = os.path.dirname(os.path.abspath(__file__))

    crawler_TikTok = os.path.join(script_dir, "adURL_TikTok.py")
    crawler_Facebook = os.path.join(script_dir, "adURL_Facebook.py")
    crawler_Twitter = os.path.join(script_dir, "adURL_Twitter.py")
    crawler_WOLogin = os.path.join(script_dir, "adURL_General.py")

    base_cmd_Tiktok = ["python3", "-u", crawler_TikTok, "--country", args.country, "--profile-zip", profile, "--timeoutMins", str(args.timeoutMins), "--pause", str(args.pause), "--round", str(args.round), "--autoRun", str(args.autoRun), "--restoreSession", ssTikTok]
    base_cmd_FB = ["python3", "-u", crawler_Facebook, "--country", args.country, "--profile-zip", profile, "--timeoutMins", str(args.timeoutMins), "--pause", str(args.pause), "--round", str(args.round), "--autoRun", str(args.autoRun), "--restoreSession", ssFacebook]
    base_cmd_X = ["python3", "-u", crawler_Twitter, "--country", args.country, "--profile-zip", profile, "--timeoutMins", str(args.timeoutMins), "--pause", str(args.pause), "--round", str(args.round), "--autoRun", str(args.autoRun),  "--restoreSession", ssTwitter]
    base_cmd_Yahoo = ["python3", "-u", crawler_WOLogin, "--country", args.country, "--profile-zip", profile, "--timeoutMins", str(args.timeoutMins), "--pause", str(args.pause), "--round", str(args.round), "--autoRun", str(args.autoRun), "--yahoo"]
    base_cmd_Microsoft = ["python3", "-u", crawler_WOLogin, "--country", args.country, "--profile-zip", profile, "--timeoutMins", str(args.timeoutMins), "--pause", str(args.pause), "--round", str(args.round), "--autoRun", str(args.autoRun), "--microsoft"]
    
    cmds = [
        {"platform":"Facebook", "base_cmd":base_cmd_FB},
        {"platform":"Tiktok", "base_cmd":base_cmd_Tiktok},
        {"platform":"X", "base_cmd":base_cmd_X},
        {"platform":"Yahoo", "base_cmd":base_cmd_Yahoo},
        {"platform":"Microsoft", "base_cmd":base_cmd_Microsoft}
    ]
    

    base_cmd_General = ["python3", "-u", crawler_WOLogin, "--country", args.country, "--profile-zip", profile, "--timeoutMins", str(args.timeoutMins), "--pause", str(args.pause), "--round", str(args.round), "--autoRun", str(args.autoRun), "--timeout", str(args.timeout)]

    for site in sites_example:
        sname = site.replace("https://", "").replace("http://","").replace("/","_")
        platform_name = f"Google_{sname}"
        base_cmd = base_cmd_General.copy()
        base_cmd.extend(["--site", site])
        cmds.append({"platform": platform_name, "base_cmd": base_cmd})


    for cmd in cmds:
        platform = cmd["platform"]
        base_cmd = cmd["base_cmd"]

        if args.headless:
            base_cmd.append("--headless")

        for i in range(workers):
            # === PLATFORM HANDLING ===
            if system == "Darwin":  # macOS            
                cmd_str = " ".join(base_cmd)
                cmd_str = f"cd {script_dir} && {cmd_str}; read"
                subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{cmd_str}"'])
            else:  # Linux / Ubuntu Server → Xvfb
                print(f"Run crawler {platform} worker {i+1}")
                if args.mixed:
                    log_file = os.path.join(script_dir, f"crawler_logs/mixed_crawler_{platform}_worker_{i+1}.log")
                else:
                    log_file = os.path.join(script_dir, f"crawler_logs/crawler_{platform}_worker_{i+1}.log")
                xvfb_cmd = ["xvfb-run", "-a"] + base_cmd

                with open(log_file, "w") as f:
                    subprocess.Popen("cd " + script_dir + " && " + " ".join(xvfb_cmd), shell=True, stdout=f, stderr=f)

            time.sleep(2)

if __name__ == "__main__":
    main()
