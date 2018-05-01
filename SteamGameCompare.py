import requests
import json
import time
from mongoengine import *
import datetime
from flask import Flask
from flask import abort, redirect, url_for, request, jsonify

connect()
settings = json.load(open('settings.json'))

webKey = settings['webKey']

app = Flask(__name__)

class Game(Document):
  name = StringField(required=True)
  appid = DecimalField(required=True)
  categories = ListField(required=True)
  date_modified = DateTimeField(default=datetime.datetime.utcnow)

class User(Document):
  name = ListField(required=True)
  steamID = StringField(required=True)

class Player:
  name = None
  avatarURI = None
  profileURI = None
  steamId = None

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'



# basic uri and auth stuff
steamOwnedGamesBaseURI = 'https://api.steampowered.com/'
steamGameInfoBaseURI = 'http://store.steampowered.com/api/'
steamPlayerInfoBaseURI = 'http://api.steampowered.com'

nullCategory = {"id":0,"description":"This Game has No Categories"}

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
    print(player.name)
    dict['name'] = player.name
    dict['avatarURI'] = player.avatarURI
    dict['profileURI'] = player.profileURI
    dict['steamid'] = player.steamId
    playerList.append(dict)
  return playerList


def zipLists(a, b):
  zipped = []
  for game in a:
    if game == {}:
      pass
    else:
      for game2 in b:
        if game == game2:
          zipped.append(game)
        else:
          pass
  return zipped


def buildUserGameList(id, debug=False):
  print("Debug1")
  gameList = []
  userListRaw = requests.get(steamOwnedGamesBaseURI + '/IPlayerService/GetOwnedGames/v1/?key=' +
                            webKey + '&steamId=' + str(id) + '&include_appinfo=1&include_played_free_games=&format=json')
  print("debug2")
  #Use this to tell which game(s) break on a steam library
  #f = open("debug.txt", 'w')
  #f.write(userListRaw.text)
  userListJSON = json.loads(userListRaw.text)
  print("debug3")
  if userListJSON['response'] == {}:
    brokenBoi = getPlayerData(id)
    print(brokenBoi[0].name + " needs to update their profile settings here: https://steamcommunity.com/profiles/" + str(brokenBoi[0].steamid) + "/edit/settings")
    print("They need to set their 'Game Details' to 'Public'")
  else:
    userGames = userListJSON['response']['games']
    totalGames = len(userGames)
    gameCursor = 0
    for game in userGames:
      print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
      gameCursor += 1
      userAppId = str(game['appid'])
      if Game.objects(appid=userAppId):
        gameList.append(gameToDict(Game.objects(appid=userAppId)))
      else:
          r = requests.get(steamGameInfoBaseURI + 'appdetails?appids=' + userAppId)
          gameInfo = json.loads(r.text)
          if r.text == 'null':
            pass
            #print("Game is Null, skipping (" + userAppId + " " + game['name'] + ")")
          elif gameInfo[userAppId]["success"]== False:
            pass
            #print("Game is broken, skipping (" + userAppId + " " + game['name'] + ")")
          else:
            if Game.objects(appid=gameInfo[userAppId]['data']['steam_appid']):
              #print("Multiple Games redirect to this same AppID: " + str(gameInfo[userAppId]['data']['steam_appid']))
              gameList.append(gameToDict(Game.objects(appid=userAppId)))
            else:
              #print("Adding " + gameInfo[userAppId]["data"]['name'] + " to DB (" + userAppId + ")")
              if "categories" in gameInfo[userAppId]["data"]:
                newGame = Game(name=gameInfo[userAppId]["data"]['name'],appid=gameInfo[userAppId]["data"]["steam_appid"],
                               categories=gameInfo[userAppId]["data"]["categories"]).save()
                #print("Added " + gameInfo[userAppId]["data"]['name'] + " to DB")
                gameList.append(gameToDict(Game.objects(appid=userAppId)))
                time.sleep(2)
              else:
                newGame = Game(name=gameInfo[userAppId]["data"]['name'],appid=gameInfo[userAppId]["data"]["steam_appid"],
                               categories=[nullCategory]).save()
                gameList.append(gameToDict(Game.objects(appid=userAppId)))
  return gameList

