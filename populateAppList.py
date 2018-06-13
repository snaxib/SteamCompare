from pymongo import MongoClient
import requests
import json
import datetime
import time


client = MongoClient()
db = client.gameData
game = db.game

settings = json.load(open('settings.json'))

webKey = settings['webKey']
steamOwnedGamesBaseURI = 'https://api.steampowered.com/'
steamGameInfoBaseURI = 'http://store.steampowered.com/api/'
steamPlayerInfoBaseURI = 'http://api.steampowered.com'
nullCategory = [{"id":0,"description":"This Game has No Categories"}]

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
        else:
            return 2, gameJSON


r = requests.get('https://api.steampowered.com/ISteamApps/GetAppList/v2/')
gameRaw = json.loads(r.text)
fullAppList = gameRaw['applist']['apps']

localAppList = game.find({},{'_id':False})
outOfDateApps = []

for gameData in localAppList:
    if 'is_free' in gameData and 'platforms' in gameData: 
        pass
    elif 'unavailable' in gameData:
        pass
    else: 
        outOfDateApps.append(gameData)



totalGames = len(outOfDateApps)
print(totalGames)
gameCursor = 0

for g in outOfDateApps:
    #print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
    gameCursor += 1
    userAppId = str(int(g['appid']))
    gameLookup = lookupSingle(g['appid'])
    if isinstance(gameLookup, tuple):
        gameResult = gameLookup[0]
        gameDetails = gameLookup[1]
        if gameResult == 0:
            print("Game is Null, waiting 5 minutes (" + userAppId + " " + g['name'] + ")")
            timer = 0
            while timer < 300:
                timer += 1
                time.sleep(1)
                print(f"{gameCursor/totalGames*100:.1f} % (" + str(300-timer) + " seconds remaining)", end="\r")
            retry = lookupSingle(userAppId)
            gameInfoRetry = retry[1]
            if retry[0] == 0:
                print(g['name'] + "was not added, double nulled")
                pass
            elif retry[0] == 1:
                game.insert_one({'name':g['name'],
                                'appid':g['appid'],
                                'categories':nullCategory,
                                'unavailable':True})
                print("Added " + g['name'] + " to DB - But game is unavailable to buy")
                time.sleep(.5)
                #print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
            elif retry[0] == 2:
                if 'categories' in gameInfoRetry[userAppId]['data']:
                    game.insert_one({'name':g['name'],
                                    'appid':g['appid'],
                                    'categories':gameInfoRetry[userAppId]['data']['categories'],
                                    'platforms':gameInfoRetry[userAppId]['data']['platforms'],
                                    'is_free':gameInfoRetry[userAppId]['data']['is_free']})
                    print("Added " + g['name'] + " to DB")
                    time.sleep(.5)
                    #print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
                else:
                    game.insert_one({'name':g['name'],
                                    'appid':g['appid'],
                                    'categories': nullCategory,
                                    'platforms':gameInfoRetry[userAppId]['data']['platforms'],
                                    'is_free':gameInfoRetry[userAppId]['data']['is_free']})
                    print("Added " + g['name'] + " to DB")
                    time.sleep(.5)
                    #print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
        elif gameResult == 1:
            game.insert_one({'name':g['name'],
                            'appid':g['appid'],
                            'categories':nullCategory,
                            'unavailable':True})
            print("Added " + g['name'] + " to DB - But game is unavailable to buy")
            time.sleep(.5)
            #print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
        elif gameResult == 2:
            if 'categories' in gameDetails[userAppId]['data']:
                game.insert_one({'name':g['name'],
                                'appid':g['appid'],
                                'categories':gameDetails[userAppId]['data']['categories'],
                                'platforms':gameDetails[userAppId]['data']['platforms'],
                                'is_free':gameDetails[userAppId]['data']['is_free']})
                print("Added " + g['name'] + " to DB")
                time.sleep(.5)
                #print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
            else:
                game.insert_one({'name':g['name'],
                                'appid':g['appid'],
                                'categories': nullCategory,
                                'platforms':gameDetails[userAppId]['data']['platforms'],
                                'is_free':gameDetails[userAppId]['data']['is_free']})
                print("Added " + g['name'] + " to DB")
                time.sleep(.5)
                #print(f"{gameCursor/totalGames*100:.1f} %", end="\r")
    elif isinstance(gameLookup, dict):
        #print(f"{gameCursor/totalGames*100:.1f} % (" + gameLookup['name'] + ")", end="\r")
        r = requests.get(steamGameInfoBaseURI + 'appdetails?appids='
                         + userAppId)
        gameDetails = json.loads(r.text)
        if gameDetails == 'null':
            print("Game is Null, waiting 5 minutes (" + userAppId + " " + g['name'] + ")")
            timer = 0
            while timer < 300:
                timer += 1
                time.sleep(1)
                print(f"{gameCursor/totalGames*100:.1f} % (" + str(300-timer) + " seconds remaining)", end="\r")
        else:
            try:
                if gameDetails[userAppId]['success'] == False:
                    game.replace_one({'appid':gameLookup['appid']},
                                    {'name':gameLookup['name'],
                                    'appid':gameLookup['appid'],
                                    'categories':nullCategory,
                                    'unavailable':True})
                    print('Updated game: '+ gameLookup['name'])
                    time.sleep(.5)
                else:
                    game.replace_one({'appid':gameLookup['appid']},
                                    {'name':gameLookup['name'],
                                    'appid':gameLookup['appid'],
                                    'categories':gameLookup['categories'],
                                    'platforms':gameDetails[userAppId]['data']['platforms'],
                                    'is_free':gameDetails[userAppId]['data']['is_free']})
                    print('Updated game: '+ gameLookup['name'])
                    time.sleep(.5)
            except TypeError:
                print (gameDetails)

