## AdClick-based-Tracking

Crawler, data, and analysis for the paper *Clicked, Stored, Tracked: Consent Banners Fail to Control AdClick-based Tracking*.

We collect AdURLs of six ad platforms (Meta Ads, TikTok Ads, X Ads, Google Ads, Microsoft Advertising, Yahoo! JAPAN Ads) from six VPs (`AU, BR, DE, JP, US, ZA`), visit each landing page with no interaction, under reject all, and under accept all, and follow the AdClick-ID (`fbclid, ttclid, twclid, gclid, msclkid, yclid`) through storage, recipients, and linkage to user accounts.

# Setup Guide

## Step 1: Install Dependencies

Run the installation script:

```bash
./install.sh
```

---

## Step 2: Install Rust

The tracking classification (Step 7 of the program) uses [adblock-rust](https://github.com/brave/adblock-rust), the filtering engine of Brave. Install Rust and Cargo with rustup:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Follow the official guide for other systems: https://www.rust-lang.org/tools/install

---

## Step 3: Install PostgreSQL

PostgreSQL is required for this project, please install it before you continue with the next steps.

Follow the official guide:
https://www.postgresql.org/download/

After installation, make sure PostgreSQL is running and accessible on your system.

---

## Step 4: Create Databases

Run the database setup script:

```bash
python3 createDB.py
```

Then provide the required information:

* Postgres host (default: `localhost`)
* Port (default: `5432`)
* Username
* Password
* Database name prefix (`db_prefix`)

The script will:

* Create 18 databases, one for each VP and consent interaction (6 VPs × 3 interactions), named `db_prefix_country_case`:
  * `country`: `AU, BR, DE, JP, US, ZA`
  * `case`: `no-interaction`, `accept-all`, `reject-all`
  * e.g. `adclick_DE_reject-all`
* Create all required tables in each database

---

# Run the Program

Steps 1–6 run at one VP. Repeat them for each VP (`--country`): `AU, BR, DE, JP, US, ZA`. Yahoo! JAPAN Ads has no German VP.

## Step 1: Train Browser Profile

Run the training script:

```bash
python3 training.py --training-sites listTrain10.txt --output-name training_profile --country DE
```

### Notes:

* `listTrain10.txt`: contains training websites (e.g., first 10 domains from Tranco Top)
* `--country`: the VP of the profile, e.g. `US, DE, JP, AU, BR, ZA`
* The script will:

  * Open Chrome with the extension
  * Visit each site
  * Simulate scrolling behavior
  * Save a trained browser profile as a `.zip` file in the `profiles/` folder

---

## Step 2: Save Logged-in Profiles (Facebook, TikTok, X)

```bash
python3 save_AuthProfile.py --country DE
```

### Notes:

* `--country`: the VP of the profiles, e.g. `US, DE, JP, AU, BR, ZA`
* The script opens Facebook, TikTok, and X one after another.
* Log in manually on each page, then press `Enter` in the terminal.
* The script backs up the logged-in profiles and exits.

---

## Step 3: Collect AdURLs

```bash
python3 launch_crawlerAdClick.py \
  --autoRun 6 \
  --timeoutMins 10 \
  --pause 10 \
  --workers 2 \
  --ssAuto \
  --round 1 \
  --country DE
```

### Parameters

* `--autoRun`: number of runs in the round (e.g. `6`)
* `--timeoutMins`: duration of each run, in minutes (e.g. `10`)
* `--pause`: pause after each scroll, in seconds (e.g. `10`)
* `--workers`: number of independent browser windows per site (e.g. `2`)
* `--ssAuto`: automatically find the profiles backed up in Step 2
* `--round`: index of the collection round (e.g. `1`)
* `--country`: one of `US, DE, JP, AU, BR, ZA`

### Notes:

* The crawler visits 10 sites: the 5 ad platforms and 5 news websites.
* With `--workers 2`, it opens 10 × 2 = 20 independent browser windows.

---

## Step 4: Resolve Yahoo! JAPAN AdURLs

```bash
python3 yahooCheck.py
```

### Notes:

* Enter the round when the script asks for it, so that it reads the correct Yahoo! JAPAN AdURL file.
* The script follows the redirects of each AdURL and records the final landing page URL and its `yclid`.

---

## Step 5: Filter and Sample AdURLs

```bash
python3 FilterAdURLs_General.py --round 4 --sampleRandom 1
```

### Parameters

* `--round`: index of the collection round
* `--sampleRandom`: number of AdURLs randomly sampled per landing page domain

### Output:

* The list of AdURLs to visit in Step 6

---

## Step 6: Visit AdURLs

```bash
python3 launch_visitAdsAutoGeneral.py \
  --workers 20 \
  --autorun 3 \
  --auto-start 1 \
  --loadMode normal \
  --round 4 \
  --country JP
```

### Parameters

* `--workers`: number of independent browser workers (e.g. `20`)
* `--autorun`: number of runs for each consent interaction (e.g. `3`)
* `--auto-start`: first `run_no` (e.g. `1`)
* `--loadMode`: Selenium page load strategy: `normal`, `eager`, or `none`
* `--round`: index of the collection round (the AdURL list from Step 5)
* `--country`: one of `US, DE, JP, AU, BR, ZA`

### What This Step Does

For each AdURL, in each run:

1. Launches a browser instance (logged-in profile for Meta Ads, TikTok Ads, and X Ads)
2. Clears cookies, cache, and site storage before visiting
3. Visits the AdURL
4. Interacts with the cookie banner, in this order:
   * No interaction
   * Reject all
   * Accept all
5. Records, before and after the interaction:
   * Final redirected URL
   * Network requests and responses (URLs, headers, payloads)
   * Cookies, localStorage, and sessionStorage
6. Stores all data into PostgreSQL

### Important Notes

* Ensure the database is running before executing this step
* Each AdURL is processed independently

---

## Step 7: Classify Tracking Requests (EasyList / EasyPrivacy)

The `tracking/` folder contains a Rust program that matches every recorded request against EasyList and EasyPrivacy with adblock-rust and stores the result in the `easylist` and `privacylist` columns of `network_requests`.

```
tracking/
├── src/main.rs        # adblock-rust matcher
├── Cargo.toml         # Rust dependencies (adblock)
├── db.conf            # PostgreSQL connection (template)
├── easylist.txt       # EasyList
├── easyprivacy.txt    # EasyPrivacy
└── launch.py          # runs the matcher on the 18 databases
```

### 7.1 Download the filter lists

```bash
cd tracking
curl -o easylist.txt https://easylist.to/easylist/easylist.txt
curl -o easyprivacy.txt https://easylist.to/easylist/easyprivacy.txt
```

The paper uses the lists retrieved on 2026-09-30. Use the copies in this folder to reproduce the results.

### 7.2 Configure the database

Edit `db.conf` with the host, port, username, and password used in Setup Step 4. The line `dbname=` is a placeholder: `launch.py` replaces it for each database.

### 7.3 Build the matcher

```bash
cargo build --release
```

### 7.4 Run the classification

```bash
python3 launch.py
```

Enter the database name prefix (`db_prefix`) when the script asks for it. For each of the 18 databases, the script:

* Writes a configuration file `db_{country}_{case}.conf` from `db.conf`, with `dbname={db_prefix}_{country}_{case}`
* Starts `./target/release/tracking --config db_{country}_{case}.conf` in the background
* Writes the output to `tracking_{country}_{case}.log`

### Notes:

* The 18 processes run in parallel, and `launch.py` returns right after it starts them. Check the log files and wait until all processes have finished before the export (Step 8), e.g. with `pgrep -f target/release/tracking`.
* An empty prefix exits without running anything.
* A request is a tracking request if it matches at least one rule of EasyList (`easylist = True`) or EasyPrivacy (`privacylist = True`).
* Run this step after all visits (Step 6) and before the export (Step 8).

---

## Step 8: Export Data

```bash
python3 launch_ExportData.py --out ExportData --trackerdb trackerdb_domains.csv
```

### Parameters

* `--out`: output folder of the CSV files
* `--trackerdb`: Ghostery TrackerDB domain list (domain → organization)

### Output (`{country}_{interaction}_<name>.csv`):

* `sites_summary`: one row per visit (banner, AdURL, final URL, AdClick-ID state)
* `clickid_flags`: one row per visit with a valid AdClick-ID
* `clickid_occ_storage`: AdClick-ID in cookies, localStorage, and sessionStorage
* `clickid_occ_requests`: AdClick-ID in tracking requests and responses, per channel
* `auth_visit`: authentication cookie of the platform sent with the AdClick-ID (Meta Ads, TikTok Ads, X Ads)
* `clickid_params_upgrade`: AdClick-ID in request parameters after recursive decoding, with the SST-Guard label
* `sst_visit_upgrade`: server-side Google tag endpoints per visit

---

# Data Analysis

```bash
jupyter notebook AdClickID_Artifact.ipynb
```

Set `DATA_DIR` to the export folder of Step 8 and `TRACKERDB_CSV` to `trackerdb_domains.csv` in the first cell, then run all cells. The notebook reproduces the figures, tables, and numbers of the paper:

* `figures/`: Figures 2–9 (PDF)
* `tables/`: Tables 1–5 (CSV)
* Numbers in the text, printed per section of the paper

---

## Done

Full pipeline:

1. Setup environment (Python, Rust)
2. Setup databases
3. Train browser profile
4. Save logged-in profiles (Facebook, TikTok, X)
5. Collect AdURLs
6. Resolve Yahoo! JAPAN AdURLs
7. Filter and sample AdURLs
8. Visit AdURLs under no interaction, reject all, and accept all
9. Classify tracking requests with EasyList and EasyPrivacy (adblock-rust)
10. Export data
11. Analyze:

    * Consent compliance
    * Storage of the AdClick-ID
    * Recipients of the AdClick-ID
    * Linkage to user accounts

---

- **dataset.zip***: contains the exported CSV data used in the study.