import requests
import pandas as pd
from datetime import datetime, timedelta
import time
from numpy.distutils.fcompiler.none import NoneFCompiler

base_url = "https://web-cdn.api.bbci.co.uk/wc-poll-data/container/sport-data-scores-fixtures"
headers = {"User-Agent": "Mozilla/5.0"}


class PLScraper:

    def __init__(self, start="2025-08-01", end="2026-05-31", finished=False):
        self.url = "https://web-cdn.api.bbci.co.uk/wc-poll-data/container/sport-data-scores-fixtures"
        self.start = start
        self.end = end
        self.finished = finished
        self.matches = []
        self.seen_ids = set()

    def fetch_matchday(self, date_str):
        params = {
            "selectedStartDate": date_str,
            "selectedEndDate": date_str,
            "todayDate": date_str,
            "urn": "urn:bbc:sportsdata:football:tournament:premier-league",
        }
        resp = requests.get(self.url, params=params)
        resp.raise_for_status()
        return resp.json()

    def parse_events(self, data, current_date):
        event_groups = data.get("eventGroups", [])
        if not event_groups:
            return None

        secondary = event_groups[0].get("secondaryGroups", [])
        if not secondary:
            return None

        next_anchor = None
        for group in secondary:
            for e in group.get("events", []):
                if "home" not in e or "away" not in e:
                    continue

                match_id = e.get("id")
                if match_id in self.seen_ids:
                    continue
                self.seen_ids.add(match_id)

                match_date = e.get("startTime", "")[:10]
                home = e["home"].get("fullName", "")
                away = e["away"].get("fullName", "")
                h_score = e["home"].get("score")
                a_score = e["away"].get("score")
                status = e.get("status", "")

                if status != "PostEvent":
                    self.finished = True
                    return self.finished

                self.matches.append({
                    "id": match_id,
                    "date": match_date,
                    "home_team": home,
                    "away_team": away,
                    "home_score": h_score,
                    "away_score": a_score,
                    "status": status,
                    "matchweek": group.get("title", "")
                })

                next_anchor = match_date
        return next_anchor

    def scrape_season(self):
        current_date = self.start
        end_dt = datetime.strptime(self.end, "%Y-%m-%d")

        while not self.finished:
            print(f"fetching {current_date}")
            data = self.fetch_matchday(current_date)
            next_anchor = self.parse_events(data, current_date)

            if not next_anchor or self.finished == True:
                dt = datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=1)
            else:
                dt = datetime.strptime(next_anchor, "%Y-%m-%d") + timedelta(days=1)

            if dt > end_dt:
                return self.matches

            current_date = dt.strftime("%Y-%m-%d")
            print(f"Collected {len(self.matches)}")
            time.sleep(0.1)
            if self.finished == True:
                print(pd.DataFrame(self.matches)[["home_team", "away_team"]])
                return self.matches

    def save_csv(self, filename="PL2425.csv"):
        df = pd.DataFrame(self.matches).drop_duplicates(subset=["id"])
        df.to_csv(filename, index=False)
        print(f"saved {len(df)}")


class Elo:

    def __init__(self, df, k=20, h_adv=0):
        self.df = df.copy()
        self.k = k
        self.h_adv = h_adv
        self.teams = pd.concat([df["home_team"], df["away_team"]]).unique()
        self.elo = {team: 1500 for team in self.teams}
        self.history = pd.DataFrame(columns=["Team", "Elo"])

    def expected_score(self, r_a, r_b):
        return 1 / (1 + 10 ** ((r_b - r_a) / 400))

    def update_match(self, home, away, hg, ag):
        if hg > ag:
            s_home, s_away = 1, 0
        elif hg == ag:
            s_home, s_away = 0.5, 0.5
        else:
            s_home, s_away = 0, 1

        e_home = self.expected_score(self.elo[home] + self.h_adv, self.elo[away])
        e_away = self.expected_score(self.elo[away], self.elo[home] + self.h_adv)

        self.elo[home] += self.k * (s_home - e_home)
        self.elo[away] += self.k * (s_away - e_away)

    def run_season(self):
        for _, row in self.df.iterrows():
            self.update_match(row["home_team"], row["away_team"], row["home_score"], row["away_score"])
            for team in [row["home_team"], row["away_team"]]:
                self.history = pd.concat([self.history, pd.DataFrame({
                    "Team": [team],
                    "Elo": [self.elo[team]]
                })], ignore_index=True)
        return self.elo

    def get_rankings(self):
        return pd.DataFrame(list(self.elo.items()), columns=["Team", "Elo"]).sort_values(by="Elo",
                                                                                         ascending=False).reset_index(
            drop=True)


if __name__ == "__main__":
    scraper = PLScraper()
    df_results = scraper.scrape_season()
    df_pd = pd.DataFrame(df_results)
    scraper.save_csv("PL2425.csv")

    elo_sys = Elo(df_pd, k=25, h_adv=75)
    elo_sys.run_season()
    finaL_rank = elo_sys.get_rankings()
    print("\nFinal Rankings:")
    print(finaL_rank)
