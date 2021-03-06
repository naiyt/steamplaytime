import re
import logging
import math
import json
import urllib2
import counters
import config
from bs3.BeautifulSoup import BeautifulSoup
from datastore.models import *
from datetime import datetime, timedelta
from random import choice
from google.appengine.api import mail
from google.appengine.api import datastore_errors
from config import *


def remove_specials(str):
    """
    Removes everything but letters from a string. This is used to create "search names" for games
    in the datastore. This makes it easier to compare the names on HLTB with Steam, and reduces
    the number of games incorrectly reported as not existing on HTLB.

    e.g. - Chivalry: Medieval Warfare -> chivalrymedievalwarfare 

    """

    special = r'[^0-9A-Za-z]'
    str = str.lower()
    return re.sub(special, '', str)

def get_user(steam_id):
    return SteamIds.get_by_id(steam_id)

def users_games(games):
    """Given a list of game appids, returns a SteamGames object"""
    games_list = []
    for game in games:
        new_game = SteamGames.find_game_by_appid(game)
        if new_game:
            games_list.append(new_game)
    return games_list

def calc_value(games):
    """Takes a list of appids, and determines the worth of all the games"""
    price = 0.0
    for game in games:
        if game:
            price += game.price
    return price

def find_games_by_id(games):
    all_games = []
    for game in games:
        all_games.append(ndb.Key('Games_DB', str(game)))
    return ndb.get_multi(all_games)

def all_games():
    """Retrieves ALL the games! Ordered by name. Not using this currently."""
    q = Games_DB.query()
    q.order(-Games_DB.game_name)
    return q

def convert_to_utc(date, time_zone):
    """Given an integer offset, converts date to UTC for easier comparisons"""
    return date - timedelta(hours=time_zone)

def validate_format_date(date, time_zone):
    """Makes sure that a date is in the correct format"""
    curr_time = datetime.utcnow()
    try:
        date = datetime.strptime(date, "%m/%d/%Y %I %p")
        date = convert_to_utc(date, time_zone)      
        if date <= curr_time: # Don't allow dates before the current time
            return None
        elif date > curr_time + timedelta(days=14): # Don't allow dates greater
                                                         # than two weeks away
            return None
        return date
    except ValueError:
        return None

def validate_date(date):
    try:
        date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return date
    except:
        return None

def create_json(json_str):
    """Grabs a json string and returns a dictionary you can use"""
    try:
        json_obj = json.loads(json_str)
        return json_obj
    except:
        return None

def find_item(name, find_by_name=True):
    """Finds an item by either name or appidw"""
    if find_by_name:
        item = Games_DB.query(Games_DB.search_name == name)
        if item:
            return item.get()
    else:
        item = Games_DB.get_by_id(str(name))
        if item:
            return item

def retrieve_stats():
    stats = Stats.get_by_id('1')
    if stats is None:
        stats = Stats(id='1',games_last_updated=datetime.now(),hltb_last_updated=datetime.now())
        stats.put()
    return stats

def retrieve_counts():
    total_queries = counters.SimpleCounter.get_by_id(queries_counter)
    total_ids = counters.SimpleCounter.get_by_id(steamids_counter)
    if total_queries and total_ids:
        return total_queries.count, total_ids.count
    else:
        return 0, 0

def retrieve_hit_count():
    ent_keys = []
    for thing in hit_counters:
        ent_keys.append(ndb.Key(counters.SimpleCounter, thing))
    all_entities = ndb.get_multi(ent_keys)
    count = 0
    for ent in all_entities:
        try:
            count += ent.count
        except AttributeError:
            pass
    return count

def retrieve_lost():
    lost = LostIds.get_by_id('1')
    if lost is None:
        lost = LostIds(id='1')
        lost.put()
    return lost

def create_bad_id(reasons):
    """Used for specifiying bad ids when reporting"""
    bad_id = None
    if reasons[1] == 1:
        bad_id = Bad_IDS(id=reasons[0],appid=int(reasons[0]),count=1,hltb_exists=1)
    elif reasons[1] == 2:
        bad_id = Bad_IDS(id=reasons[0],appid=int(reasons[0]),count=1,nasty_numbers=1)
    elif reasons[1] == 3:
        bad_id = Bad_IDS(id=reasons[0],appid=int(reasons[0]),count=1,mp_only=1)
    elif reasons[1] == 4:
        bad_id = Bad_IDS(id=reasons[0],appid=int(reasons[0]),count=1,other_issues=1)
    bad_id.put()

def update_bad_id(reasons, bad_id):
    bad_id.count += 1
    if reasons[1] == 1:
        bad_id.hltb_exists += 1
    elif reasons[1] == 2:
        bad_id.nasty_numbers += 1
    elif reasons[1] == 3:
        bad_id.mp_only += 1
    elif reasons[1] == 4:
        bad_id.other_issues += 1
    bad_id.put()