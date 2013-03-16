#!/usr/bin/env python3
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

import sys
import os
import argparse
import configparser

from data import Player, Match
from provider import DataProvider, HttpDataProvider

"""honstats console statistics program for Heroes of Newerth
"""
def playercommand(args):
    print(Player.header())

    for id in args.id:
        #print(url)
        data = args.dataprovider.fetch('player_statistics/' + args.statstype + DataProvider.nickoraccountid(id))
        player = Player(id, data)
        #print(json.dumps(data))
        print(player.str(args.dataprovider, args.statstype))

def matchescommand(args):
    for id in args.id:
        data = args.dataprovider.fetchmatches(id, args.statstype)
        history = ""
        if len(data) > 0:
            history = data[0]['history']
        hist = history.split(',')
        limit = args.limit if args.limit else len(hist)
        matchids = [ int(x.split('|')[0]) for  x in hist ]
        matchids = sorted(matchids, reverse=True)

        print(args.dataprovider.id2nick(id))
        print(Match.headermatches())
        for i in range(limit):
            match = Match(args.dataprovider.fetchmatchdata([matchids[i]])[matchids[i]])
#        matches = args.dataprovider.fetchmatchdata(matchids[:limit])
#        for matchid in matchids[:limit]:
#            match = Match(matches[matchid])
            print(match.matchesstr(args.dataprovider.nick2id(id), args.dataprovider))
        #print(json.dumps(history))

def matchcommand(args):
    matches = args.dataprovider.fetchmatchdata(args.matchid)
    for mid in args.matchid:
        match = Match(matches[mid])
        print(match.matchstr(args.dataprovider))

def heroplayerscommand(args):
    print(args)

def main():
    parser = argparse.ArgumentParser(description='honstats fetches and displays Heroes of Newerth statistics')
    #parser.add_argument('--host', default='http://api.heroesofnewerth.com/', help='statistic host provider')
    parser.add_argument('--host', default='http://localhost:1234/', help='statistic host provider')
    parser.add_argument('-l', '--limit', type=int, help='Limit output to the given number')
    parser.add_argument('-t', '--token', help="hon statistics token")
    parser.add_argument('-s', '--statstype', choices=['ranked', 'public', 'casual'],
                        default='ranked', help='Statstype to show')

    subparsers = parser.add_subparsers(help='honstats commands')
    playercmd = subparsers.add_parser('player', help='Show player stats')
    playercmd.set_defaults(func=playercommand)
    playercmd.add_argument('id', nargs='+', help='Player nickname or hon id')

    matchescmd = subparsers.add_parser('matches', help='Show matches of a player(s)')
    matchescmd.set_defaults(func=matchescommand)
    matchescmd.add_argument('id', nargs='+', help='Player nickname or hon id')

    matchcmd = subparsers.add_parser('match', help='Show stats for match(es)')
    matchcmd.set_defaults(func=matchcommand)
    matchcmd.add_argument('matchid', nargs='+', help='HoN match id')

    heroplayercmd = subparsers.add_parser('hero-players', help='Show stats for heros played')
    heroplayercmd.set_defaults(func=heroplayerscommand)
    heroplayercmd.add_argument('id', nargs='+', help='Player nickname or hon id')
    heroplayercmd.add_argument('-b', "--sort-by", choices=['use','kdr','k','d','a','kpg','dpg','apg'],
                               default='use', help='Sort by specified stat')

    args = parser.parse_args()

    configpath = '/etc/honstats'
    if not os.path.exists(configpath):
        configpath = os.path.expanduser('~/.config/honstats/config')
    if os.path.exists(configpath):
        cp = configparser.SafeConfigParser({'directory': os.path.expanduser('~/.honstats')})
        cp.read(configpath)
    else:
        cp = {}

    if not args.token and not 'auth' in cp:
        sys.exit('Token not specified and no config file found.')
    else:
        args.token = cp.get('auth', 'token')

    if 'func' in args:
        args.dataprovider = HttpDataProvider(args.host, token=args.token,  cachedir=cp.get('cache', 'directory'))
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
