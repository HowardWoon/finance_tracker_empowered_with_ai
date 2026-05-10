import requests
import pandas as pd
import json
import time
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────
OLLAMA_MODEL  = "llama3:latest"
MIN_VOLUME    = 5000
MIN_LIQUIDITY = 1000
MAX_ANALYSE   = 5
# ────────────────────────────────────────────────────────────────────────

def fetch_markets():
    print("[*] Fetching live Polymarket markets...")
    all_markets = []
    offset = 0
    while len(all_markets) < 500:
        url = (
            f"https://gamma-api.polymarket.com/markets"
            f"?closed=false&active=true&limit=100&offset={offset}"
            f"&order=volume24hr&ascending=false"
        )
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            if not data:
                break
            all_markets.extend(data)
            offset += 100
            if len(data) < 100:
                break
        except Exception as e:
            print(f"  Error: {e}")
            break
    print(f"  Fetched {len(all_markets)} markets")
    return all_markets

def parse_field(raw):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except:
            return []
    return []

def fetch_gold_silver():
    """Fetch real-time gold and silver prices — free, no API key."""
    print("\n[*] Fetching gold & silver prices...")
    result = {
        "gold_usd":        None,
        "silver_usd":      None,
        "gold_change_pct": None,
        "silver_change_pct": None,
        "gold_myr":        None,
        "silver_myr":      None,
        "usd_myr":         None,
        "source":          "unavailable"
    }

    # Get USD/MYR exchange rate (free)
    try:
        r = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            result["usd_myr"] = data.get("rates", {}).get("MYR")
    except:
        pass

    # Get gold & silver from metals-api alternative (free)
    try:
        r = requests.get(
            "https://api.metals.live/v1/spot",
            timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            for item in data:
                if item.get("gold"):
                    result["gold_usd"] = float(item["gold"])
                if item.get("silver"):
                    result["silver_usd"] = float(item["silver"])
            result["source"] = "metals.live"
    except:
        pass

    # Fallback: use frankfurter for metals via XAU/XAG
    if not result["gold_usd"]:
        try:
            r = requests.get(
                "https://api.frankfurter.app/latest?from=XAU&to=USD",
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                xau_to_usd = data.get("rates", {}).get("USD")
                if xau_to_usd:
                    result["gold_usd"] = round(xau_to_usd, 2)
                    result["source"] = "frankfurter"
        except:
            pass

    if not result["silver_usd"]:
        try:
            r = requests.get(
                "https://api.frankfurter.app/latest?from=XAG&to=USD",
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                xag_to_usd = data.get("rates", {}).get("USD")
                if xag_to_usd:
                    result["silver_usd"] = round(xag_to_usd, 2)
        except:
            pass

    # Calculate MYR prices
    if result["gold_usd"] and result["usd_myr"]:
        result["gold_myr"] = round(result["gold_usd"] * result["usd_myr"], 2)
    if result["silver_usd"] and result["usd_myr"]:
        result["silver_myr"] = round(result["silver_usd"] * result["usd_myr"], 2)

    # Get yesterday's price for % change
    try:
        r = requests.get(
            "https://api.metals.live/v1/spot/gold/history",
            timeout=8
        )
        if r.status_code == 200:
            history = r.json()
            if len(history) >= 2 and result["gold_usd"]:
                prev = float(history[-2].get("price", 0))
                if prev > 0:
                    result["gold_change_pct"] = round(
                        (result["gold_usd"] - prev) / prev * 100, 2
                    )
    except:
        pass

    return result

def analyse_commodities_with_ollama(gold_data):
    """Ask Ollama to analyse gold and silver outlook."""
    gold_usd    = gold_data.get("gold_usd", "unknown")
    silver_usd  = gold_data.get("silver_usd", "unknown")
    gold_myr    = gold_data.get("gold_myr", "unknown")
    silver_myr  = gold_data.get("silver_myr", "unknown")
    usd_myr     = gold_data.get("usd_myr", "unknown")
    gold_chg    = gold_data.get("gold_change_pct", "unknown")

    # Search for gold news
    news = search_news("gold price outlook 2026 Federal Reserve inflation")
    silver_news = search_news("silver price outlook 2026 industrial demand")

    prompt = f"""You are a commodity analyst specializing in precious metals.

CURRENT PRICES (real-time):
- Gold:   USD ${gold_usd}/oz  |  MYR RM{gold_myr}/oz  |  24h change: {gold_chg}%
- Silver: USD ${silver_usd}/oz  |  MYR RM{silver_myr}/oz
- USD/MYR rate: {usd_myr}

RECENT NEWS:
Gold: {str(news)[:400]}
Silver: {str(silver_news)[:400]}

As a Malaysian investor, analyse:
1. Is gold currently BULLISH, BEARISH, or NEUTRAL short-term (1-4 weeks)?
2. Is silver currently BULLISH, BEARISH, or NEUTRAL short-term?
3. Key factors driving the price right now
4. Should I BUY MORE gold, HOLD, or WAIT for dip?
5. Gold/Silver ratio analysis — which is better value right now?

Be specific and concise. Format:
GOLD TREND: BULLISH or BEARISH or NEUTRAL
SILVER TREND: BULLISH or BEARISH or NEUTRAL
GOLD ACTION: BUY MORE or HOLD or WAIT FOR DIP
SILVER ACTION: BUY or HOLD or WAIT
GOLD/SILVER RATIO: [number] — [which is better value]
KEY FACTORS: [2-3 bullet points]
OUTLOOK: [2 sentences]"""

    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 300,
                    "num_ctx": 2048
                }
            },
            timeout=120
        )
        if r.status_code == 200:
            return r.json().get("response", "No response").strip()
        else:
            return f"Ollama error: {r.status_code}"
    except Exception as e:
        return f"Ollama error: {e}"

