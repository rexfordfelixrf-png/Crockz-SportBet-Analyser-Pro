import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
from scipy.stats import poisson

st.set_page_config(
    page_title="SportsBet Analyzer Pro",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🏆"
)

# Dark mode toggle (Streamlit community component style)
dark_mode = st.sidebar.checkbox("Dark Mode 🌙", value=True)
if dark_mode:
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] {background: #0e1117 !important;}
    .stApp {background: #0e1117; color: white;}
    </style>
    """, unsafe_allow_html=True)

st.title("🏆 SportsBet Analyzer Pro — Live Odds + Predictions + Bankroll")
st.markdown("**Private local app** | The Odds API (odds) + API-SPORTS (stats) | Manual betting only")

# --- API Keys ---
col1, col2 = st.columns(2)
with col1:
    odds_api_key = st.text_input("The Odds API Key", type="password", help="Free at the-odds-api.com")
with col2:
    stats_api_key = st.text_input("API-SPORTS Key (optional for stats)", type="password", help="Free at api-sports.io")

if not odds_api_key:
    st.info("Enter your The Odds API key to load odds")
    st.stop()

# --- Bankroll Management ---
BANKROLL_FILE = "my_bankroll.json"

def load_bankroll():
    if os.path.exists(BANKROLL_FILE):
        with open(BANKROLL_FILE, 'r') as f:
            return json.load(f)
    return {"balance": 1000.0, "history": []}  # default 1000 units

def save_bankroll(data):
    with open(BANKROLL_FILE, 'w') as f:
        json.dump(data, f)

bankroll = load_bankroll()
st.sidebar.header("💰 Bankroll Tracker")
st.sidebar.metric("Current Balance", f"{bankroll['balance']:.2f} units")
st.sidebar.metric("Total Bets Tracked", len(bankroll['history']))

# Log a manual bet
with st.sidebar.expander("Log a Bet (after placing manually)"):
    bet_event = st.text_input("Event")
    bet_outcome = st.text_input("Your Bet (e.g. Team A Win)")
    odds_placed = st.number_input("Odds you took", min_value=1.01, value=2.0, step=0.1)
    stake = st.number_input("Stake (units)", min_value=0.1, value=10.0, step=1.0)
    if st.button("Log Bet"):
        if bet_event and stake > 0:
            bankroll['history'].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "event": bet_event,
                "outcome": bet_outcome,
                "odds": odds_placed,
                "stake": stake,
                "result": None  # update later
            })
            bankroll['balance'] -= stake
            save_bankroll(bankroll)
            st.sidebar.success("Bet logged! Update result later.")
        else:
            st.sidebar.error("Fill event & stake")

# Update bet result
with st.sidebar.expander("Update Bet Result"):
    if bankroll['history']:
        idx = st.selectbox("Select open bet", range(len(bankroll['history'])), format_func=lambda i: f"{bankroll['history'][i]['date']} - {bankroll['history'][i]['event']}")
        result = st.radio("Result", ["Win", "Loss", "Push"])
        if st.button("Update"):
            hist = bankroll['history'][idx]
            if hist['result'] is None:
                profit = 0
                if result == "Win":
                    profit = hist['stake'] * (hist['odds'] - 1)
                elif result == "Loss":
                    profit = -hist['stake']
                bankroll['balance'] += hist['stake'] + profit  # return stake + profit/loss
                hist['result'] = result
                hist['profit'] = profit
                save_bankroll(bankroll)
                st.sidebar.success(f"Updated! Profit: {profit:.2f} | New balance: {bankroll['balance']:.2f}")
    else:
        st.sidebar.info("No bets logged yet")

# ROI calc
if bankroll['history']:
    closed = [h for h in bankroll['history'] if h['result']]
    total_staked = sum(h['stake'] for h in closed)
    total_profit = sum(h.get('profit', 0) for h in closed)
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    st.sidebar.metric("ROI (closed bets)", f"{roi:.1f}%")

# --- Core App ---
@st.cache_data(ttl=900)  # 15 min
def get_sports():
    url = f"https://api.the-odds-api.com/v4/sports/?apiKey={odds_api_key}"
    try:
        resp = requests.get(url).json()
        return {s['title']: s['key'] for s in resp if not s.get('has_outrights', True)}
    except:
        return {}

sports = get_sports()
selected_sport_title = st.selectbox("Choose Sport", options=list(sports.keys()), index=0)
sport_key = sports.get(selected_sport_title)

regions = st.multiselect("Regions (au for PNG/Aus bookies)", ["au", "uk", "eu", "us"], default=["au"])
markets = st.multiselect("Markets", ["h2h", "spreads", "totals"], default=["h2h"])

# Poisson prediction helper (simple)
def poisson_prob(lambda_team, lambda_opp, outcome):
    if outcome == "home_win":
        return sum(poisson.pmf(i, lambda_team) * sum(poisson.pmf(j, lambda_opp) for j in range(i)) for i in range(1, 20))
    elif outcome == "away_win":
        return sum(poisson.pmf(i, lambda_opp) * sum(poisson.pmf(j, lambda_team) for j in range(i)) for i in range(1, 20))
    elif outcome == "draw":
        return sum(poisson.pmf(i, lambda_team) * poisson.pmf(i, lambda_opp) for i in range(20))
    return 0.5

if st.button("🔄 Fetch Odds + Analyze", type="primary"):
    with st.spinner("Loading live/upcoming odds..."):
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={odds_api_key}&regions={','.join(regions)}&markets={','.join(markets)}&oddsFormat=decimal"
        resp = requests.get(url)
        
        if resp.status_code == 200:
            data = resp.json()
            st.success(f"{len(data)} events | Check your API dashboard for credits left")
            
            events_list = []
            for ev in data:
                for book in ev.get('bookmakers', []):
                    for mkt in book.get('markets', []):
                        for out in mkt.get('outcomes', []):
                            events_list.append({
                                'Event': f"{ev['home_team']} vs {ev['away_team']}",
                                'Commence': ev['commence_time'],
                                'Bookie': book['title'],
                                'Market': mkt['key'],
                                'Outcome': out['name'],
                                'Odds': out['price'],
                                'Implied %': round(100 / out['price'], 1) if out['price'] > 0 else 0
                            })
            
            df = pd.DataFrame(events_list)
            df['Commence'] = pd.to_datetime(df['Commence']).dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(df.sort_values(['Event', 'Odds']), use_container_width=True)
            
            # Best odds
            st.subheader("Best Available Odds")
            best_df = df.groupby(['Event', 'Outcome', 'Market'])['Odds'].max().reset_index()
            st.dataframe(best_df, use_container_width=True)
            
            # Value + Poisson section
            st.subheader("🎯 Value Bets & Poisson Predictions")
            selected_event = st.selectbox("Pick Event", df['Event'].unique())
            event_df = df[df['Event'] == selected_event]
            
            if not event_df.empty:
                home, away = selected_event.split(" vs ")
                colA, colB = st.columns(2)
                with colA:
                    your_prob = st.slider(f"Your estimated prob for Home Win ({home}) %", 1, 99, 50)
                with colB:
                    outcome_choice = st.radio("Outcome to analyze", ["Home Win", "Away Win", "Draw (if available)"])
                
                best_odds = event_df[event_df['Outcome'].str.contains(outcome_choice, case=False, na=False)]['Odds'].max()
                if pd.isna(best_odds):
                    best_odds = event_df['Odds'].max()
                
                implied = 100 / best_odds if best_odds > 0 else 0
                edge = your_prob - implied
                
                # Simple Poisson (fallback averages; enhance with API-SPORTS if key provided)
                lambda_home = 1.6  # dummy avg goals
                lambda_away = 1.4
                if stats_api_key:
                    try:
                        # Example: fetch last matches (AFL/NRL/soccer)
                        league_id = 1 if "football" in selected_sport_title.lower() else None  # customize per sport
                        if league_id:
                            stats_url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season=2025&team=home_team_id_here"  # placeholder
                            # You can expand: get recent goals scored/conceded
                            # For now, keep simple
                    except:
                        pass
                
                pred_prob_home = poisson_prob(lambda_home, lambda_away, "home_win") * 100
                
                st.write(f"**Best Odds:** {best_odds:.2f}")
                st.write(f"**Implied Prob:** {implied:.1f}%")
                st.metric("Your Edge", f"{edge:+.1f}%")
                
                if edge > 5:
                    st.success(f"STRONG VALUE! Suggested Kelly bet: {max(0, (your_prob/100 - (1-your_prob/100)/(best_odds-1)))*100:.1f}% of bankroll")
                elif edge > 0:
                    st.info(f"Mild value — Kelly: {max(0, (your_prob/100 - (1-your_prob/100)/(best_odds-1)))*100:.1f}%")
                else:
                    st.warning("No clear value")
                
                st.info(f"Poisson est. Home Win prob: {pred_prob_home:.1f}% (simple model — improve with real stats)")
            
            # Download
            st.download_button("Export Odds CSV", df.to_csv(index=False), f"odds_{sport_key}_{datetime.now().strftime('%Y%m%d')}.csv")
        else:
            st.error(f"API error: {resp.text}")

st.caption("Tips: Use 'au' region for Sportsbet/TAB/Neds odds. Log bets manually after placing. Poisson is basic — real models need historical data. Gamble responsibly — set limits! Rexford, stay sharp in Kokopo. 🚀")
