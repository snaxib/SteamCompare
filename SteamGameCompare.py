import requests
import json
import time
import re
from pymongo import MongoClient
import datetime
import xml.etree.ElementTree as ET
from flask import Flask
from flask import abort, redirect, url_for, request, jsonify

client = MongoClient()
db = client.gameData
gamedb = db.game

settings = json.load(open('settings.json'))

webKey = settings['webKey']

app = Flask(__name__)


class Player:

    name = None
    avatarURI = None
    profileURI = None
    steamId = None


# This is for console output

class bcolors:

    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


# Maybe can be moved to a local file later, but for now it's here
STEAM_ID_ERROR_TYPE = [{
    'type':'STEAM_ID_LOOKUP_ERROR',
    'error':'user_not_found',
    'code':0,
    'message':'The user you were trying to lookup was not found.'
},{
    'type':'STEAM_ID_LOOKUP_ERROR',
    'eror':'unknown_error',
    'code':1,
    'message':'An unknown erorr occured when looking up the users steam id.'
}

]
STEAM_APP_ERROR_TYPE = [{
    'type': 'STEAM_APP_ERROR',
    'error': 'rate_limited',
    'code': 0,
    'message': 'Over 200 detail requests in the last 5 minutes. Wait 5 or more minutes before making any new requests.'
        ,
    }, {
    'type': 'STEAM_APP_ERROR',
    'error': 'game_does_not_exist',
    'code': 1,
    'message': 'The game you were requesting information on does not exist. Either the ID is incorrect or it was replaced by another app on Steam.',
    }, {
    'type': 'STEAM_APP_ERROR',
    'error': 'redirect',
    'code': 2,
    'message': 'The game redirects to another title.',
    }]

# basic uri and auth stuff

steamOwnedGamesBaseURI = 'https://api.steampowered.com/'
steamGameInfoBaseURI = 'http://store.steampowered.com/api/'
steamPlayerInfoBaseURI = 'http://api.steampowered.com/'
steamPlayerIDBaseURI = 'https://steamcommunity.com/id/'
steamMediaBaseURI = 'http://media.steampowered.com/steamcommunity/public/images/apps/'
steamWishlistBaseURI = 'https://store.steampowered.com/wishlist/profiles/'

# A filler DB entry for games that have no categories

nullCategory = {'id': 0, 'description': 'This Game has No Categories'}


def playersToDict(players):
    if type(players) is list:
        playerList = []
        for player in players:
            dict = {}
            dict['name'] = player.name
            dict['avatarURI'] = player.avatarURI
            dict['profileURI'] = player.profileURI
            dict['steamid'] = player.steamId
            playerList.append(dict)
        return playerList
    elif type(players) is Player:
        dict = {}
        dict['name'] = players.name
        dict['avatarURI'] = players.avatarURI
        dict['profileURI'] = players.profileURI
        dict['steamid'] = players.steamId
        return dict


def zipLists(userlists):
    rawids = []
    seenIDs = []
    dupeids = []
    result = []
    for gamelist in userlists:
        for game in gamelist['games']:
            rawids.append(game['appid'])
    dupeids = [x for n, x in enumerate(rawids) if x in rawids[:n]]
    for gamelist in userlists:
        for game in gamelist['games']:
            if game['appid'] in dupeids:
                if game['appid'] not in seenIDs:
                    seenIDs.append(game['appid'])
                    game['users'] = []
                    game['users'].append(gamelist['player'])
                    if 'wishlist' in game:
                        game['wishlist'] = []
                        game['wishlist'].append(gamelist['player'])
                    result.append(game)
                elif game['appid'] in seenIDs:
                    for title in result:
                        if game['appid'] == title['appid']:
                            title['users'].append(gamelist['player'])
                            if 'wishlist' in game:
                                if 'wishlist' in title:
                                    title['wishlist'].append(gamelist['player'])
                                if 'wishlist' not in title:
                                    title['wishlist'] = []
                                    title['wishlist'].append(gamelist['player'])

            if game['appid'] not in dupeids:
                pass
    return result


