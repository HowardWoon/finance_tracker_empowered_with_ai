"""
Enhanced Find Edge with: type hints, logging, connection pooling, retry logic, caching, and parallelization.
"""

import logging
import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

from poly_utils.api_client import get_json, post_json, cache_stats

# ── LOGGING SETUP ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── CONFIG ──────────────────────────────────────────────────────────────
OLLAMA_MODEL: str = "llama3:latest"
MIN_VOLUME: float = 5000
MIN_LIQUIDITY: float = 1000
MAX_ANALYSE: int = 5
OLLAMA_TIMEOUT: int = 120
MARKET_FETCH_TIMEOUT: int = 10
NEWS_SEARCH_TIMEOUT: int = 8

# ────────────────────────────────────────────────────────────────────────

def fetch_markets() -> List[Dict[str, Any]]:
    """Fetch live Polymarket markets with type hints."""
    logger.info("📡 Fetching live Polymarket markets...")
    all_markets: List[Dict[str, Any]] = []
    offset: int = 0
    
    while len(all_markets) < 500:
        params: Dict[str, Any] = {
            "closed": "false",
            "active": "true",
            "limit": 100,
            "offset": offset,
            "order": "volume24hr",
            "ascending": "false"
        }
        
        try:
            data: List[Dict] = get_json(
                "https://gamma-api.polymarket.com/markets",
                params=params,
                timeout=MARKET_FETCH_TIMEOUT,
                use_cache=False  # Don't cache market data
            )
            
            if not data:
                break
            all_markets.extend(data)
            offset += 100
            
            if len(data) < 100:
                break
        except Exception as e:
            logger.error(f"Error fetching markets at offset {offset}: {e}")
            break
    
    logger.info(f"✅ Fetched {len(all_markets)} markets")
    return all_markets


