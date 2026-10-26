#!/usr/bin/env python3
import subprocess
import sys
countries = ["JP", "US", "DE", "AU", "BR", "ZA"]
cases = ["no-interaction","accept-all","reject-all"]

prefixDB = input("Prefix DB: ")

if prefixDB == "":
    sys.exit(0)

def create_db_config(template, country, case):
    output = f"db_{country}_{case}.conf"
    with open(template, "r") as f:
        lines = f.readlines()

    new_lines = []

    for line in lines:
        if line.startswith("dbname="):
            line = f"dbname={prefixDB}_{country}_{case}\n"

        new_lines.append(line)

    with open(output, "w") as f:
        f.writelines(new_lines)

    return output

def run(country, case, config_file):
    logFile = f"tracking_{country}_{case}.log"
    print("Run. Log file: {}".format(logFile))
    base_cmd = f"./target/release/tracking --config {config_file}"
    with open(logFile, "w") as f:
        subprocess.Popen(
            base_cmd,
            shell=True,
            stdout=f,
            stderr=f
        )
    

if __name__ == "__main__":
    for country in countries:
        for case in cases:
            config_file = create_db_config("db.conf", country, case)
            run(country, case, config_file)

