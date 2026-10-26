use adblock::engine::Engine;
use adblock::lists::{FilterSet, ParseOptions};
use adblock::request::Request;

use anyhow::Result;
use sqlx::{PgPool, Row, Postgres, QueryBuilder};

use std::collections::HashMap;
use std::fs;
use std::env;

#[derive(Debug)]
struct TrackingResult {
    request_id: i32,
    id_csv: i32,
    id_site: i32,
    easylist: bool,
    privacylist: bool,
    is_third_party: bool,
}

fn load_db_config(path: &str) -> anyhow::Result<HashMap<String, String>> {
    let content = fs::read_to_string(path)?;

    let mut config = HashMap::new();

    for line in content.lines() {
        let line = line.trim();

        if line.is_empty() || line.starts_with('#') {
            continue;
        }

        if let Some((k, v)) = line.split_once('=') {
            config.insert(
                k.trim().to_string(),
                v.trim().to_string(),
            );
        }
    }

    Ok(config)
}

fn load_engine(path: &str) -> Result<Engine> {
    let rules = fs::read_to_string(path)?;

    let mut filter_set = FilterSet::new(true);

    filter_set.add_filters(
        rules.lines(),
        ParseOptions::default(),
    );

    Ok(
        Engine::from_filter_set(
            filter_set,
            true,
        )
    )
}

async fn get_id_csv_list(
    pool: &PgPool,
) -> Result<Vec<i32>> {
    let rows = sqlx::query(
        r#"
        SELECT DISTINCT id_csv
        FROM sites
        WHERE crawl_status = 'success'
        ORDER BY id_csv
        "#,
    )
    .fetch_all(pool)
    .await?;

    Ok(
        rows.into_iter()
            .map(|r| r.get::<i32, _>("id_csv"))
            .collect(),
    )
}

async fn get_requests_backup(
    pool: &PgPool,
    id_csv: i32,
) -> Result<Vec<sqlx::postgres::PgRow>> {
    let rows = sqlx::query(
        r#"
        SELECT
            s.reached_url,
            s.id_csv,
            s.id_site,
            n.request_id,
            n.request_url,
            n.resource_type
        FROM sites s
        JOIN network_requests n
            ON s.id_site = n.id_site
        WHERE s.id_csv = $1
          AND s.crawl_status = 'success'
          AND n.easylist IS NULL
          AND n.privacylist IS NULL
        "#,
    )
    .bind(id_csv)
    .fetch_all(pool)
    .await?;

    Ok(rows)
}


async fn get_requests(
    pool: &PgPool,
    id_csv: i32,
) -> Result<Vec<sqlx::postgres::PgRow>> {
    let rows = sqlx::query(
        r#"
        SELECT
            s.reached_url,
            s.id_csv,
            s.id_site,
            n.request_id,
            n.request_url,
            n.resource_type
        FROM sites s
        JOIN network_requests n
            ON s.id_site = n.id_site
        WHERE s.id_csv = $1
          AND s.crawl_status = 'success'
          AND (n.easylist IS NULL OR n.privacylist IS NULL)
        "#,
    )
    .bind(id_csv)
    .fetch_all(pool)
    .await?;

    Ok(rows)
}

fn map_resource_type(resource_type: &str) -> &'static str {
    match resource_type.to_ascii_lowercase().as_str() {
        "script" => "script",
        "image" => "image",
        "stylesheet" => "stylesheet",
        "xhr" => "xmlhttprequest",
        "fetch" => "xmlhttprequest",
        "eventsource" => "xmlhttprequest",
        "document" => "document",
        "font" => "font",
        "media" => "media",
        "manifest" => "manifest",
        "ping" => "ping",
        "texttrack" => "other",
        "other" => "other",
        _ => "other",
    }
}