def parse_field(raw: Any) -> List[Any]:
    """Parse field safely with type hints."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except:
            return []
    return []


def fetch_gold_silver() -> Dict[str, Any]:
    """Fetch real-time gold and silver prices with retry logic and caching."""
    logger.info("🥇 Fetching gold & silver prices...")
    
    result: Dict[str, Any] = {
        "gold_usd": None,
        "silver_usd": None,
        "gold_change_pct": None,
        "silver_change_pct": None,
        "gold_myr": None,
        "silver_myr": None,
        "usd_myr": None,
        "source": "unavailable"
    }

    # Get USD/MYR exchange rate (free)
    try:
        data: Dict = get_json(
            "https://open.er-api.com/v6/latest/USD",
            timeout=NEWS_SEARCH_TIMEOUT,
            cache_ttl=3600  # Cache for 1 hour
        )
        result["usd_myr"] = data.get("rates", {}).get("MYR")
        logger.debug(f"USD/MYR: {result['usd_myr']}")
    except Exception as e:
        logger.warning(f"Failed to fetch USD/MYR: {e}")

    # Get gold & silver from metals.live (free)
    try:
        data: List = get_json(
            "https://api.metals.live/v1/spot",
            timeout=NEWS_SEARCH_TIMEOUT,
            cache_ttl=600  # Cache for 10 minutes (prices update frequently)
        )
        
        for item in data:
            if item.get("gold"):
                result["gold_usd"] = float(item["gold"])
            if item.get("silver"):
                result["silver_usd"] = float(item["silver"])
        
        result["source"] = "metals.live"
        logger.debug(f"Metals: Gold=${result['gold_usd']}, Silver=${result['silver_usd']}")
    except Exception as e:
        logger.warning(f"Failed to fetch from metals.live: {e}")

    # Fallback: use frankfurter for metals
    if not result["gold_usd"]:
        try:
            data: Dict = get_json(
                "https://api.frankfurter.app/latest",
                params={"from": "XAU", "to": "USD"},
                timeout=NEWS_SEARCH_TIMEOUT,
                cache_ttl=600
            )
            xau_to_usd: Optional[float] = data.get("rates", {}).get("USD")
            if xau_to_usd:
                result["gold_usd"] = round(xau_to_usd, 2)
                result["source"] = "frankfurter"
        except Exception as e:
            logger.warning(f"Failed to fetch gold from frankfurter: {e}")

    if not result["silver_usd"]:
        try:
            data: Dict = get_json(
                "https://api.frankfurter.app/latest",
                params={"from": "XAG", "to": "USD"},
                timeout=NEWS_SEARCH_TIMEOUT,
                cache_ttl=600
            )
            xag_to_usd: Optional[float] = data.get("rates", {}).get("USD")
            if xag_to_usd:
                result["silver_usd"] = round(xag_to_usd, 2)
        except Exception as e:
            logger.warning(f"Failed to fetch silver from frankfurter: {e}")

    # Calculate MYR prices
    if result["gold_usd"] and result["usd_myr"]:
        result["gold_myr"] = round(result["gold_usd"] * result["usd_myr"], 2)
    if result["silver_usd"] and result["usd_myr"]:
        result["silver_myr"] = round(result["silver_usd"] * result["usd_myr"], 2)

    # Get yesterday's price for % change
    try:
        history: List = get_json(
            "https://api.metals.live/v1/spot/gold/history",
            timeout=NEWS_SEARCH_TIMEOUT,
            cache_ttl=3600
        )
        if len(history) >= 2 and result["gold_usd"]:
            prev: float = float(history[-2].get("price", 0))
            if prev > 0:
                result["gold_change_pct"] = round(
                    (result["gold_usd"] - prev) / prev * 100, 2
                )
    except Exception as e:
        logger.warning(f"Failed to fetch gold history: {e}")

    return result


def search_news(query: str) -> str:
    """Search news from multiple free sources with type hints."""
    snippets: List[str] = []
    logger.debug(f"Searching news for: {query[:50]}")

    # DuckDuckGo
    try:
        data: Dict = get_json(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1"},
            timeout=NEWS_SEARCH_TIMEOUT,
            cache_ttl=3600,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        
        if data.get("Abstract"):
            snippets.append(f"[DDG] {data['Abstract']}")
        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                snippets.append(f"[DDG] {topic['Text']}")
    except Exception as e:
        logger.debug(f"DuckDuckGo search failed: {e}")

    # Wikipedia
    try:
        search_term: str = query.split("?")[0].strip()[:60]
        data: Dict = get_json(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_term.replace(' ', '_')}",
            timeout=NEWS_SEARCH_TIMEOUT,
            cache_ttl=3600,
            headers={"User-Agent": "polymarket-edge-finder/1.0"}
        )
        if data.get("extract"):
            snippets.append(f"[Wiki] {data['extract'][:300]}")
    except Exception as e:
        logger.debug(f"Wikipedia search failed: {e}")

    # Reddit
    try:
        search_term: str = query.split("?")[0].strip()[:80]
        data: Dict = get_json(
            "https://www.reddit.com/search.json",
            params={"q": search_term, "sort": "new", "limit": "5", "t": "month"},
            timeout=NEWS_SEARCH_TIMEOUT,
            cache_ttl=3600,
            headers={"User-Agent": "polymarket-edge-finder/1.0"}
        )
        
        posts: List[Dict] = data.get("data", {}).get("children", [])
        for post in posts[:4]:
            p: Dict = post.get("data", {})
            title: str = p.get("title", "")
            score: int = p.get("score", 0)
            subreddit: str = p.get("subreddit", "")
            if title and score > 5:
                snippets.append(f"[Reddit r/{subreddit}] {title}")
    except Exception as e:
        logger.debug(f"Reddit search failed: {e}")

    if not snippets:
        return "No relevant news found."
    
    return " || ".join(snippets[:7])


def analyse_commodities_with_ollama(gold_data: Dict[str, Any]) -> str:
    """Analyse gold/silver with Ollama using type hints."""
    gold_usd: Any = gold_data.get("gold_usd", "unknown")
    silver_usd: Any = gold_data.get("silver_usd", "unknown")
    gold_myr: Any = gold_data.get("gold_myr", "unknown")
    silver_myr: Any = gold_data.get("silver_myr", "unknown")
    usd_myr: Any = gold_data.get("usd_myr", "unknown")
    gold_chg: Any = gold_data.get("gold_change_pct", "unknown")

    # Parallel news search
    with ThreadPoolExecutor(max_workers=2) as executor:
        gold_news_future = executor.submit(search_news, "gold price outlook 2026 Federal Reserve inflation")
        silver_news_future = executor.submit(search_news, "silver price outlook 2026 industrial demand")
        news: str = gold_news_future.result()
        silver_news: str = silver_news_future.result()

    prompt: str = f"""You are a commodity analyst specializing in precious metals.

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
        response: Dict = post_json(
            "http://localhost:11434/api/generate",
            {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 300,
                    "num_ctx": 2048
                }
            },
            timeout=OLLAMA_TIMEOUT
        )
        return response.get("response", "No response").strip()
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return f"Ollama error: {e}"