def search_news(query):
    snippets = []

    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1"},
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = r.json()
        if data.get("Abstract"):
            snippets.append(f"[DDG] {data['Abstract']}")
        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                snippets.append(f"[DDG] {topic['Text']}")
    except:
        pass

    try:
        search_term = query.split("?")[0].strip()[:60]
        r = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/" +
            search_term.replace(" ", "_"),
            timeout=8,
            headers={"User-Agent": "polymarket-edge-finder/1.0"}
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("extract"):
                snippets.append(f"[Wiki] {data['extract'][:300]}")
    except:
        pass

    try:
        search_term = query.split("?")[0].strip()[:80]
        r = requests.get(
            "https://www.reddit.com/search.json",
            params={"q": search_term, "sort": "new", "limit": "5", "t": "month"},
            timeout=8,
            headers={"User-Agent": "polymarket-edge-finder/1.0"}
        )
        if r.status_code == 200:
            data = r.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts[:4]:
                p = post.get("data", {})
                title     = p.get("title", "")
                score     = p.get("score", 0)
                subreddit = p.get("subreddit", "")
                if title and score > 5:
                    snippets.append(f"[Reddit r/{subreddit}] {title}")
    except:
        pass

    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query[:100],
                "format": "json",
                "srlimit": "3"
            },
            timeout=8,
            headers={"User-Agent": "polymarket-edge-finder/1.0"}
        )
        if r.status_code == 200:
            data = r.json()
            results = data.get("query", {}).get("search", [])
            for result in results[:3]:
                title   = result.get("title", "")
                snippet = result.get("snippet", "").replace(
                    "<span class=\"searchmatch\">", ""
                ).replace("</span>", "")
                if title:
                    snippets.append(f"[Wiki Search] {title}: {snippet[:150]}")
    except:
        pass

    if not snippets:
        return "No relevant news found."
    return " || ".join(snippets[:7])

def analyse_with_ollama(question, yes_price, no_price, news_context):
    prompt = f"""You are a prediction market analyst. Be concise and direct.

MARKET QUESTION: {question}
CURRENT MARKET PRICE: YES={yes_price*100:.1f}%, NO={no_price*100:.1f}%

RELEVANT NEWS AND CONTEXT:
{news_context[:1000]}

Answer ONLY in this exact format:
SUPPORTS: YES or NO or UNCLEAR
CROWD PRICE: TOO HIGH or TOO LOW or FAIR
MY ESTIMATE: X%
RECOMMENDATION: BUY YES or BUY NO or SKIP
CONFIDENCE: HIGH or MEDIUM or LOW
REASON: one sentence"""

    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 200,
                    "num_ctx": 2048
                }
            },
            timeout=120
        )
        if r.status_code == 200:
            return r.json().get("response", "No response").strip()
        else:
            return f"Ollama HTTP error: {r.status_code}"
    except requests.exceptions.Timeout:
        return "Ollama timed out"
    except Exception as e:
        return f"Ollama error: {e}"

