"""
This file is part of honstats.

honstats is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

honstats is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with honstats.  If not, see <http://www.gnu.org/licenses/>.
"""
import os
import json
import sqlite3
import urllib.request
from urllib.error import HTTPError
import gzip
import time

DBCREATE = """
CREATE TABLE IF NOT EXISTS player (
id  INTEGER PRIMARY KEY,
nick TEXT
);

CREATE TABLE IF NOT EXISTS playerdata (
id INTEGER,
date DATETIME,
statstype TEXT,
data TEXT,
PRIMARY KEY(id, date, statstype)
);

CREATE TABLE IF NOT EXISTS hero (
id INTEGER PRIMARY KEY,
name TEXT
);
"""


class NoResultsError(Exception):
    pass


class DataProvider(object):
    MatchCacheDir = 'match'
    PlayerCacheDir = 'player'

    CacheTime = 60 * 15

    HeroNicks = {
        6: "Devo",
        9: "Elec",
        14: "NH",
        15: "Swift",
        16: "BH",
        25: "KotF",
        26: "TDL",
        27: "VJ",
        29: "WB",
        42: "MadM",
        43: "DS",
        104: "Hag",
        108: "PR",
        109: "SR",
        114: "CD",
        120: "WS",
        121: "FA",
        124: "Chip",
        161: "Gladi",
        162: "DR",
        185: "Sil",
        192: "RA",
        195: "EW",
        201: "DM",
        209: "Salf",
        234: "Benz"
    }

    @staticmethod
    def nickoraccountid(aid):
        try:
            int(aid)
            return '/accountid/' + str(aid)
        except ValueError:
            return '/nickname/' + aid


class HttpDataProvider(DataProvider):
    StatsMapping = {'ranked': 'rnk', 'public': 'acc', 'casual': 'cs'}

    def __init__(self, url='api.heroesofnewerth.com', token=None, cachedir="~/.honstats"):
        self.url = url
        self.token = token
        self.cachedir = os.path.abspath(os.path.expanduser(cachedir))
        if self.cachedir:
            os.makedirs(self.cachedir, exist_ok=True)
            dbfile = os.path.join(self.cachedir, 'stats.db')
            self.db = sqlite3.connect(dbfile)
            self.db.executescript(DBCREATE)

            os.makedirs(os.path.join(self.cachedir, DataProvider.MatchCacheDir), exist_ok=True)
            os.makedirs(os.path.join(self.cachedir, DataProvider.PlayerCacheDir), exist_ok=True)

    def __del__(self):
        self.db.close()

    def nick2id(self, nick):
        try:
            int(nick)
        except ValueError:
            cursor = self.db.cursor()
            cursor.execute("SELECT id from player WHERE lower(nick) = lower(:nick)", {'nick': nick})
            row = cursor.fetchone()
            cursor.close()
            if row:
                return int(row[0])
            data = self.fetch('/player_statistics/ranked/nickname/' + nick)
            # insert the real nick into database, case sensitiv
            self.id2nick(int(data['account_id']))
            return int(data['account_id'])
        return int(nick)

    def id2nick(self, aid):
        if isinstance(aid, int):
#            resp = urllib.request.urlopen('http://forums.heroesofnewerth.com/member.php?' + str(int(id)))
#            begin = resp.read(4048).decode('utf-8')
#            print(begin)
#            m = re.search(r'<title>View Profile:\s*(\S+)-', begin)
#            if m:
#                return m.group(1)
            cursor = self.db.cursor()
            cursor.execute("SELECT nick FROM player WHERE id = :id", {'id': aid})
            row = cursor.fetchone()
            cursor.close()
            if row:
                return row[0]

            data = self.fetch('/player_statistics/ranked/accountid/' + str(aid))

            self.db.execute('INSERT INTO player VALUES( :id, :nick );', {'id': aid, 'nick': data['nickname']})
            self.db.commit()
            return data['nickname']

        return str(aid)

    def heroid2name(self, aid, full=False):
        if not full and aid in DataProvider.HeroNicks:
            return DataProvider.HeroNicks[aid]
        cursor = self.db.cursor()
        cursor.execute("SELECT name FROM hero WHERE id = :id", {'id': aid})
        row = cursor.fetchone()
        cursor.close()
        if row:
            return row[0]
        data = self.fetch('/heroes/id/{id}'.format(id=aid))
        name = data['disp_name'].strip()
        self.db.execute('INSERT INTO hero VALUES( :id, :name);',  {'id': aid, 'name': name})
        self.db.commit()
        return name

    def fetch(self, path):
        url = self.url + path + "/?token=" + self.token
        #print(url)
        try:
            resp = urllib.request.urlopen(url)
        except HTTPError as e:
            if e.code == 404:
                raise NoResultsError()
            if e.code == 429:  # too much requests
                time.sleep(0.1)  # this might be a bit harsh, but fetch until we get what we want
                return self.fetch(path)
            raise e
        raw = resp.read().decode('utf-8').strip()

        # work around a serialization bug from hon
        if raw.startswith('Notice:'):
            raw = raw[raw.find('\n'):]
        data = json.loads(raw)
        resp.close()
        return data

    def fetchplayer(self, aid, statstype):
        cursor = self.db.cursor()
        cursor.execute("SELECT data FROM playerdata WHERE id=:id AND "
                       "strftime('%s',date)-:date>0 AND statstype=:statstype ORDER BY date;",
                       {'id': self.nick2id(aid), 'date': int(time.time() - DataProvider.CacheTime),
                        'statstype': statstype})
        row = cursor.fetchone()
        cursor.close()
        if row:
            return json.loads(row[0])
        data = self.fetch('/player_statistics/' + statstype + DataProvider.nickoraccountid(aid))