def analyse_with_ollama(question: str, yes_price: float, no_price: float, news_context: str) -> str:
    """Analyse market with Ollama."""
    prompt: str = f"""You are a prediction market analyst. Be concise and direct.

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
        response: Dict = post_json(
            "http://localhost:11434/api/generate",
            {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 200,
                    "num_ctx": 2048
                }
            },
            timeout=OLLAMA_TIMEOUT
        )
        return response.get("response", "No response").strip()
    except Exception as e:
        logger.error(f"Ollama analysis error: {e}")
        return f"Ollama error: {e}"


def filter_markets(all_markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter markets by volume, liquidity, and edge detection."""
    results: List[Dict[str, Any]] = []
    logger.debug(f"Filtering {len(all_markets)} markets...")
    
    for m in all_markets:
        try:
            volume24hr: float = float(m.get('volume24hr') or 0)
            liquidity: float = float(m.get('liquidityNum') or m.get('liquidity') or 0)

            if volume24hr < MIN_VOLUME or liquidity < MIN_LIQUIDITY:
                continue

            prices: List = parse_field(m.get('outcomePrices', []))
            outcomes: List = parse_field(m.get('outcomes', []))

            if len(prices) < 2 or len(outcomes) < 2:
                continue

            yes_idx: Optional[int] = None
            no_idx: Optional[int] = None
            
            for i, label in enumerate(outcomes):
                l: str = str(label).strip().lower()
                if l == 'yes':
                    yes_idx = i
                elif l == 'no':
                    no_idx = i

            if yes_idx is None or no_idx is None:
                continue

            yes_price: float = float(prices[yes_idx])
            no_price: float = float(prices[no_idx])

            if yes_price <= 0.001 or yes_price >= 0.999 or yes_price < 0.03:
                continue

            question: str = m.get('question', '')
            slug: str = m.get('slug', '')
            end_date: str = (m.get('endDate') or '')[:10]
            change24h: float = float(m.get('oneDayPriceChange') or 0)
            change1h: float = float(m.get('oneHourPriceChange') or 0)

            # Edge detection
            edge: str = 'low'
            if yes_price < 0.10 or yes_price > 0.90:
                edge = 'high'
            elif yes_price < 0.20 or yes_price > 0.80:
                edge = 'medium'
            elif abs(change1h) > 0.08 or abs(change24h) > 0.20:
                edge = 'medium'

            if edge == 'low':
                continue

            results.append({
                'question': question,
                'yes_price': yes_price,
                'no_price': no_price,
                'yes_pct': round(yes_price * 100, 1),
                'no_pct': round(no_price * 100, 1),
                'volume_24h': round(volume24hr),
                'liquidity': round(liquidity),
                'change_1h': round(change1h * 100, 1),
                'change_24h': round(change24h * 100, 1),
                'edge': edge,
                'ends': end_date,
                'link': f"https://polymarket.com/market/{slug}",
            })
        except Exception as e:
            logger.debug(f"Error filtering market: {e}")
            continue

    results.sort(key=lambda x: (0 if x['edge'] == 'high' else 1, -x['volume_24h']))
    logger.info(f"✅ Found {len(results)} edge candidates")
    return results


def analyse_market_batch(market: Dict[str, Any], ollama_ok: bool) -> Dict[str, Any]:
    """Analyse a single market (for parallel execution)."""
    logger.debug(f"Analysing: {market['question'][:50]}")
    
    try:
        news: str = search_news(market['question'])
        market['news'] = news
        
        if ollama_ok:
            ai_analysis: str = analyse_with_ollama(
                market['question'],
                market['yes_price'],
                market['no_price'],
                news
            )
            market['ai_analysis'] = ai_analysis
        else:
            market['ai_analysis'] = "Ollama not available"
        
        return market
    except Exception as e:
        logger.error(f"Error analysing market: {e}")
        market['news'] = "Error fetching news"
        market['ai_analysis'] = f"Error: {e}"
        return market


def test_ollama() -> bool:
    """Test Ollama connection."""
    logger.info("🔌 Testing Ollama...")
    try:
        response: Dict = post_json(
            "http://localhost:11434/api/generate",
            {
                "model": OLLAMA_MODEL,
                "prompt": "Reply with just the word OK",
                "stream": False,
                "options": {"num_predict": 5}
            },
            timeout=60
        )
        reply: str = response.get("response", "").strip()
        logger.info(f"✅ Ollama ready — model: {OLLAMA_MODEL} — replied: {reply}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Ollama connection failed: {e}")
        return False


