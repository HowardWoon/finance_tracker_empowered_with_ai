import warnings
warnings.filterwarnings('ignore')

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import polars as pl
from poly_utils.utils import get_markets, update_missing_tokens

import subprocess

import pandas as pd


def _read_last_line(file_path):
    last_line = None
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as handle:
        for line in handle:
            if line.strip():
                last_line = line.strip()
    return last_line

def get_processed_df(df):
    markets_df = get_markets()
    markets_df = markets_df.rename({'id': 'market_id'})

    # 1) Make markets long: (market_id, side, asset_id) where side ∈ {"token1", "token2"}
    markets_long = (
        markets_df
        .select(["market_id", "token1", "token2"])
        .melt(id_vars="market_id", value_vars=["token1", "token2"],
            variable_name="side", value_name="asset_id")
    )

    # 2) Identify the non-USDC asset for each trade (the one that isn't 0)
    df = df.with_columns(
        pl.when(pl.col("makerAssetId") != "0")
        .then(pl.col("makerAssetId"))
        .otherwise(pl.col("takerAssetId"))
        .alias("nonusdc_asset_id")
    )

    # 3) Join once on that non-USDC asset to recover the market + side ("token1" or "token2")
    df = df.join(
        markets_long,
        left_on="nonusdc_asset_id",
        right_on="asset_id",
        how="left",
    )

    # 4) label columns and keep market_id
    df = df.with_columns([
        pl.when(pl.col("makerAssetId") == "0").then(pl.lit("USDC")).otherwise(pl.col("side")).alias("makerAsset"),
        pl.when(pl.col("takerAssetId") == "0").then(pl.lit("USDC")).otherwise(pl.col("side")).alias("takerAsset"),
        pl.col("market_id"),
    ])

    df = df[['timestamp', 'market_id', 'maker', 'makerAsset', 'makerAmountFilled', 'taker', 'takerAsset', 'takerAmountFilled', 'transactionHash']]

    df = df.with_columns([
        (pl.col("makerAmountFilled") / 10**6).alias("makerAmountFilled"),
        (pl.col("takerAmountFilled") / 10**6).alias("takerAmountFilled"),
    ])

    df = df.with_columns([
        pl.when(pl.col("takerAsset") == "USDC")
        .then(pl.lit("BUY"))
        .otherwise(pl.lit("SELL"))
        .alias("taker_direction"),

        # reverse of taker_direction
        pl.when(pl.col("takerAsset") == "USDC")
        .then(pl.lit("SELL"))
        .otherwise(pl.lit("BUY"))
        .alias("maker_direction"),
    ])

    df = df.with_columns([
        pl.when(pl.col("makerAsset") != "USDC")
        .then(pl.col("makerAsset"))
        .otherwise(pl.col("takerAsset"))
        .alias("nonusdc_side"),

        pl.when(pl.col("takerAsset") == "USDC")
        .then(pl.col("takerAmountFilled"))
        .otherwise(pl.col("makerAmountFilled"))
        .alias("usd_amount"),
        pl.when(pl.col("takerAsset") != "USDC")
        .then(pl.col("takerAmountFilled"))
        .otherwise(pl.col("makerAmountFilled"))
        .alias("token_amount"),
        pl.when(pl.col("takerAsset") == "USDC")
        .then(pl.col("takerAmountFilled") / pl.col("makerAmountFilled"))
        .otherwise(pl.col("makerAmountFilled") / pl.col("takerAmountFilled"))
        .cast(pl.Float64)
        .alias("price")
    ])


    df = df[['timestamp', 'market_id', 'maker', 'taker', 'nonusdc_side', 'maker_direction', 'taker_direction', 'price', 'usd_amount', 'token_amount', 'transactionHash']]
    return df



