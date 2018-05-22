from mongoengine import *
import requests
import json
import datetime
import time


class Game(Document):
  name = StringField(required=True)
  appid = DecimalField(required=True)
  categories = ListField(required=True)
  date_modified = DateTimeField(default=datetime.datetime.utcnow)

settings = json.load(open('settings.json'))

webKey = settings['webKey']
steamOwnedGamesBaseURI = 'https://api.steampowered.com/'
steamGameInfoBaseURI = 'http://store.steampowered.com/api/'
steamPlayerInfoBaseURI = 'http://api.steampowered.com'
nullCategory = [{"id":0,"description":"This Game has No Categories"}]


def gameToDict(game):
  dict = {}
  for boop in game:
    dict['name'] = boop.name
    dict['appid'] = int(boop.appid)
    dict['categories'] = boop.categories
  return dict

connect()

r = requests.get('https://api.steampowered.com/ISteamApps/GetAppList/v2/')
gameRaw = json.loads(r.text)
fullGameList = gameRaw['applist']['apps']

totalGames = len(fullGameList)
iteration = 1
gameCursor = 0
#Use this to tell which game(s) break on a steam library
#f = open("debug.txt", 'w')
#f.write(r.text)

for game in fullGameList:
    print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
    gameCursor += 1
    #print('Working on '+ game['name'] + ' (' + str(iteration) + ' of ' + str(totalGames) + ' ' + str(100*(iteration/totalGames)) + '%)')
    iteration += 1
    userAppId = str(game['appid'])
    if Game.objects(appid=userAppId):
      pass
    else:
        r = requests.get(steamGameInfoBaseURI + 'appdetails?appids=' + userAppId)
        gameInfo = json.loads(r.text)
        if r.text == 'null':
          print("Game is Null, waiting 5 minutes (" + userAppId + " " + game['name'] + ")")
          timer = 0
          while timer < 300:
            timer += 1
            time.sleep(1)
            print(f"{gameCursor/totalGames*100:.1f} % (" + str(300-timer) + " seconds remaining)", end="\r")
          retry = requests.get(steamGameInfoBaseURI + 'appdetails?appids=' + userAppId)
          gameInfoRetry = json.loads(retry.text)
          try:
            attempt = gameInfoRetry[userAppId]
            if gameInfoRetry[userAppId]["success"] == "false":
              newGame = Game(name=game["name"],appid=game["appid"],
                             categories=nullCategory).save()
              print("Added " + game['name'] + " to DB")
              print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
            elif gameInfoRetry[userAppId]["data"]["steam_appid"] != userAppId:
              newGame = Game(name=game["name"],appid=game["appid"],
                             categories=nullCategory).save()
              print("Added " + gameInfo[userAppId]["data"]['name'] + " to DB")
              print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
          except:
            pass
            print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
        elif gameInfo[userAppId]["success"]== False:
          #print("Game is broken, skipping (" + userAppId + " " + game['name'] + ")")
          newGame = Game(name=game["name"],appid=game["appid"],
                             categories=nullCategory).save()
          print("Added " + game['name'] + " to DB")
          print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
          pass
          time.sleep(.75)
        else:
          if Game.objects(appid=gameInfo[userAppId]['data']['steam_appid']):
            #print("Multiple Games redirect to this same AppID: " + str(gameInfo[userAppId]['data']['steam_appid']))
            newGame = Game(name=game["name"],appid=game["appid"],
                             categories=nullCategory).save()
            print("Added " + gameInfo[userAppId]["data"]['name'] + " to DB (Multiple Games redirect to this appid)")
            print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
            time.sleep(.75)
          else:
            print("Adding " + gameInfo[userAppId]["data"]['name'] + " to DB (" + userAppId + ")")
            if "categories" in gameInfo[userAppId]["data"]:
              newGame = Game(name=gameInfo[userAppId]["data"]['name'],appid=gameInfo[userAppId]["data"]["steam_appid"],
                             categories=gameInfo[userAppId]["data"]["categories"]).save()
              print("Added " + gameInfo[userAppId]["data"]['name'] + " to DB")
              time.sleep(.75)
            else:
              newGame = Game(name=gameInfo[userAppId]["data"]['name'],appid=gameInfo[userAppId]["data"]["steam_appid"],
                             categories=[nullCategory]).save()