# ── MAIN ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("  POLYMARKET AI EDGE FINDER + GOLD & SILVER ANALYSIS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # Test Ollama
    ollama_ok: bool = test_ollama()

    # ── GOLD & SILVER SECTION ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  GOLD & SILVER REAL-TIME ANALYSIS")
    print("=" * 70)

    gold_data: Dict[str, Any] = fetch_gold_silver()

    print(f"\n  [LIVE PRICES]:")
    if gold_data["gold_usd"]:
        chg: str = f" ({gold_data['gold_change_pct']:+.2f}%)" if gold_data["gold_change_pct"] else ""
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

    # Your TNG eMas context
    print(f"\n  [YOUR GOLD POSITION (TNG eMas)]:")
    print(f"     Holding: 0.426118g | Buy: RM603.06/g | Sell: RM589.92/g")
    if gold_data["gold_myr"]:
        # Using sell price as current market value
        your_cost_per_g: float = 603.06  # TNG eMas buy price
        your_sell_price: float = 589.92  # TNG eMas sell price
        holding_grams: float = 0.426118
        your_cost_total: float = holding_grams * your_cost_per_g
        your_value: float = holding_grams * your_sell_price
        your_pnl: float = your_value - your_cost_total
        print(f"     Cost basis:      RM{your_cost_total:.2f}")
        print(f"     Current value:   RM{your_value:.2f}")
        print(f"     P&L:             RM{your_pnl:+.2f} ({your_pnl/your_cost_total*100:+.1f}%)")

    if ollama_ok:
        print(f"\n  [AI COMMODITY ANALYSIS (Ollama)]...")
        commodity_analysis: str = analyse_commodities_with_ollama(gold_data)
        print(f"\n  {commodity_analysis.replace(chr(10), chr(10)+'  ')}")
    else:
        print("\n  [!] Ollama not available for commodity analysis")

    # ── POLYMARKET SECTION ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  POLYMARKET EDGE FINDER")
    print("=" * 70)

    all_markets: List[Dict] = fetch_markets()
    candidates: List[Dict] = filter_markets(all_markets)

    print(f"\n[*] Found {len(candidates)} edge candidates")
    print(f"[*] Deep analysing top {min(MAX_ANALYSE, len(candidates))} markets (with parallelization)...\n")

    # Parallel market analysis
    final_results: List[Dict[str, Any]] = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(analyse_market_batch, m, ollama_ok): i 
            for i, m in enumerate(candidates[:MAX_ANALYSE])
        }
        
        for i, future in enumerate(as_completed(futures)):
            try:
                result: Dict = future.result()
                final_results.append(result)
                print(f"✅ Completed analysis {i+1}/{min(MAX_ANALYSE, len(candidates))}")
            except Exception as e:
                logger.error(f"Error in parallel analysis: {e}")

    # ── PRINT POLYMARKET REPORT ───────────────────────────────────────────
    print("\n\n" + "=" * 70)
    print("  POLYMARKET FINAL REPORT")
    print("=" * 70)

    buy_yes_list: List[str] = []
    buy_no_list: List[str] = []

    for m in final_results:
        ai: str = m.get('ai_analysis', '')
        rec: str = "[SKIP]"

        if "BUY YES" in ai:
            rec = "[BUY YES]"
            buy_yes_list.append(m['question'][:60])
        elif "BUY NO" in ai:
            rec = "[BUY NO]"
            buy_no_list.append(m['question'][:60])

        conf: str = "[HIGH]" if "HIGH" in ai else "[MEDIUM]" if "MEDIUM" in ai else "LOW"

        print(f"\n{'-'*70}")
        print(f"{m['question']}")
        print(f"   YES: {m['yes_pct']}%  |  NO: {m['no_pct']}%  |  Ends: {m['ends']}")
        print(f"   Vol 24h: ${m['volume_24h']:,}  |  Liq: ${m['liquidity']:,}")
        print(f"   1h: {m['change_1h']}%  |  24h: {m['change_24h']}%")
        print(f"\n[NEWS]:")
        for chunk in [m.get('news', '')[:110] for _ in range(1)]:
            if chunk:
                print(f"   {chunk}")
        print(f"\n[AI VERDICT]:")
        for line in ai.split('\n')[:6]:
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

    # Save results
    df: pd.DataFrame = pd.DataFrame(final_results)
    df.to_csv('edge_report.csv', index=False)

    # Cache stats
    stats: Dict = cache_stats()
    logger.info(f"[STATS] Cache: {stats['entries']} entries, {stats['expired']} expired")

    print(f"\n{'='*70}")
    print(f"[OK] Saved to edge_report.csv")
    print(f"[CACHE] Entries: {stats['entries']}, Expired: {stats['expired']}")
    print(f"[!] Paper trade first. Never risk money you cannot lose.")
    print(f"{'='*70}")