def filter_markets(all_markets):
    results = []
    for m in all_markets:
        try:
            volume24hr = float(m.get('volume24hr') or 0)
            liquidity  = float(m.get('liquidityNum') or m.get('liquidity') or 0)

            if volume24hr < MIN_VOLUME:
                continue
            if liquidity < MIN_LIQUIDITY:
                continue

            prices   = parse_field(m.get('outcomePrices', []))
            outcomes = parse_field(m.get('outcomes', []))

            if len(prices) < 2 or len(outcomes) < 2:
                continue

            yes_idx = no_idx = None
            for i, label in enumerate(outcomes):
                l = str(label).strip().lower()
                if l == 'yes':
                    yes_idx = i
                elif l == 'no':
                    no_idx = i

            if yes_idx is None or no_idx is None:
                continue

            yes_price = float(prices[yes_idx])
            no_price  = float(prices[no_idx])

            if yes_price <= 0.001 or yes_price >= 0.999:
                continue
            if yes_price < 0.03:
                continue

            question  = m.get('question', '')
            slug      = m.get('slug', '')
            end_date  = (m.get('endDate') or '')[:10]
            change24h = float(m.get('oneDayPriceChange') or 0)
            change1h  = float(m.get('oneHourPriceChange') or 0)

            if yes_price < 0.10 or yes_price > 0.90:
                edge = 'high'
            elif yes_price < 0.20 or yes_price > 0.80:
                edge = 'medium'
            elif abs(change1h) > 0.08 or abs(change24h) > 0.20:
                edge = 'medium'
            else:
                edge = 'low'

            if edge == 'low':
                continue

            results.append({
                'question'  : question,
                'yes_price' : yes_price,
                'no_price'  : no_price,
                'yes_pct'   : round(yes_price * 100, 1),
                'no_pct'    : round(no_price   * 100, 1),
                'volume_24h': round(volume24hr),
                'liquidity' : round(liquidity),
                'change_1h' : round(change1h * 100, 1),
                'change_24h': round(change24h * 100, 1),
                'edge'      : edge,
                'ends'      : end_date,
                'link'      : f"https://polymarket.com/market/{slug}",
            })
        except:
            continue

    results.sort(key=lambda x: (0 if x['edge'] == 'high' else 1, -x['volume_24h']))
    return results

# ── MAIN ────────────────────────────────────────────────────────────────
print("=" * 70)
print("  POLYMARKET AI EDGE FINDER + GOLD & SILVER ANALYSIS")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)

# Test Ollama
print("\n[*] Testing Ollama...")
OLLAMA_OK = False
try:
    test = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": "Reply with just the word OK",
            "stream": False,
            "options": {"num_predict": 5}
        },
        timeout=60
    )
    if test.status_code == 200:
        reply = test.json().get("response", "").strip()
        print(f"[OK] Ollama ready -- model: {OLLAMA_MODEL} -- replied: {reply}")
        OLLAMA_OK = True
    else:
        print(f"[!] Ollama status {test.status_code}")
except Exception as e:
    print(f"[!] Ollama connection failed: {e}")

# ── GOLD & SILVER SECTION ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("  GOLD & SILVER REAL-TIME ANALYSIS")
print("=" * 70)

gold_data = fetch_gold_silver()

print(f"\n  [LIVE PRICES]:")
if gold_data["gold_usd"]:
    chg = f" ({gold_data['gold_change_pct']:+.2f}%)" if gold_data["gold_change_pct"] else ""
    print(f"     Gold:   USD ${gold_data['gold_usd']:,.2f}/oz{chg}")
    if gold_data["gold_myr"]:
        print(f"             MYR RM{gold_data['gold_myr']:,.2f}/oz")
else:
    print("     Gold:   Price unavailable")

if gold_data["silver_usd"]:
    print(f"     Silver: USD ${gold_data['silver_usd']:,.2f}/oz")
    if gold_data["silver_myr"]:
        print(f"             MYR RM{gold_data['silver_myr']:,.2f}/oz")
else:
    print("     Silver: Price unavailable")

if gold_data["usd_myr"]:
    print(f"     USD/MYR: {gold_data['usd_myr']:.4f}")

# Gold/Silver ratio
if gold_data["gold_usd"] and gold_data["silver_usd"]:
    ratio = gold_data["gold_usd"] / gold_data["silver_usd"]
    print(f"     Gold/Silver Ratio: {ratio:.1f}x")
    if ratio > 85:
        print(f"     → Ratio is HIGH ({ratio:.1f}x) — Silver is historically cheap vs Gold")
    elif ratio < 65:
        print(f"     → Ratio is LOW ({ratio:.1f}x) — Gold is historically cheap vs Silver")
    else:
        print(f"     → Ratio is NORMAL ({ratio:.1f}x) — fair relative pricing")

