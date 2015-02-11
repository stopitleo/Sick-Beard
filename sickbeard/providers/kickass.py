###################################################################################################
# Author: Jodi Jones <venom@gen-x.co.nz>
# URL: https://github.com/VeNoMouS/Sick-Beard
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.
###################################################################################################

import os
import re
import sys
import json
import urllib
import generic
import datetime
import sickbeard
import exceptions

from lib import requests
from xml.sax.saxutils import escape

from sickbeard import db
from sickbeard import logger
from sickbeard import tvcache
from sickbeard.exceptions import ex
from sickbeard.common import Quality
from sickbeard.common import Overview
from sickbeard import show_name_helpers

class KickAssProvider(generic.TorrentProvider):

    ###################################################################################################
    def __init__(self):
        generic.TorrentProvider.__init__(self, "KickAss")
        self.cache = KickAssCache(self)     
        self.name = "KickAss"
        self.session = None
        self.supportsBacklog = True
        self.url = "http://kat.ph"
        logger.log("[" + self.name + "] initializing...")
        
    ###################################################################################################
    
    def isEnabled(self):
        return sickbeard.KICKASS
    
    ###################################################################################################
    
    def imageName(self):
        return 'kickass.png'
    
    ###################################################################################################

    def getQuality(self, item):        
        quality = Quality.nameQuality(item[0])
        return quality 
    
    ###################################################################################################

    def _get_title_and_url(self, item):
        return item

    ###################################################################################################

    def _get_airbydate_season_range(self, season):        
        if season == None:
            return ()        
        year, month = map(int, season.split('-'))
        min_date = datetime.date(year, month, 1)
        if month == 12:
            max_date = datetime.date(year, month, 31)
        else:    
            max_date = datetime.date(year, month+1, 1) -  datetime.timedelta(days=1)
        return (min_date, max_date)    

    ###################################################################################################

    def _get_season_search_strings(self, show, season=None):
        search_string = []
    
        if not show:
            return []
      
        myDB = db.DBConnection()
        
        if show.air_by_date:
            (min_date, max_date) = self._get_airbydate_season_range(season)
            sqlResults = myDB.select("SELECT * FROM tv_episodes WHERE showid = ? AND airdate >= ? AND airdate <= ?", [show.tvdbid,  min_date.toordinal(), max_date.toordinal()])
        else:
            sqlResults = myDB.select("SELECT * FROM tv_episodes WHERE showid = ? AND season = ?", [show.tvdbid, season])
            
        for sqlEp in sqlResults:
            if show.getOverview(int(sqlEp["status"])) in (Overview.WANTED, Overview.QUAL):
                if show.air_by_date:
                    for show_name in set(show_name_helpers.allPossibleShowNames(show)):
                        ep_string = show_name_helpers.sanitizeSceneName(show_name) +' '+ str(datetime.date.fromordinal(sqlEp["airdate"])).replace('-', '.')
                        search_string.append(ep_string)
                else:
                    for show_name in set(show_name_helpers.allPossibleShowNames(show)):
                        ep_string = show_name_helpers.sanitizeSceneName(show_name) +' '+ sickbeard.config.naming_ep_type[2] % {'seasonnumber': season, 'episodenumber': int(sqlEp["episode"])}
                        search_string.append(ep_string)                       
        return search_string

    ###################################################################################################

    def _get_episode_search_strings(self, ep_obj):    
        search_string = []
       
        if not ep_obj:
            return []
        if ep_obj.show.air_by_date:
            for show_name in set(show_name_helpers.allPossibleShowNames(ep_obj.show)):
                ep_string = show_name_helpers.sanitizeSceneName(show_name) +' '+ str(ep_obj.airdate).replace('-', '.')
                search_string.append(ep_string)
        else:
            for show_name in set(show_name_helpers.allPossibleShowNames(ep_obj.show)):
                ep_string = show_name_helpers.sanitizeSceneName(show_name) +' '+ sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.season, 'episodenumber': ep_obj.episode}
                search_string.append(ep_string)
        return search_string    
 
    ###################################################################################################

    def _doSearch(self, search_params, show=None):
        results = []
        logger.log("[" + self.name + "] Performing Search: {0}".format(search_params))
        for page in range(1,3):
            searchData = None
            SearchParameters = {}
            
            if len(sickbeard.KICKASS_ALT_URL):
                self.url = sickbeard.KICKASS_ALT_URL
            
            if len(search_params):
                SearchParameters["q"] = search_params+" category:tv"
            else:
                SearchParameters["q"] = "category:tv"
                
            SearchParameters["order"] = "desc"
            SearchParameters["page"] = str(page)
            
            if len(search_params):
                SearchParameters["field"] = "seeders"
            else:
                SearchParameters["field"] = "time_add"
            
            SearchQuery = urllib.urlencode(SearchParameters)
            
            searchData = self.getURL(self.url + "json.php?%s" % SearchQuery )
              
            if searchData:
                try:
                    jdata = json.loads(searchData)
                except ValueError, e:
                    logger.log("[" + self.name + "] _doSearch() invalid data on search page " + str(page))
                    continue
                
                torrents = jdata.get('list', [0])
                
                for torrent in torrents:
                    item = (torrent['title'].replace('.',' '), torrent['torrentLink'])
                    logger.log("[" + self.name + "] _doSearch() Title: " + torrent['title'], logger.DEBUG)
                    results.append(item)
                    
        if not len(results):
            logger.log("[" + self.name + "] _doSearch() No results found.", logger.DEBUG)
        return results
    
    ###################################################################################################
    
    def getURL(self, url, headers=None):
        logger.log("[" + self.name + "] getURL() retrieving URL: " + url, logger.DEBUG)
        response = None
        
        if not self.session:
            self.session = requests.Session()
            
        if not headers:
            headers = []
            
        try:
            response = self.session.get(url, verify=False)
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError), e:
            logger.log("[" + self.name + "] getURL() Error loading " + self.name + " URL: " + ex(e), logger.ERROR)
            return None
        
        if response.status_code not in [200,302,303,404]:
            # response did not return an acceptable result
            logger.log("[" + self.name + "] getURL() requested URL - " + url +" returned status code is " + str(response.status_code), logger.ERROR)
            return None
        if response.status_code in [404]:
            # response returned an empty result
            return None

        return response.content
    
    ###################################################################################################

class KickAssCache(tvcache.TVCache):
    
    ###################################################################################################
    
    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)
        # only poll KAT every 15 minutes max
        self.minTime = 15
        
    ###################################################################################################
    
    def _getRSSData(self):
        logger.log("[" + provider.name + "] Retriving RSS")
        
        xml = "<rss xmlns:atom=\"http://www.w3.org/2005/Atom\" version=\"2.0\">" + \
            "<channel>" + \
            "<title>" + provider.name + "</title>" + \
            "<link>" + provider.url + "</link>" + \
            "<description>torrent search</description>" + \
            "<language>en-us</language>" + \
            "<atom:link href=\"" + provider.url + "\" rel=\"self\" type=\"application/rss+xml\"/>"
        data = provider._doSearch("")
        if data:
            for title, url in data:
                xml += "<item>" + "<title>" + escape(title) + "</title>" +  "<link>"+ url + "</link>" + "</item>"
        xml += "</channel></rss>"
        return xml
    
    ###################################################################################################

provider = KickAssProvider()
