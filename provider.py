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
#import re

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

class DataProvider(object):
    MatchCacheDir = 'match'
    PlayerCacheDir = 'player'

    CacheTime = 60 * 15

    HeroNicks = {
        6: "Devo",
        9: "Elec",
        15: "Swift",
        16: "BH",
        29: "WB",
        42: "MadM",
        43: "DS",
        104: "Hag",
        121: "FA",
        161: "Gladi",
        185: "Sil",
        192: "RA"
    }

    @staticmethod
    def nickoraccountid(id):
        try:
            int(id)
            return '/accountid/' + str(id)
        except ValueError:
            return '/nickname/' + id

class HttpDataProvider(DataProvider):
    StatsMapping = {'ranked': 'rnk', 'public': 'acc', 'casual': 'cs'}

    def __init__(self, url = 'http://api.heroesofnewerth.com/', token=None, cachedir="~/.honstats"):
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
            cursor.execute("SELECT id from player WHERE lower(nick) = lower(:nick)", { 'nick': nick})
            row = cursor.fetchone()
            cursor.close()
            if row:
                return int(row[0])
            data = self.fetch('player_statistics/ranked/nickname/' + nick)
            # insert the real nick into database, case sensitiv
            self.id2nick(int(data['account_id']))
            return int(data['account_id'])
        return int(nick)

    def id2nick(self, id):
        if isinstance(id,int):
#            resp = urllib.request.urlopen('http://forums.heroesofnewerth.com/member.php?' + str(int(id)))
#            begin = resp.read(4048).decode('utf-8')
#            print(begin)
#            m = re.search(r'<title>View Profile:\s*(\S+)-', begin)
#            if m:
#                return m.group(1)
            cursor = self.db.cursor()
            cursor.execute("SELECT nick FROM player WHERE id = :id", { 'id': id})
            row = cursor.fetchone()
            cursor.close()
            if row:
                return row[0]

            resp = urllib.request.urlopen('http://www.hondmg.com/api/id_to_nick/' + str(int(id)))
            reply = json.loads(resp.read().decode())
            resp.close()
            if str(id) in reply:
                self.db.execute('INSERT INTO player VALUES( :id, :nick );', {'id': id, 'nick': reply[str(id)]})
                self.db.commit()
                return reply[str(id)]

        return str(id)

    def heroid2name(self, id, full=False):
        if not full and id in DataProvider.HeroNicks:
            return DataProvider.HeroNicks[id]
        cursor = self.db.cursor()
        cursor.execute("SELECT name FROM hero WHERE id = :id", { 'id': id})
        row = cursor.fetchone()
        cursor.close()
        if row:
            return row[0]
        data = self.fetch('heroes/id/{id}'.format(id=id))
        name = data['disp_name'].strip()
        self.db.execute('INSERT INTO hero VALUES( :id, :name);',  {'id': id, 'name':name})
        self.db.commit()
        return name

    def fetch(self, path):
        url = self.url + path + "/?token=" + self.token
        #print(url)
        try:
            resp = urllib.request.urlopen(url)
        except HTTPError as e:
            if e.code == 429: #too much requests
                time.sleep(0.1) # this might be a bit harsh, but fetch until we get what we want
                return self.fetch(path)
            raise e
        data = json.loads(resp.read().decode('utf-8'))
        resp.close()
        return data

    def fetchplayer(self, id, statstype):
        cursor = self.db.cursor()
        cursor.execute("SELECT data FROM playerdata WHERE id=:id AND strftime('%s',date)-:date>0 AND statstype=:statstype ORDER BY date;",
                       {'id': self.nick2id(id), 'date': int(time.time() - DataProvider.CacheTime), 'statstype': statstype})
        row = cursor.fetchone()
        cursor.close()
        if row:
            return json.loads(row[0])
        data = self.fetch('player_statistics/' + statstype + DataProvider.nickoraccountid(id))

#        # check if the data really changed
#        cursor = self.db.cursor()
#        cursor.execute("SELECT data FROM playerdata WHERE id=:id AND statstype=:statstype " \
#                       "AND strftime('%s', date)=(select MAX(strftime('%s',date)) from playerdata WHERE id=:id AND statstype=:statstype);",
#                       {'id': self.nick2id(id), 'date': int(time.time() - DataProvider.CacheTime), 'statstype': statstype})
#        dbdata = json.loads(cursor.fetchone()[0])
#        # insert if we have more games
#        if int(dbdata[self.StatsMapping[statstype] + '_games_played']) != int(data[self.StatsMapping[statstype] + '_games_played']):
        if True:
            self.db.execute("INSERT INTO playerdata VALUES(:id, CURRENT_TIMESTAMP, :statstype, :data);",
                            {'id': self.nick2id(id), 'statstype': statstype, 'data': json.dumps(data)})
            self.db.commit()

        return data

    def fetchmatches(self, id, statstype):
        playerdir = os.path.join(self.cachedir,  DataProvider.PlayerCacheDir)
        playermatches = os.path.join(playerdir, "{id}_matches_{statstype}.gz".format(id=self.nick2id(id), statstype=statstype))
        if os.path.exists(playermatches) and os.stat(playermatches).st_ctime > time.time() - DataProvider.CacheTime:
            with gzip.open(playermatches, 'rt') as f:
                data = json.load(f)
        else:
            path = 'match_history/' + statstype + DataProvider.nickoraccountid(id)
            data = self.fetch(path)
            with gzip.open(playermatches,'wt+') as f:
                f.write(json.dumps(data))
        return data

    def matches(self, id, statstype):
        data = self.fetchmatches(id, statstype)
        history = ""
        if len(data) > 0:
            history = data[0]['history']
        hist = history.split(',')
        matchids = [ int(x.split('|')[0]) for  x in hist ]
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
        if id_hero:
            id, heroname = id_hero
            id = self.nick2id(id)

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
                matchdata = self.fetch('match/summ/matchid/{id}'.format(id=matchid))
                matchstats = self.fetch('match/all/matchid/{id}'.format(id=matchid))
                matchdata.append(matchstats[0][0]) # settings
                matchdata.append(matchstats[1]) # items
                matchdata.append(matchstats[2]) # player stats
                with gzip.open(matchpath, 'wt+') as f:
                    f.write(json.dumps(matchdata))
            if id_hero:
                playerstats = matchdata[3]
                for stats in playerstats:
                    if id == int(stats['account_id']):
                        playedhero = self.heroid2name(stats['hero_id'],full=True).lower()
                        if heroname in playedhero:
                            data[matchid] = matchdata
                        break
            else:
                data[matchid] = matchdata
            i += 1
        return data

class FSDataProvider(DataProvider):
    def __init__(self, url = './sampledata'):
        self.url = os.path.abspath(url)

    def fetch(self, path):
        with open(os.path.join(self.url, path)) as fd:
            return json.load(fd)