# Your TNG eMas context
print(f"\n  [YOUR GOLD POSITION (TNG eMas)]:")
print(f"     Holding: 0.426118g | Buy: RM603.06/g | Sell: RM589.92/g")
if gold_data["gold_myr"]:
    # Using sell price as current market value
    your_cost_per_g   = 603.06  # TNG eMas buy price (cost basis)
    your_sell_price   = 589.92  # TNG eMas sell price (current market)
    holding_grams     = 0.426118
    your_cost_total   = holding_grams * your_cost_per_g  # Cost basis
    your_value        = holding_grams * your_sell_price  # Current value at sell price
    your_pnl          = your_value - your_cost_total
    print(f"     Cost basis:      RM{your_cost_total:.2f}")
    print(f"     Current value:   RM{your_value:.2f}")
    print(f"     P&L:             RM{your_pnl:+.2f} ({your_pnl/your_cost_total*100:+.1f}%)")

if OLLAMA_OK:
    print(f"\n  [AI COMMODITY ANALYSIS (Ollama)]...")
    commodity_analysis = analyse_commodities_with_ollama(gold_data)
    print(f"\n  {commodity_analysis.replace(chr(10), chr(10)+'  ')}")
else:
    print("\n  [!] Ollama not available for commodity analysis")

# ── POLYMARKET SECTION ────────────────────────────────────────────────
print("\n" + "=" * 70)
print("  POLYMARKET EDGE FINDER")
print("=" * 70)

all_markets = fetch_markets()
candidates  = filter_markets(all_markets)

print(f"\n[*] Found {len(candidates)} edge candidates")
print(f"[*] Deep analysing top {min(MAX_ANALYSE, len(candidates))} markets...\n")

final_results = []

for i, m in enumerate(candidates[:MAX_ANALYSE]):
    print(f"\n[{i+1}/{min(MAX_ANALYSE, len(candidates))}] {m['question'][:65]}")
    print(f"  [*] Searching news...")
    news = search_news(m['question'])
    print(f"  >> {news[:120]}...")
    time.sleep(1)

    ai_analysis = "Ollama not available"
    if OLLAMA_OK:
        print(f"  [*] Asking Ollama...")
        ai_analysis = analyse_with_ollama(
            m['question'], m['yes_price'], m['no_price'], news
        )
        print(f"  >> {ai_analysis[:100]}...")

    m['news']        = news
    m['ai_analysis'] = ai_analysis
    final_results.append(m)

# ── PRINT POLYMARKET REPORT ───────────────────────────────────────────
print("\n\n" + "=" * 70)
print("  POLYMARKET FINAL REPORT")
print("=" * 70)

buy_yes_list = []
buy_no_list  = []
skip_list    = []

for m in final_results:
    ai   = m['ai_analysis']
    rec  = "[SKIP]"
    conf = "LOW"

    if "BUY YES" in ai:
        rec = "[BUY YES]"
        buy_yes_list.append(m['question'][:60])
    elif "BUY NO" in ai:
        rec = "[BUY NO]"
        buy_no_list.append(m['question'][:60])
    else:
        skip_list.append(m['question'][:60])

    if "HIGH" in ai:
        conf = "[HIGH]"
    elif "MEDIUM" in ai:
        conf = "[MEDIUM]"

    print(f"\n{'-'*70}")
    print(f"{m['question']}")
    print(f"   YES: {m['yes_pct']}%  |  NO: {m['no_pct']}%  |  Ends: {m['ends']}")
    print(f"   Vol 24h: ${m['volume_24h']:,}  |  Liq: ${m['liquidity']:,}")
    print(f"   1h: {m['change_1h']}%  |  24h: {m['change_24h']}%")
    print(f"\n[NEWS]:")
    for chunk in [m['news'][i:i+110] for i in range(0, min(400, len(m['news'])), 110)]:
        print(f"   {chunk}")
    print(f"\n[AI VERDICT]:")
    for line in ai.split('\n'):
        if line.strip():
            print(f"   {line.strip()}")
    print(f"\n[TRADE]: {rec}  |  CONFIDENCE: {conf}")
    print(f"   Link: {m['link']}")

print(f"\n{'='*70}")
print(f"  [SUMMARY]")
print(f"{'='*70}")
if buy_yes_list:
    print(f"\n[BUY YES] ({len(buy_yes_list)}):")
    for q in buy_yes_list:
        print(f"   • {q}")
if buy_no_list:
    print(f"\n[BUY NO] ({len(buy_no_list)}):")
    for q in buy_no_list:
        print(f"   • {q}")
if skip_list:
    print(f"\n[SKIP] ({len(skip_list)}):")
    for q in skip_list:
        print(f"   • {q}")

df = pd.DataFrame(final_results)
df.to_csv('edge_report.csv', index=False)

print(f"\n{'='*70}")
print(f"[OK] Saved to edge_report.csv")
print(f"[!] Paper trade first. Never risk money you cannot lose.")
print(f"{'='*70}")