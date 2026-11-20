"""Runtime tools for the initial Voice-derived built-in plugin set."""

from __future__ import annotations

import json
from xml.etree import ElementTree
import httpx

from app.vault_runtime.builtin_plugins import BuiltinPluginRepository
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.voice.credentials import VoiceProviderCredentialStore
from app.vault_runtime.web_search import run_web_search

NEWS_FEEDS = {"top":"https://feeds.npr.org/1001/rss.xml","world":"https://feeds.bbci.co.uk/news/world/rss.xml","business":"https://feeds.npr.org/1006/rss.xml","technology":"https://feeds.feedburner.com/TechCrunch/","science":"https://www.sciencedaily.com/rss/top/science.xml","health":"https://www.sciencedaily.com/rss/top/health.xml","sports":"https://www.espn.com/espn/rss/news","entertainment":"https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"}


def register_builtin_plugin_tools(*, catalog: ToolCatalog, repository: BuiltinPluginRepository, credentials: VoiceProviderCredentialStore) -> None:
    def add(plugin: str, name: str, description: str, properties: dict[str, object], handler):
        def execute(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
            if not repository.enabled(account_id=context.user_id, workspace_id=context.workspace_id, plugin_key=plugin):
                return ToolInvocationResult(f"{plugin.replace('_', ' ').title()} is turned off.", is_error=True)
            try:
                payload = handler(context, arguments, repository.get(account_id=context.user_id, workspace_id=context.workspace_id, plugin_key=plugin)["configuration"])
                return ToolInvocationResult(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), payload)
            except Exception:
                return ToolInvocationResult(f"{plugin.replace('_', ' ').title()} is temporarily unavailable.", is_error=True)
        catalog.register(ToolDefinition(tool_id=f"builtin.{name.replace('_','-')}.v1", name=name, description=description, input_schema={"type":"object","properties":properties,"additionalProperties":False}, handler=execute, effect_class="read", audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}), availability=lambda user_id, workspace_id, key=plugin: repository.enabled(account_id=user_id, workspace_id=workspace_id, plugin_key=key)))

    add("weather", "weather_read", "Get current weather. Call with no location to use the saved primary location; do not ask the user first. Supply location only when the user explicitly names another place.", {"location":{"type":"string"}}, _weather)
    add("news", "news_read", "Get current category headlines such as technology, business, world, or sports. This is not geographic local news; use web_search with the saved location for local news.", {"topic":{"type":"string"}}, _news)
    add("markets", "markets_overview", "Use for every general market overview request. Includes current market conditions and the saved stock watchlist; prefer this over web_search.", {"query":{"type":"string"}}, lambda c,a,s: _search(credentials,c,_market_query(a,s)))
    add("markets", "markets_search_symbol", "Find the ticker symbol for a public company.", {"query":{"type":"string"}}, lambda c,a,s: _search(credentials,c,f"Find the stock ticker for {a.get('query','')}. Return the exchange and company name with current sources."))
    add("markets", "markets_quote", "Get the latest available quote for a ticker symbol.", {"symbol":{"type":"string"}}, lambda c,a,s: _search(credentials,c,f"Latest stock quote and today's change for {a.get('symbol','')}. Use current financial sources and state market timing."))
    add("markets", "markets_news", "Use for every market-news or company-news request. Uses a requested symbol or the saved watchlist; prefer this over web_search.", {"symbol":{"type":"string"},"query":{"type":"string"}}, lambda c,a,s: _search(credentials,c,f"Latest material market news for {a.get('symbol') or a.get('query') or ', '.join(s.get('watchlist',[]))}. Cite current sources."))
    add("local_events", "local_events_search", "Find current events near the user's saved home area. Call without location to use saved setup; prefer this over web_search.", {"query":{"type":"string"},"location":{"type":"string"}}, lambda c,a,s: _search(credentials,c,_events_query(a,s)))
    def local_update(context, _arguments, settings, changes):
        updated = repository.update(account_id=context.user_id, workspace_id=context.workspace_id, plugin_key="local_events", configuration={**settings, **changes})
        return {"status":"completed", "configuration":updated["configuration"]}
    add("local_events", "local_events_setup", "Save the user's home area and event preferences.", {"homeLocation":{"type":"string"},"radiusMiles":{"type":"integer","minimum":1,"maximum":100},"interests":{"type":"array","items":{"type":"string"}}}, lambda c,a,s: local_update(c,a,s,{"homeLocation":a.get("homeLocation",s.get("homeLocation","")),"radiusMiles":a.get("radiusMiles",s.get("radiusMiles",25)),"interests":a.get("interests",s.get("interests",[]))}))
    add("local_events", "local_events_save_event", "Save an event the user wants to remember.", {"title":{"type":"string"},"eventUrl":{"type":"string"},"startsAt":{"type":"string"},"venue":{"type":"string"}}, lambda c,a,s: local_update(c,a,s,{"savedEvents":[*s.get("savedEvents",[]),dict(a)][-50:]}))
    add("local_events", "local_events_add_source", "Add a trusted local event source.", {"name":{"type":"string"},"url":{"type":"string"}}, lambda c,a,s: local_update(c,a,s,{"sources":[*s.get("sources",[]),dict(a)][-25:]}))
    add("local_events", "local_events_remove_source", "Remove a saved local event source.", {"url":{"type":"string"}}, lambda c,a,s: local_update(c,a,s,{"sources":[item for item in s.get("sources",[]) if item.get("url") != a.get("url")]}))
    add("local_events", "local_events_review_sources", "Review saved local event sources.", {}, lambda _c,_a,s:{"status":"completed","items":s.get("sources",[])})
    add("local_events", "local_events_feedback", "Remember whether an event suggestion was useful.", {"event":{"type":"string"},"feedback":{"type":"string"}}, lambda c,a,s: local_update(c,a,s,{"feedback":[*s.get("feedback",[]),dict(a)][-100:]}))
    def add_to_calendar(context, arguments, _settings):
        calendar_arguments = {key: arguments[key] for key in ("linkedAccountId","title","startsAt","endsAt","description","location") if key in arguments}
        result = catalog.invoke("calendar_create", calendar_arguments, context=context)
        if result.is_error: raise ValueError(result.text)
        return result.structured_content or {"status":"unavailable"}
    add("local_events", "local_events_add_to_calendar", "Prepare a saved event for the user's calendar. Calendar confirmation is still required.", {"linkedAccountId":{"type":"string"},"title":{"type":"string"},"startsAt":{"type":"string"},"endsAt":{"type":"string"},"description":{"type":"string"},"location":{"type":"string"}}, add_to_calendar)


