#!/usr/bin/env python3
import argparse
import math
import subprocess
import sys
import platform
import os
import glob
import shutil
import json
import time

system = platform.system()

PLATFORMS = ["FB","GG","MS","TT","TW","YH"]
TEMP_DIR_NAME = "Temp_run"

def cleanup_temp_dirs(script_dir):
    pattern = os.path.join(script_dir, "Temp_*")
    for path in glob.glob(pattern):
        if os.path.isdir(path):
            print(f"[INFO] Remove old temp dir: {path}")
            shutil.rmtree(path)


def create_worker_config(temp_dir,worker_id,common_config,platform_configs):
    config = {
        "worker_id": worker_id,

        # General parameters
        "country": common_config["country"],
        "autorun": common_config["autorun"],
        "auto_start": common_config["auto_start"],
        "loadMode": common_config["loadMode"],
        "headless": common_config["headless"],

        # Config for each platform
        "platforms": platform_configs
    }

    path = os.path.join(temp_dir,f"run_worker_{worker_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config,f,ensure_ascii=False,indent=4)

    return path

def parse_workers(expr, max_workers):
    if expr == "all":
        return set(range(1, max_workers + 1))

    result = set()
    for part in expr.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.update(range(int(a), int(b) + 1))
        else:
            result.add(int(part))
    return {w for w in result if 1 <= w <= max_workers}


def launch_worker(config_path, script_dir, worker_id, logs=None):
    crawler_py = os.path.join(script_dir,"visitAdsURLAutomate_General.py")

    base_cmd = ["python3","-u",crawler_py,"--config",config_path]

    if system == "Darwin":  # macOS
        cmd_str = " ".join(base_cmd)
        cmd_str = f"cd {script_dir} && {cmd_str}; read"
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{cmd_str}"'])
    else:  # Linux
        if logs is not None:
            log_file = os.path.join(script_dir, f"logs/{logs}.log")
        else:
            log_file = os.path.join(script_dir, f"logs/Click_{worker_id}.log")
        xvfb_cmd = ["xvfb-run", "-a"] + base_cmd
        with open(log_file, "w") as f:
            subprocess.Popen("cd " + script_dir + " && " + " ".join(xvfb_cmd), shell=True, stdout=f,stderr=f)


strategies = ["none", "eager", "normal"]

def main():
    parser = argparse.ArgumentParser(description="Launch parallel visitors for Ads URLs")
    parser.add_argument("--round")
    parser.add_argument("--sites")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--country", required=True)

    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--run-workers", default="all")
    parser.add_argument("--logs", default=None)
    parser.add_argument("--autorun", type=int, default=0)
    parser.add_argument("--auto-start", type=int, default=0, help="Run auto (default: 0)")
    parser.add_argument("--start", type=int, default=None, help="Start offset inside worker chunk (0-based)")
    parser.add_argument("--stop", type=int, default=None, help="Stop offset inside worker chunk (exclusive)")
    parser.add_argument("--loadMode", required=True, choices=strategies, help=f"Mode of load (one of: {', '.join(strategies)})")

    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    cleanup_temp_dirs(script_dir)

    temp_dir = os.path.join(script_dir, TEMP_DIR_NAME)
    os.makedirs(temp_dir, exist_ok=True)

    sites_by_platforms = {}
    for platform_name in PLATFORMS:
        if args.round is not None:
            path_sites = f"O_General_Filter_{args.round}/O_{platform_name}_Round{args.round}_selected_adsURL.csv"
           
        elif args.sites is not None:
            path_sites = args.sites
            
        else:
            print("Error: --round or --sites is required!")
            sys.exit(1)

        with open(path_sites, "r") as f:
            sites = [line.strip() for line in f if line.strip()]

        total_sites = len(sites)
        if total_sites == 0:
            print(f"Empty sites file: {path_sites}")
            sys.exit(1)

        if platform_name == "FB":
            siteRestore = "https://www.facebook.com"
            restoreSession = f"profiles/{args.country}/Facebook_{args.country}.json"
                
        elif platform_name == "TT":
            siteRestore = "https://www.tiktok.com/@tiktok"
            restoreSession = f"profiles/{args.country}/TikTok_{args.country}.json"
                
        elif platform_name == "TW":
            siteRestore = "https://www.x.com"
            restoreSession = f"profiles/{args.country}/Twitter_{args.country}.json"

        else:
            siteRestore = None
            restoreSession = None

        sites_by_platforms[platform_name] = {
            "path": path_sites,
            "total": total_sites,
            "siteRestore": siteRestore,
            "restoreSession": restoreSession
        }

        print(
            f"[INFO] {platform_name}: "
            f"{len(sites)} sites"
        )

    workers = args.workers
    run_workers = parse_workers(args.run_workers, workers)

    print(f"[INFO] Workers: {workers}")
    print(f"[INFO] Run workers: {sorted(run_workers)}")

    platform_chunks = {}
    for platform_name in PLATFORMS:
        total_sites = sites_by_platforms[platform_name]["total"]
        chunk_size = math.ceil(total_sites / workers)

        chunks = {}

        for i in range(workers):
            worker_id = i + 1
            if worker_id not in run_workers:
                continue

            chunk_begin = i * chunk_size
            chunk_end = min(chunk_begin + chunk_size, total_sites)
            
            inner_start = args.start if args.start is not None else 0
            inner_stop = args.stop if args.stop is not None else (chunk_end - chunk_begin)
            
            begin = chunk_begin + inner_start
            end = chunk_begin + inner_stop
            
            begin = max(chunk_begin, min(begin, chunk_end))
            end = max(begin, min(end, chunk_end))

            chunks[worker_id] = {"begin": begin,"end": end}
        platform_chunks[platform_name] = chunks
        print(
            f"[INFO] {platform_name}: "
            f"total={total_sites}, "
            f"chunk={chunk_size}"
        )
    
    for worker_id in sorted(run_workers):
        platform_configs = {}
        for platform_name in PLATFORMS:
            site_info = sites_by_platforms[platform_name]
            chunk = platform_chunks[platform_name][worker_id]
            platform_configs[platform_name] = {
                "sites": site_info["path"],
                "siteRestore": site_info["siteRestore"],
                "restoreSession": site_info["restoreSession"],
                "begin": chunk["begin"],
                "end": chunk["end"]
            }

        common_config = {
            "country": args.country,
            "autorun": args.autorun,
            "auto_start": args.auto_start,
            "loadMode": args.loadMode,
            "headless": args.headless,            
        }

        config_path = create_worker_config(temp_dir=temp_dir, worker_id=worker_id, common_config=common_config, platform_configs=platform_configs)

        print("")
        print(f"[INFO] Worker {worker_id}")
        for platform_name in PLATFORMS:
            cfg = platform_configs[platform_name]
            print(
                f"       {platform_name}: "
                f"{cfg['begin']}:{cfg['end']} "
                f"-> {cfg['sites']}"
            )
        print(
            f"       Config: {config_path}"
        )

        launch_worker(config_path, script_dir, worker_id, logs=args.logs)
        time.sleep(5)


if __name__ == "__main__":
    main()