fn check_requests(
    rows: &[sqlx::postgres::PgRow],
    easylist: &Engine,
    easyprivacy: &Engine,
) -> Vec<TrackingResult> {
    let mut results = Vec::with_capacity(rows.len());

    for row in rows {
        let reached_url: String = row.get("reached_url");
        let request_url: String = row.get("request_url");

        let resource_type: Option<String> =
            row.try_get("resource_type").ok();

        let request_id: i32 = row.get("request_id");
        let id_csv: i32 = row.get("id_csv");
        let id_site: i32 = row.get("id_site");

        let adblock_resource_type =
            map_resource_type(
                resource_type
                    .as_deref()
                    .unwrap_or("other"),
            );

        let mut easylist_match = false;
        let mut easyprivacy_match = false;
        let mut is_third_party = false;

        use url::Url;

        let parsed = match Url::parse(&request_url) {
            Ok(u) => u,
            Err(err) => {
                eprintln!("[INVALID URL] request_id={} url={} error={}",request_id,request_url,err);
                continue;
            }
        };
        
        if parsed.scheme() != "http" && parsed.scheme() != "https"
        {
            continue;
        }


        match Request::new(
            &request_url,
            &reached_url,
            adblock_resource_type,
        ) {
            Ok(req) => {
                easylist_match = easylist.check_network_request(&req).matched;
                easyprivacy_match = easyprivacy.check_network_request(&req).matched;
                is_third_party = req.is_third_party;
            }

            Err(err) => {
                eprintln!(
                    "[REQUEST ERROR] request_id={}, id_csv={}, id_site={},resource_type={},request_url={},reached_url={}, error={:?}",
                    request_id, id_csv, id_site, adblock_resource_type, request_url, reached_url, err,
                );
            }
        }

        results.push(
            TrackingResult {
                request_id,
                id_csv,
                id_site,
                easylist: easylist_match,
                privacylist: easyprivacy_match,
                is_third_party: is_third_party,
            },
        );
    }

    results
}

async fn update_results(
    pool: &PgPool,
    results: &[TrackingResult],
) -> Result<()> {
    let mut tx = pool.begin().await?;

    let mut updated = 0u64;

    for r in results {
        let affected = sqlx::query(
            r#"
            UPDATE network_requests
            SET
                easylist = $1,
                privacylist = $2,
                is_third_party = $3
            WHERE
                request_id = $4
                AND id_csv = $5
                AND id_site = $6
            "#,
        )
        .bind(r.easylist)
        .bind(r.privacylist)
        .bind(r.is_third_party)
        .bind(r.request_id)
        .bind(r.id_csv)
        .bind(r.id_site)
        .execute(&mut *tx)
        .await?
        .rows_affected();

        if affected == 0 {
            eprintln!(
                "[UPDATE MISS] request_id={} id_site={}",
                r.request_id,
                r.id_site
            );
        }

        updated += affected;
    }

    tx.commit().await?;

    println!("Updated {} rows", updated);

    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<String> = env::args().collect();

    let config_file = if args.len() >= 3 && args[1] == "--config" {
        &args[2]
    } else {
        "db.conf"
    };

    println!("Using config: {}", config_file);

    let cfg = load_db_config(config_file)?;

    let host = cfg.get("host").unwrap();
    let port = cfg.get("port").unwrap();
    let user = cfg.get("user").unwrap();
    let password = cfg.get("password").unwrap();
    let dbname = cfg.get("dbname").unwrap();

    let database_url = format!(
        "postgres://{}:{}@{}:{}/{}",
        user,
        password,
        host,
        port,
        dbname
    );

    println!("Loading EasyList...");
    let easylist = load_engine("easylist.txt")?;

    println!("Loading EasyPrivacy...");
    let easyprivacy = load_engine("easyprivacy.txt")?;

    println!("Connecting PostgreSQL...");

    let pool = PgPool::connect(&database_url).await?;

    let id_csv_list = get_id_csv_list(&pool).await?;

    println!("Found {} id_csv", id_csv_list.len());

    for id_csv in id_csv_list {
        println!("\nProcessing id_csv={}", id_csv);

        let requests = get_requests(&pool, id_csv, ).await?;

        if requests.is_empty() {
            println!("No pending requests");
            continue;
        }

        println!("Checking {} requests", requests.len());

        let results = check_requests(&requests, &easylist, &easyprivacy, );

        println!("Checked {} requests", requests.len());
        
        update_results(&pool, &results, ).await?;
        println!(
            "Finished id_csv={} ({} requests)",
            id_csv,
            results.len()
        );
    }

    println!("Done.");

    Ok(())
}