#        # check if the data really changed
#        cursor = self.db.cursor()
#        cursor.execute("SELECT data FROM playerdata WHERE id=:id AND statstype=:statstype " \
#                       "AND strftime('%s', date)=(select MAX(strftime('%s',date)) " \
#                       "from playerdata WHERE id=:id AND statstype=:statstype);",
#                       {'id': self.nick2id(id), 'date': int(time.time() - DataProvider.CacheTime),
#                       'statstype': statstype})
#        dbdata = json.loads(cursor.fetchone()[0])
#        # insert if we have more games
#        if int(dbdata[self.StatsMapping[statstype] + '_games_played']) !=
#           int(data[self.StatsMapping[statstype] + '_games_played']):
        if True:
            self.db.execute("INSERT INTO playerdata VALUES(:id, CURRENT_TIMESTAMP, :statstype, :data);",
                            {'id': self.nick2id(aid), 'statstype': statstype, 'data': json.dumps(data)})
            self.db.commit()

        return data

    def fetchmatches(self, aid, statstype):
        playerdir = os.path.join(self.cachedir,  DataProvider.PlayerCacheDir)
        playermatches = os.path.join(playerdir, "{id}_matches_{statstype}.gz".format(
            id=self.nick2id(aid),
            statstype=statstype))
        if os.path.exists(playermatches) and os.stat(playermatches).st_ctime > time.time() - DataProvider.CacheTime:
            with gzip.open(playermatches, 'rt') as f:
                data = json.load(f)
        else:
            path = '/match_history/' + statstype + DataProvider.nickoraccountid(aid)
            data = self.fetch(path)
            with gzip.open(playermatches, 'wt+') as f:
                f.write(json.dumps(data))
        return data

    def matches(self, aid, statstype):
        data = self.fetchmatches(aid, statstype)
        history = ""
        if len(data) > 0:
            history = data[0]['history']
        hist = history.split(',')
        matchids = [int(x.split('|')[0]) for x in hist]
        matchids = sorted(matchids, reverse=True)
        return matchids

    def fetchmatchdata(self, matchids, *, limit=None, id_hero=None):
        """Fetches match data by id and caches it onto disk
           First checks if the match stats are already cached

           Args:
             matchids: list of match ids

           Returns:
             dict with matches, the key is the matchid
        """
        data = {}
        limit = limit if limit else len(matchids)
        heroname = None
        aid = None
        if id_hero:
            aid, heroname = id_hero
            aid = self.nick2id(aid)

        i = 0
        while len(data) < limit and i < len(matchids):
            matchid = matchids[i]
            matchdir = os.path.join(self.cachedir,  DataProvider.MatchCacheDir)
            matchpath = os.path.join(matchdir, str(matchid)[0:4])
            os.makedirs(matchpath, exist_ok=True)
            matchpath = os.path.join(matchpath, str(matchid) + ".gz")
            if os.path.exists(matchpath):
                with gzip.open(matchpath, 'rt') as f:
                    matchdata = json.load(f)
            else:
                try:
                    matchdata = self.fetch('/match/summ/matchid/{id}'.format(id=matchid))
                    matchstats = self.fetch('/match/all/matchid/{id}'.format(id=matchid))
                    matchdata.append(matchstats[0][0])  # settings
                    matchdata.append(matchstats[1])  # items
                    matchdata.append(matchstats[2])  # player stats
                    with gzip.open(matchpath, 'wt+') as f:
                        f.write(json.dumps(matchdata))
                except NoResultsError:
                    matchdata = None

            if id_hero and matchdata:
                playerstats = matchdata[3]
                for stats in playerstats:
                    if aid == int(stats['account_id']):
                        playedhero = self.heroid2name(stats['hero_id'], full=True).lower()
                        if heroname in playedhero:
                            data[matchid] = matchdata
                        break
            else:
                data[matchid] = matchdata
            i += 1
        return data

    def heroes(self):
        return self.fetch('/heroes/all')