def lookupSingle(gameID):
    gameData = gamedb.find_one({'appid':gameID},{'_id': False})
    if gameData is not None:
        return gameData
    else:
        r = requests.get(steamGameInfoBaseURI + 'appdetails?appids='
                         + str(gameID))
        gameJSON = json.loads(r.text)
        if r.text == 'null':
            return 0, gameJSON
        elif gameJSON[str(gameID)]['success'] == False:
            return 1, gameJSON
        elif gameID != gameJSON[str(gameID)]['data']['steam_appid']:
            return 2, gameJSON
        else:
            return 3, gameJSON


def getUserSteamID(steamName):
    playerXMLRaw = requests.get(steamPlayerIDBaseURI + steamName + '/?xml=1')
    playerXMLRoot = ET.fromstring(playerXMLRaw.text)
    if playerXMLRoot.tag == 'response':
        return 0
    elif playerXMLRoot.tag == 'profile':
        steamID64 = playerXMLRoot.find('steamID64')
        return steamID64.text
    else:
        return 1


def buildQuickGameList(id):
    '''
    returns dict of gamelist, if access denied throw.
    This does not do any filtering based on categories or anything
    Literally just returns the getOwnedGames
    '''
    userListRaw = requests.get(steamOwnedGamesBaseURI
                               + '/IPlayerService/GetOwnedGames/v1/?key='
                                + webKey + '&steamId=' + str(id)
                               + '&include_appinfo=1&include_played_free_games=1&format=json'
                               )
    userListJSON = json.loads(userListRaw.text)
    if userListJSON['response'] == {}:
        brokenBoi = getPlayerData(id)
        print (brokenBoi.name \
                    + ' needs to update their profile settings here: https://steamcommunity.com/profiles/' \
                    + str(brokenBoi.steamId) + '/edit/settings')
        print ("They need to set their 'Game Details' to 'Public'")
        return 2
    return userListJSON


# This is the "Full Compare." Basically it gets the user's owned games, then checks the local DB for it, and grabs details of it doesn't exist in the DB