def determineProperList(game):
  gameRate = 0
  for category in game['categories']:
    if category["id"] == 38 or category["id"] == 9:
      if gameRate == 0 or gameRate == 2:
        gameRate +=1
    elif category["id"] == 1 or category["id"] == 36:
      if gameRate == 0 or gameRate == 1:
        gameRate += 2
  return gameRate

def printSharedGames(coop, multi, useless):
  print(bcolors.BOLD + bcolors.OKGREEN + "Here's the Coop games you share:" + bcolors.ENDC)
  for game in coop:
    print("\t" + game['name'])
  print(bcolors.BOLD + bcolors.OKGREEN + "Here's the Multiplayer games you share:" + bcolors.ENDC)
  for game in multi:
    print("\t" + game['name'])
  print(bcolors.BOLD + bcolors.OKGREEN + "Here's the Useless games you share:" + bcolors.ENDC)
  for game in useless:
    print("\t" + game['name'])

def getPlayerData(player1, player2=None):
  players = []
  if player2 == None:
    r = requests.get(steamPlayerInfoBaseURI + '/ISteamUser/GetPlayerSummaries/v0002/?key=' + webKey + '&steamids=' + str(player1))
    userDataRaw = json.loads(r.text)
    user = userDataRaw['response']['players'][0]
    player = Player()
    player.name = user['personaname']
    player.steamId = user['steamid']
    player.profileURI =user['profileurl']
    player.avatarURI = user['avatarfull']
    players.append(player)
    return players
  elif player2 != None:
    r = requests.get(steamPlayerInfoBaseURI + '/ISteamUser/GetPlayerSummaries/v0002/?key=' + webKey + '&steamids=' + str(player1) + ',' + str(player2))
    userDataRaw = json.loads(r.text)
    for user in userDataRaw['response']['players']:
      player = Player()
      player.name = user['personaname']
      player.steamId = user['steamid']
      player.profileURI =user['profileurl']
      player.avatarURI = user['avatarfull']
      players.append(player)
    return players

@app.errorhandler(404)
def page_not_found(error):
    return 'This page does not exist', 404

@app.errorhandler(400)
def bad_request(error):
    return 'You need to give exactly two users', 400

@app.errorhandler(401)
def bad_request(error):
    return 'You did not provide a json payload', 401

@app.route('/steamcompare/full', methods=['POST'])
def fullCompare():
  print("We are starting a full comparison")
  if request.data:
    players = request.get_json(force=True)
    if len(players) != 2:
      abort(400)
    print(players['player1'])
    print('getting player 1 list')
    playerList1 = buildUserGameList(int(players["player1"]))
    print('getting player 2 list')
    playerList2 = buildUserGameList(int(players["player2"]))
    print('got lists')
    playerData = getPlayerData(players["player1"], players["player2"])
    zipped = zipLists(playerList1, playerList2)
    coop = []
    multi = []
    useless = []
    master = {}
    for game in zipped:
      list = determineProperList(game)
      #print(game['name'] + " has a score of " + str(list))
      if list == 1 or list == 3:
        coop.append(game)
      elif list == 2 or list == 3:
        multi.append(game)
      elif list == 0:
        useless.append(game)
      else:
        print("the value of list was " + str(list) + "...")
    master['players'] = playersToDict(playerData)
    print(playersToDict(playerData))
    master['coop'] = coop
    master['multi'] = multi
    master['useless'] = useless
    return jsonify(master)
  else:
    abort(401)
'''
playerList1 = buildUserGameList(player1)
playerList2 = buildUserGameList(player2)


players = getPlayerData(player1, player2)


zipped = zipLists(playerList1, playerList2)


coop = []
multi = []
useless = []

for game in zipped:
  list = determineProperList(game)
  #print(game['name'] + " has a score of " + str(list))
  if list == 1 or list == 3:
    coop.append(game)
  elif list == 2 or list == 3:
    multi.append(game)
  elif list == 0:
    useless.append(game)
  else:
    print("the value of list was " + str(list) + "...")

print(bcolors.BOLD + bcolors.FAIL + 'Info for Games Shared Between ' + players[0].name + ' & ' + players[1].name + bcolors.ENDC)
printSharedGames(coop, multi, useless)
'''