def _weather(_context, arguments, settings):
    location = str(arguments.get("location") or settings.get("primaryLocation") or "").strip()
    if not location: return {"status":"needs_setup","message":"Add a primary location in Weather settings."}
    geo = httpx.get("https://geocoding-api.open-meteo.com/v1/search", params={"name":location,"count":1,"language":"en","format":"json"}, timeout=20).json().get("results", [])
    if not geo: raise ValueError("location not found")
    place = geo[0]
    data = httpx.get("https://api.open-meteo.com/v1/forecast", params={"latitude":place["latitude"],"longitude":place["longitude"],"current":"temperature_2m,apparent_temperature,weather_code,wind_speed_10m","daily":"temperature_2m_max,temperature_2m_min","temperature_unit":"fahrenheit","wind_speed_unit":"mph","timezone":"auto","forecast_days":1}, timeout=20).json()
    current, daily = data.get("current",{}), data.get("daily",{})
    resolved = ", ".join(str(place.get(key)) for key in ("name","admin1","country") if place.get(key))
    return {"status":"completed","provider":"Open-Meteo","location":resolved,"temperatureF":current.get("temperature_2m"),"feelsLikeF":current.get("apparent_temperature"),"windMph":current.get("wind_speed_10m"),"highF":next(iter(daily.get("temperature_2m_max",[])),None),"lowF":next(iter(daily.get("temperature_2m_min",[])),None)}


def _news(_context, arguments, settings):
    topic = str(arguments.get("topic") or settings.get("defaultCategory") or "top").lower().strip()
    category = topic if topic in NEWS_FEEDS else str(settings.get("defaultCategory") or "top")
    response = httpx.get(NEWS_FEEDS[category], timeout=20, follow_redirects=True); response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    titles = [" ".join((node.text or "").split()) for node in root.findall(".//item/title") if (node.text or "").strip()]
    return {"status":"completed","topic":topic,"category":category,"headlines":titles[:max(1,min(int(settings.get("headlineCount") or 5),10))]}


def _search(credentials, context, query):
    result = run_web_search(credentials=credentials, context=context, query=query)
    return {**result, "operation":"plugin.search"}


def _market_query(arguments, settings):
    query = str(arguments.get("query") or "").strip()
    watchlist = ", ".join(settings.get("watchlist", []))
    return f"Current US stock market overview including market status, major indexes, top movers, and financial headlines. {'Focus on '+query if query else ''} {'Include watchlist '+watchlist if watchlist else ''} Cite current financial sources."


def _events_query(arguments, settings):
    location = str(arguments.get("location") or settings.get("homeLocation") or "").strip()
    if not location: raise ValueError("Local Events needs a home city or area")
    interests = ", ".join(settings.get("interests", []))
    return f"Find real upcoming events near {location}, within {settings.get('radiusMiles',25)} miles. Request: {arguments.get('query') or interests or 'interesting local events'}. Give dates, venues, prices when known, and official event links. Exclude past events."