def buildUserGameList(player, wishlist=False, debug=False):
    gameList = []
    gameData = {}
    userWishlist = []
    userListRaw = requests.get(steamOwnedGamesBaseURI
                                + '/IPlayerService/GetOwnedGames/v1/?key=' \
                                + webKey + '&steamId=' + player.steamId \
                                + '&include_appinfo=1&include_played_free_games=1&format=json')

  # Use this to tell which game(s) break on a steam library (SHould no longer be needed, but keeping it just in case)
  # f = open("debug.txt", 'w')
  # f.write(userListRaw.text)

    userListJSON = json.loads(userListRaw.text)

  # This is a check to see if the user has their game visibility set to public, and returns 2 if they are not

    if userListJSON['response'] == {}:
        print (player.name \
            + ' needs to update their profile settings here: https://steamcommunity.com/profiles/' \
            + str(player.steamId) + '/edit/settings')
        print("They need to set their 'Game Details' to 'Public'")
        return 2
    else:
        userGames = userListJSON['response']['games']
        if wishlist == "True":
            userWishlist = getUserWishlist(player)  
            print(userWishlist)
        if userWishlist != []:
            for game in userWishlist:
                userGames.append(game)
        totalGames = len(userGames)
        gameCursor = 0
        for g in userGames:
            
      # This is/was for console output - Mostly because as of writing this, there's no frontend and sending people JSON is not as...parseable
            print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
            gameCursor += 1
            userAppId = str(g['appid'])
            gameStatus = lookupSingle(g['appid'])
            if isinstance(gameStatus, dict):
                if 'priority' not in g:
                    gameStatus['thumbnail'] = 'https://steamcdn-a.akamaihd.net/steam/apps/' + userAppId +'/header_292x136.jpg'
                    gameStatus['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                    gameList.append(gameStatus)
                if 'priority' in g:
                    gameStatus['thumbnail'] = 'https://steamcdn-a.akamaihd.net/steam/apps/' + userAppId +'/header_292x136.jpg'
                    gameStatus['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                    gameStatus['wishlist'] = True
                    gameList.append(gameStatus)
            elif gameStatus[0] == 0:

        # This is the Rate-limited case
        # Maybe there should be some logic here for waiting.

                pass
            elif gameStatus[0] == 1:

        # This is the success=false case
                gamedb.insert_one({'name':g['name'],
                                'appid':g['appid'],
                                'categories':[nullCategory],
                                'unavailable':True})
                newGame = gamedb.find_one({'appid':int(userAppId)},{'_id': False})
                newGame['thumbnail'] = steamMediaBaseURI + userAppId + '/' + g['img_logo_url'] + '.jpg'
                newGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                gameList.append(newGame)
            elif gameStatus[0] == 2:
                gameDetails = gameStatus[1]

        # This is the case where Multiple games return the game details for the same game
        # This happens with Expansion packs that are no longer for individual sale often.
        # Examples include F.E.A.R. Purseus Mandate/Extraction Point (appid's: 21110/21120)

                if gamedb.find_one({'appid':gameDetails[userAppId]['data']['steam_appid'] }):

          # The game whose details were returned we have info for

                    if not gamedb.find_one({"appid":g['appid']}):

            # We do not have an ID with the game we searched for

                        if 'categories' in gameDetails[userAppId]['data']:
                            gamedb.insert_one({'name':g['name'],
                                            'appid':g['appid'],
                                            'categories':gameDetails[userAppId]['data']['categories'],
                                            'platforms':gameDetails[userAppId]['data']['platforms'],
                                            'is_free':gameDetails[userAppId]['data']['is_free']})
                            newGame = gamedb.find_one({'appid':int(userAppId)},{'_id': False})
                            newGame['thumbnail'] = 'https://steamcdn-a.akamaihd.net/steam/apps/' + userAppId +'/header_292x136.jpg'
                            newGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                            gameList.append(newGame)
                        else:
                            gamedb.insert_one({'name':g['name'],
                                            'appid':g['appid'],
                                            'categories':[nullCategory],
                                            'platforms':gameDetails[userAppId]['data']['platforms'],
                                            'is_free':gameDetails[userAppId]['data']['is_free']})
                            newGame = gamedb.find_one({'appid':int(userAppId)},{'_id': False})
                            newGame['thumbnail'] = 'https://steamcdn-a.akamaihd.net/steam/apps/' + userAppId +'/header_292x136.jpg'
                            newGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                            gameList.append(newGame)
                    elif gamedb.find_one({'appid':g['appid']}):
                        newGame = gamedb.find_one({'appid':int(userAppId)},{'_id': False})
                        newGame['thumbnail'] = 'https://steamcdn-a.akamaihd.net/steam/apps/' + userAppId +'/header_292x136.jpg'
                        newGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                        gameList.append(newGame)
                    else:
                        pass
            elif gameStatus[0] == 3:
                newGameRaw = gameStatus[1]
                newGame = newGameRaw[userAppId]['data']
                newGameInsert = gamedb.insert_one({'appid':newGame['steam_appid'],
                                                    'name':newGame['name'],
                                                    'categories':newGame['categories'],
                                                    'platforms':newGame['platforms'],
                                                    'is_free':newGame['is_free']})
                foundGame = gamedb.find_one({'appid':int(userAppId)},{'_id': False})
                foundGame['thumbnail'] = 'https://steamcdn-a.akamaihd.net/steam/apps/' + userAppId +'/header_292x136.jpg'
                foundGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                gameList.append(foundGame)
    gameData['games'] = gameList
    return gameData


def determineProperList(game):
    gameRate = 0
    for category in game['categories']:
        if isinstance(category, list):
            pass
        elif category['id'] == 38 or category['id'] == 9:
            if gameRate == 0 or gameRate == 2:
                gameRate += 1
        elif category['id'] == 1 or category['id'] == 36:
            if gameRate == 0 or gameRate == 1:
                gameRate += 2
    return gameRate


# This is for console output

def printSharedGames(gameList):
    games = gameList['games']
    print (bcolors.BOLD + bcolors.OKGREEN \
            + "Here's the Coop games you share:" + bcolors.ENDC)
    for game in games:
        if "coop" in game['multi']:
            print('\t' + game['name'])
    print (bcolors.BOLD + bcolors.OKGREEN \
            + "Here's the Multiplayer games you share:" + bcolors.ENDC)
    for game in games:
        if "multiplayer" in game['multi']:
            print('\t' + game['name'])
    print (bcolors.BOLD + bcolors.OKGREEN \
        + "Here's the Useless games you share:" + bcolors.ENDC)
    for game in games:
        if "singleplayer" in game['multi']:
            print('\t' + game['name'])


def getPlayerData(player):
    r = requests.get(steamPlayerInfoBaseURI
                     + '/ISteamUser/GetPlayerSummaries/v0002/?key='
                     + webKey + '&steamids=' + str(player))
    userDataRaw = json.loads(r.text)
    if userDataRaw['response']['players'] == []:
        return 2
    user = userDataRaw['response']['players'][0]
    player = Player()
    player.name = user['personaname']
    player.steamId = user['steamid']
    player.profileURI = user['profileurl']
    player.avatarURI = user['avatarfull']
    return player


def getUserWishlist(player):
    wishlist=[]
    wishGame = {}
    r = requests.get(steamWishlistBaseURI
                    + str(player.steamId))
    wishlistRaw = re.search(r'(?<=g_rgWishlistData = )[a-zA-Z\[\]\{\}":0-9,]+', r.text)
    wishlist = json.loads(wishlistRaw.group(0))
    #wishlistGameRaw = re.findall(r'{[\a-z:0-9]+}', wishlistRaw[0])
    #for game in wishlistGameRaw:
    #    rawGameId = re.search(r'[0-9][0-9][0-9][0-9][0-9][0-9],', game)
    #    gameId = rawGameId.group(0)
    #    wishGame['appid'] = int(gameId[:-1])
    #    wishGame['wishlist'] = True
    #    wishlist.append(wishGame)
    return wishlist


# APPLICATION ROUTE

@app.errorhandler(404)
def page_not_found(error):
    return ('This page does not exist', 404)

@app.errorhandler(401)
def bad_request(error):
    return ('You did not provide a json payload', 401)

# Check for players, check for complete dataset, return game list or throw.
@app.route('/steamcompare/full', methods=['POST'])
def fullCompare():
    wishlist = False
    gameLists=[]
    master = {}
    master['players'] = []
    master['errors'] = []
    print ('We are starting a full comparison')
    if request.data:
        playerData = request.get_json(force=True)
        if 'wishlist' in playerData:
            wishlist = playerData['wishlist']
        for playerId in playerData['players']:
            errorResponse = {}
            Player = getPlayerData(playerId)
            if isinstance(Player, int):
                continue
            print ('Building the game list for ' + str(Player.name))
            playerList= buildUserGameList(Player, wishlist)
            if playerList == 2:
                print(Player.name + ' is bad!')
                errorResponse[Player.steamId] = Player.name \
                    + ' needs to set their "Game details" to public here: ' \
                    + Player.profileURI + 'edit/settings'
                master['errors'].append(errorResponse)
            elif isinstance(playerList, dict):
                playerList['player'] = playersToDict(Player)
                gameLists.append(playerList)
                master['players'].append(playerList['player'])
        zipped = zipLists(gameLists)
        games = []
        for game in zipped:
            game['multi'] = []
            list = determineProperList(game)
            if list == 1:
                game['multi'].append("coop")
                games.append(game)
            elif list == 2:
                game['multi'].append("multiplayer")
                games.append(game)
            elif list == 3:
                if "multi" not in game['multi']:
                    game['multi'].append("multiplayer")
                if "coop" not in game['multi']:
                    game['multi'].append("coop")
                games.append(game)
            elif list == 0:
                game['multi'].append("singleplayer")
                games.append(game)
            else:
                print ('the value of list was ' + str(list) + '...')
        master['games'] = games

    # print(bcolors.BOLD + bcolors.FAIL + 'Info for Games Shared Between ' + players[0].name + ' & ' + players[1].name + bcolors.ENDC)
        printSharedGames(master)
        return jsonify(master)
    else:
        abort(401)

# Same as /steamcompare/full but doesn't care about local databae or app details
@app.route('/steamcompare/quick', methods=['POST'])
def quickCompare():
    errorResponse = {}
    print('We are starting a quick comparison')
    if request.data:
        players = request.get_json(force=True)
        if players['player1'] == players['player2']:
            return ('you put in the same player twice', 400)
        if len(players) != 2:
            abort(400)
        player1steamId = players['player1']
        player2steamId = players['player2']
        player1 = getPlayerData(player1steamId)
        player2 = getPlayerData(player2steamId)
        print ('1: Building quick game list for ' + str(player1.name))
        playerList1 = buildQuickGameList(int(player1.steamId))
        print ('2: Building quick game list for ' + str(player2.name))
        playerList2 = buildQuickGameList(int(player2.steamId))
        if playerList1 == 2:
            print('Player 1 is bad!')
            errorResponse['player1'] = player1.name \
                + ' needs to set their "Game details" to public here: ' \
                + player1.profileURI + 'edit/settings'
        if playerList2 == 2:
            print('Player 2 is bad!')
            errorResponse['player2'] = player2.name \
                + ' needs to set their "Game details" to public here: ' \
                + player2.profileURI + 'edit/settings'
        if errorResponse != {}:
            return (jsonify(errorResponse), 403)
        zipped = zipLists(playerList1['response']['games'],
                          playerList2['response']['games'])
        master = {}
        master['players'] = []
        for playerId in playerData['players']:
            print (playerid)
            master['players'].append(playersToDict(getPlayerData(playerId)))
        master['games'] = zipped
        return jsonify(master), 200
    else:
        abort(401)

# Takes app id, if error throw, if local database
@app.route('/steamcompare/single', methods=['POST'])
def single():
    errorResponse = {}
    if request.data:
        game = request.get_json(force=True)
        gameResult = lookupSingle(game['appid'])
        if type(gameResult) is int:
            errorResponse = STEAM_APP_ERROR_TYPE[gameResult]
            return (jsonify(errorResponse), 400)
        else:
            return jsonify(gameResult), 200
    else:
        abort(401)

# Lookup a user's data, returning a Player Object
@app.route('/steamcompare/steamidlookup', methods=['POST'])
def userLookup():
    errorResponse = {}
    if request.data:
        if request.data:
            playerData = request.get_json(force=True)
            players = playerData['players']
            master = {}
            for player in players:
                print (player)
                playerID = getUserSteamID(player)
                if type(playerID) is int:
                    master[player] = STEAM_ID_ERROR_TYPE[playerID]
                else:
                    master[player] = playersToDict(getPlayerData(playerID))
            return jsonify(master)

@app.route('/steamcompare/returnWishlist', methods=['POST'])
def returnWishlist():
    errorResponse = {}
    if request.data:
        if request.data:
            playerData = request.get_json(force=True)
            players = playerData['players']
            master = {}
            for player in players:
                playerInfo = getPlayerData(player)
                if type(playerInfo) is int:
                    errorResponse[player] = STEAM_ID_ERROR_TYPE[playerInfo]
                else:
                    master[playerInfo.steamId] = getUserWishlist(playerInfo)
                    if master[playerInfo.steamId] != None:
                        print("Added games")
            if errorResponse != {}:
                return jsonify(errorResponse)
            else:
                return jsonify(master)