def process_live():
    processed_file = 'processed/trades.csv'
    source_file = 'goldsky/orderFilled.csv'

    print("=" * 60)
    print("Processing Live Trades")
    print("=" * 60)

    if not os.path.exists(source_file):
        print(f"[!] Missing source file: {source_file}")
        return

    if not (os.path.exists('markets.csv') or os.path.exists('missing_markets.csv')):
        print("[!] Missing market metadata files: markets.csv or missing_markets.csv")
        return

    last_processed = None

    if os.path.exists(processed_file):
        print(f"[OK] Found existing processed file: {processed_file}")
        last_line = _read_last_line(processed_file)
        if not last_line:
            print("[!] Processed file is empty; processing from beginning")
            last_processed = None
        else:
            splitted = last_line.split(',')

            last_processed = {
                'timestamp': pd.to_datetime(splitted[0]),
                'transactionHash': splitted[-1],
                'maker': splitted[2],
                'taker': splitted[3],
            }

            print(f"[DATA] Resuming from: {last_processed['timestamp']}")
            print(f"   Last hash: {last_processed['transactionHash'][:16]}...")
    else:
        print("[!] No existing processed file found - processing from beginning")

    print(f"\nReading: {source_file}")

    schema_overrides = {
        "takerAssetId": pl.Utf8,
        "makerAssetId": pl.Utf8,
    }

    df = pl.scan_csv(source_file, schema_overrides=schema_overrides).collect(streaming=True)
    df = df.with_columns(
        pl.from_epoch(pl.col('timestamp'), time_unit='s').alias('timestamp')
    )

    print(f"✓ Loaded {len(df):,} rows")

    df = df.with_row_index()

    if last_processed is None:
        df_process = df.drop('index')
    else:
        same_timestamp = df.filter(pl.col('timestamp') == last_processed['timestamp'])
        same_timestamp = same_timestamp.filter(
            (pl.col("transactionHash") == last_processed['transactionHash']) & (pl.col("maker") == last_processed['maker']) & (pl.col("taker") == last_processed['taker'])
        )

        if same_timestamp.is_empty():
            print("[!] Last processed row not found in source data; processing all rows")
            df_process = df.drop('index')
        else:
            df_process = df.filter(pl.col('index') > same_timestamp.row(0)[0]).drop('index')

    print(f"⚙️  Processing {len(df_process):,} new rows...")

    # Discover and fetch missing markets before processing
    # Extract unique non-USDC asset IDs from trade data
    import csv as csv_lib
    maker_ids = set()
    taker_ids = set()
    with open("goldsky/orderFilled.csv", newline="", encoding="utf-8") as f:
        reader = csv_lib.DictReader(f)
        for row in reader:
            if row.get("makerAssetId", "0") != "0":
                maker_ids.add(row["makerAssetId"])
            if row.get("takerAssetId", "0") != "0":
                taker_ids.add(row["takerAssetId"])
    trade_asset_ids = maker_ids | taker_ids

    # Load existing markets to find which trade assets are missing
    existing_ids = set()
    for fname in ("markets.csv", "missing_markets.csv"):
        if os.path.exists(fname):
            with open(fname, newline="", encoding="utf-8") as f:
                reader = csv_lib.DictReader(f)
                for row in reader:
                    if row.get("token1"):
                        existing_ids.add(row["token1"])
                    if row.get("token2"):
                        existing_ids.add(row["token2"])
    missing_ids = sorted(trade_asset_ids - existing_ids)

    if missing_ids:
        print(f"🔍 Found {len(missing_ids)} markets not in markets.csv — fetching from Polymarket API...")
        update_missing_tokens(missing_ids)
    else:
        print("✅ All markets already present — no missing markets to fetch")

    new_df = get_processed_df(df_process)
    
    if not os.path.isdir('processed'):
        os.makedirs('processed')


    op_file = 'processed/trades.csv'

    if not os.path.isfile(op_file):
        new_df.write_csv(op_file)
        print(f"[OK] Created new file: processed/trades.csv")
    else:
        print(f"[OK] Appending {len(new_df):,} rows to processed/trades.csv")
        with open(op_file, mode="a") as f:
            new_df.write_csv(f, include_header=False)

    
    print("=" * 60)
    print("Processing complete!")
    print("=" * 60)
    
if __name__ == "__main__":
    process_live()