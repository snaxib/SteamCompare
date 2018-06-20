# SteamCompare

This is a tool to compare two users' steam games with two modes:
1. Quick Compare
  * This uses the results of /GetOwnedGames/ for both users and sees which ones they share
1. Full Compare
  * This grabs detailed information about each game and splits the results into three lists: Coop, Multiplayer, and Useless based on the Categories on the games

Starter mongodump: [DB Dump](https://drive.google.com/file/d/1tRZlh7ORQHN4o4dy9AhlwMckM_PSCoQr/view?usp=sharing)

Dependencies:
* Requests
* PyMongo
* Flask
