import requests
import json
import time
from pymongo import MongoClient
import datetime
from flask import Flask
from flask import abort, redirect, url_for, request, jsonify

client = MongoClient()
db = client.gameData
game = db.game

settings = json.load(open('settings.json'))

webKey = settings['webKey']

app = Flask(__name__)


# Schema for player Object, maybe will add to DB eventually

class Player:

    name = None
    avatarURI = None
    profileURI = None
    steamId = None


# This is for console output and will be eventually removed

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

STEAM_APP_ERROR_TYPE = [{
    'type': 'STEAM_APP_ERROR',
    'error': 'rate_limited',
    'code': 0,
    'message': 'Over 200 detail requests in the last 5 minutes. Wait 5 or more minutes before making any new requests'
        ,
    }, {
    'type': 'STEAM_APP_ERROR',
    'error': 'game_does_not_exist',
    'code': 1,
    'message': 'The game you were requesting information on does not exist. Either the ID is incorrect or it was replaced by another app on Steam.'
        ,
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
steamMediaBaseURI = 'http://media.steampowered.com/steamcommunity/public/images/apps/'

# A filler DB entry for games that have no categories

nullCategory = {'id': 0, 'description': 'This Game has No Categories'}


def gameToDict(game):
    dict = {}
    for boop in game:
        dict['name'] = boop.name
        dict['appid'] = int(boop.appid)
        dict['categories'] = boop.categories
    return dict


def playersToDict(players):
    playerList = []
    for player in players:
        dict = {}
        dict['name'] = player.name
        dict['avatarURI'] = player.avatarURI
        dict['profileURI'] = player.profileURI
        dict['steamid'] = player.steamId
        playerList.append(dict)
    return playerList


def zipLists(a, b):
    result = []
    fullList = a.copy()
    fullList.extend(b)
    for g in fullList:
        if g in a:
            if g in b:
                result.append(g)
    return result


def lookupSingle(gameID):
    gameData = game.find_one({'appid':gameID},{'_id': False})
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



def buildQuickGameList(id):
    '''
    returns dict of gamelist, if access denied throw
    '''
    userListRaw = requests.get(steamOwnedGamesBaseURI
                               + '/IPlayerService/GetOwnedGames/v1/?key='
                                + webKey + '&steamId=' + str(id)
                               + '&include_appinfo=1&include_played_free_games=&format=json'
                               )
    userListJSON = json.loads(userListRaw.text)
    if userListJSON['response'] == {}:
        brokenBoi = getPlayerData(id)
        print (brokenBoi[0].name \
                    + ' needs to update their profile settings here: https://steamcommunity.com/profiles/' \
                    + str(brokenBoi[0].steamId) + '/edit/settings')
        print ("They need to set their 'Game Details' to 'Public'")
        return 2
    return userListJSON


# This is the "Full Compare." Basically it gets the user's owned games, then checks the local DB for it, and grabs details of it doesn't exist in the DB

def buildUserGameList(id, debug=False):
    gameList = []
    userListRaw = requests.get(steamOwnedGamesBaseURI
                                + '/IPlayerService/GetOwnedGames/v1/?key=' \
                                + webKey + '&steamId=' + str(id) \
                                + '&include_appinfo=1&include_played_free_games=1&format=json')

  # Use this to tell which game(s) break on a steam library (SHould no longer be needed, but keeping it just in case)
  # f = open("debug.txt", 'w')
  # f.write(userListRaw.text)

    userListJSON = json.loads(userListRaw.text)

  # This is a check to see if the user has their game visibility set to public, and returns 2 if they are not

    if userListJSON['response'] == {}:
        brokenBoi = getPlayerData(id)
        print (brokenBoi[0].name \
            + ' needs to update their profile settings here: https://steamcommunity.com/profiles/' \
            + str(brokenBoi[0].steamId) + '/edit/settings')
        print("They need to set their 'Game Details' to 'Public'")
        return 2
    else:
        userGames = userListJSON['response']['games']
        totalGames = len(userGames)
        gameCursor = 0
        for g in userGames:

      # This is/was for console output - Mostly because as of writing this, there's no frontend and sending people JSON is not as...parseable
            print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
            gameCursor += 1
            userAppId = str(g['appid'])
            gameStatus = lookupSingle(g['appid'])
            if isinstance(gameStatus, dict):
                gameStatus['thumbnail'] = steamMediaBaseURI + userAppId + '/' + g['img_logo_url'] + '.jpg'
                gameStatus['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                gameList.append(gameStatus)
            elif gameStatus[0] == 0:

        # This is the Rate-limited case
        # Maybe there should be some logic here for waiting.

                pass
            elif gameStatus[0] == 1:

        # This is the success=false case
                game.insert_one({'name':g['name'],
                                'appid':g['appid'],
                                'categories':[nullCategory],
                                'unavailable':True})
                newGame = game.find_one({'appid':int(userAppId)},{'_id': False})
                newGame['thumbnail'] = steamMediaBaseURI + userAppId + '/' + g['img_logo_url'] + '.jpg'
                newGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                gameList.append(newGame)
            elif gameStatus[0] == 2:
                gameDetails = gameStatus[1]

        # This is the case where Multiple games return the game details for the same game
        # This happens with Expansion packs that are no longer for individual sale often.
        # Examples include F.E.A.R. Purseus Mandate/Extraction Point (appid's: 21110/21120)

                if game.find_one({'appid':gameDetails[userAppId]['data']['steam_appid'] }):

          # The game whose details were returned we have info for

                    if not game.find_one({"appid":g['appid']}):

            # We do not have an ID with the game we searched for

                        if 'categories' in gameDetails[userAppId]['data']:
                            game.insert_one({'name':g['name'],
                                            'appid':g['appid'],
                                            'categories':gameDetails[userAppId]['data']['categories'],
                                            'platforms':gameDetails[userAppId]['data']['platforms'],
                                            'is_free':gameDetails[userAppId]['data']['is_free']})
                            newGame = game.find_one({'appid':int(userAppId)},{'_id': False})
                            newGame['thumbnail'] = steamMediaBaseURI + userAppId + '/' + g['img_logo_url'] + '.jpg'
                            newGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                            gameList.append(newGame)
                        else:
                            game.insert_one({'name':g['name'],
                                            'appid':g['appid'],
                                            'categories':[nullCategory],
                                            'platforms':gameDetails[userAppId]['data']['platforms'],
                                            'is_free':gameDetails[userAppId]['data']['is_free']})
                            newGame = game.find_one({'appid':int(userAppId)},{'_id': False})
                            newGame['thumbnail'] = steamMediaBaseURI + userAppId + '/' + g['img_logo_url'] + '.jpg'
                            newGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                            gameList.append(newGame)
                    elif game.find_one({'appid':g['appid']}):
                        newGame = game.find_one({'appid':int(userAppId)},{'_id': False})
                        newGame['thumbnail'] = steamMediaBaseURI + userAppId + '/' + g['img_logo_url'] + '.jpg'
                        newGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                        gameList.append(newGame)
                    else:
                        pass
            elif gameStatus[0] == 3:
                newGameRaw = gameStatus[1]
                newGame = newGameRaw[userAppId]['data']
                newGameInsert = db.game.insert_one({'appid':newGame['steam_appid'],
                                                    'name':newGame['name'],
                                                    'categories':newGame['categories'],
                                                    'platforms':newGame['platforms'],
                                                    'is_free':newGame['is_free']})
                foundGame = game.find_one({'appid':int(userAppId)},{'_id': False})
                foundGame['thumbnail'] = steamMediaBaseURI + userAppId + '/' + g['img_logo_url'] + '.jpg'
                foundGame['steam_url'] = 'http://store.steampowered.com/app/' + userAppId
                gameList.append(foundGame)
    return gameList


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


# This is for console output and will, likely, be removed eventually

def printSharedGames(coop, multi, useless):
    print (bcolors.BOLD + bcolors.OKGREEN \
            + "Here's the Coop games you share:" + bcolors.ENDC)
    for game in coop:
        print('\t' + game['name'])
    print (bcolors.BOLD + bcolors.OKGREEN \
            + "Here's the Multiplayer games you share:" + bcolors.ENDC)
    for game in multi:
        print('\t' + game['name'])
    print (bcolors.BOLD + bcolors.OKGREEN \
        + "Here's the Useless games you share:" + bcolors.ENDC)
    for game in useless:
        print('\t' + game['name'])


def getPlayerData(player):
    r = requests.get(steamPlayerInfoBaseURI
                     + '/ISteamUser/GetPlayerSummaries/v0002/?key='
                     + webKey + '&steamids=' + str(player))
    userDataRaw = json.loads(r.text)
    user = userDataRaw['response']['players'][0]
    player = Player()
    player.name = user['personaname']
    player.steamId = user['steamid']
    player.profileURI = user['profileurl']
    player.avatarURI = user['avatarfull']
    return player

# APPLICATION ROUTE

@app.errorhandler(404)
def page_not_found(error):
    return ('This page does not exist', 404)


@app.errorhandler(400)
def bad_request(error):
    return ('You need to give exactly two users', 400)


@app.errorhandler(401)
def bad_request(error):
    return ('You did not provide a json payload', 401)

# Check for two players, check for complete dataset, return game list or throw.
@app.route('/steamcompare/full', methods=['POST'])
def fullCompare():
    errorResponse = {}
    print ('We are starting a full comparison')
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
        print ('1: Building the game list for ' + str(player1.name))
        playerList1 = buildUserGameList(int(player1.steamId))
        print ('2: Building the game list for ' + str(player2.name))
        playerList2 = buildUserGameList(int(player2.steamId))
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
            return (jsonify(errorResponse), 406)
        zipped = zipLists(playerList1, playerList2)
        coop = []
        multi = []
        useless = []
        master = {}
        for game in zipped:
            list = determineProperList(game)

      # print(game['name'] + " has a score of " + str(list))

            if list == 1 or list == 3:
                coop.append(game)
            elif list == 2 or list == 3:
                multi.append(game)
            elif list == 0:
                useless.append(game)
            else:
                print ('the value of list was ' + str(list) + '...')
        playerData = [player1, player2]
        master['players'] = playersToDict(playerData)
        master['coop'] = coop
        master['multi'] = multi
        master['useless'] = useless

    # print(bcolors.BOLD + bcolors.FAIL + 'Info for Games Shared Between ' + players[0].name + ' & ' + players[1].name + bcolors.ENDC)

        printSharedGames(master['coop'], master['multi'],
                         master['useless'])
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
            return (jsonify(errorResponse), 406)
        zipped = zipLists(playerList1['response']['games'],
                          playerList2['response']['games'])
        master = {}
        playerData = [player1, player2]
        master['players'] = playersToDict(playerData)
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


@app.route('/steamcompare/lookupuser', methods=['POST'])
def lookupUser():
    errorResponse = {}
    if request.data:
        pass
