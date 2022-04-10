from concurrent.futures import thread

from pyparsing import CharsNotIn
from picamera import PiCamera
from discord.ext import commands
from discord.ext import tasks
import gpiozero
import shutil
import os

# from picamera import PiCamera
from http.server import BaseHTTPRequestHandler, HTTPServer
import discord, json, random, time, sys, threading, asyncio

with open("template-embed.json") as file:
    embedData = json.load(file)

with open("setting/setting.json") as file:
    setting = json.load(file)

try:
    os.mkdir("capture")
    sys.stdout.write("capture folder created \n")
except:
    pass

bot = commands.Bot(
    description=setting["global"]["description"],
    command_prefix=setting["global"]["prefix"],
)

camera = PiCamera()
firstConnection = True


def makeEmbed(file):
    embed = discord.Embed(
        title=file["title"],
        description=file["description"],
        color=discord.Color.from_rgb(
            file["color"][0],
            file["color"][1],
            file["color"][2],
        ),
    )
    for field in file["fields"]:
        embed.add_field(
            name=field["name"], value=field["value"], inline=field["inline"]
        )
    return embed


# make a capture with picamera
def take_picture():
    name = time.strftime("capture/img %Hh %Mmin %Ssec.jpg")
    camera.capture(name)
    sys.stdout.write(f"> photo enregisté :{name}\n")
    return name


def take_video(recordTime):
    """record a video (only in h264 format because encoding are very slow on rasberry)"""
    name = time.strftime("capture/vid %Hh %Mmin %Ssec.h264")
    camera.start_recording(name)
    camera.wait_recording(recordTime)
    camera.stop_recording()
    sys.stdout.write(f"> video enregisté :{name}\n")
    return name


@bot.event
async def on_ready():
    global firstConnection, channel
    if firstConnection:
        sys.stdout.write("ok \n")
        channel = bot.get_channel(setting["global"]["channel"])

        sys.stdout.write(
            "logged in as {} \nat {}\n".format(
                bot.user, time.strftime("%Hh %Mmin %Ssec")
            )
        )
        gpioInit()
        firstConnection = False
        await channel.send(embed=makeEmbed(embedData["start"]))
        await dailyCheck()

    else:
        sys.stdout.write(
            "> reconnected at {}\n".format(time.strftime("%Hh %Mmin %Ssec"))
        )
    sys.stdout.write(" - - - event - - - \n")
    return


async def alert_pic(name):
    """take a picture"""
    global channel
    sys.stdout.write(f"> capteur {name} active\n")
    await channel.send(
        content='alert !  le capteur "{}" a detecter quelque chose \n a {}'.format(
            name, time.strftime("%Hh %Mmin %Ssec")
        ),
        file=discord.File(take_picture()),
    )


@bot.command()
async def pic(ctx, *arg):
    """manually take a picture"""
    await ctx.send(
        content="image prise a {}".format(time.strftime("%Hh %Mmin %Ssec")),
        file=discord.File(take_picture()),
    )


@bot.command()
async def vid(ctx, *arg):
    """manually take a video (only in h264 because encoding on rasberry are slow) argument: time in second"""
    message = await ctx.send(content="enregistrement en cours...")
    try:
        await ctx.send(file=discord.File(take_video(int(arg[0]))))
        await message.edit(
            content="video prise a {}".format(time.strftime("%Hh %Mmin %Ssec")),
        )
    except:
        await message.edit(content="", embed=makeEmbed(embedData["videoError"]))


@bot.command()
async def shell(ctx, *arg):
    """shell comand for debug"""
    embed = discord.Embed(
        title="Shell command",
        color=discord.Color.red(),
        description=" ".join(arg),
    )

    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
    if ctx.author.id == shellAccess:
        try:
            embed.add_field(name="Result :", value=str(eval(" ".join(arg))))
            embed.color = discord.Color.blue()
        except:
            embed.add_field(name="Error :", value=str(sys.exc_info()))
        sys.stdout.write(
            '> executed " {} " command in {}'.format(" ".join(arg), ctx.channel)
        )
    else:
        embed.add_field(name="denied access", value="you can't use this command")
    await ctx.send(embed=embed)


@bot.command()
async def state(ctx, *arg):
    """show state of all sensors"""
    embed = makeEmbed(embedData["state"])
    states = ""
    for elem in ils:
        states += "{} | {} {} \n".format(
            elem[2],
            "🟩" if elem[0].is_pressed == elem[1] else "🟥",
            "close" if elem[0].is_pressed else "open",
        )
    embed.description = f"```{states}```"
    await ctx.send(embed=embed)


@bot.command()
async def disk(ctx, *arg):
    await checkDisk(ctx.channel)


async def checkDisk(channel, onlyIfLow=False):
    """check disk space"""
    disk = shutil.disk_usage("/")
    if onlyIfLow:
        if disk.free / disk.total > 0.1:
            return
        else:
            sys.stdout.write("> disk space is low\n")
            embed = makeEmbed(embedData["diskLow"])
    else:
        embed = makeEmbed(embedData["disk"])

    embed.description = f"```{disk.total / (1024 * 1024 * 1024):.2f} Go au total\n {disk.used / (1024 * 1024 * 1024):.2f} Go utilise\n {disk.free / (1024 * 1024 * 1024):.2f} Go libre\n {disk.free / disk.total * 100:.2f} % libre``` "
    await channel.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def delete(ctx, day, *arg):
    """delete all capture older than day argument: day in number"""
    await deleteOldCapture(ctx.channel, float(day))


async def deleteOldCapture(channel, day, automatic=False):
    """delete old image"""
    deletes = []
    for file in os.listdir("capture"):
        if file.endswith(".jpg") or file.endswith(".h264"):
            file_path = os.path.join("capture/", file)
            if os.path.isfile(file_path):
                if time.time() - os.path.getmtime(file_path) > day * 24 * 60 * 60:
                    os.remove(file_path)
                    sys.stdout.write(f"> {file_path} deleted\n")
                    deletes.append(file)

    if len(deletes) == 0:
        if automatic:
            return
        else:
            await channel.send(embed=embedData["deleteEmpty"])
    else:
        embed = makeEmbed(embedData["delete"])
        embed.description = "liste des fichier \n  ```{}```".format("\n".join(deletes))
        await channel.send(embed=embed)


# gpio setup
@tasks.loop(seconds=0.5)
async def eventLoop():
    for elem in ils:
        if elem[0].is_pressed != elem[1]:
            await alert_pic(elem[2])


def gpioInit():
    global ils
    ils = []
    for elem in setting["alarm"]["ils"]:
        ils.append([gpiozero.Button(elem["port"]), elem["close"], elem["name"]])

    eventLoop.start()


with open("setting/token.json") as file:
    tokenFile = json.load(file)

# daily check
@tasks.loop(hours=24)
async def dailyCheck():
    await checkDisk(channel, True)
    await deleteOldCapture(channel, setting["global"]["captureTimeout"], True)


sys.stdout.write("loggin to discord...")
shellAccess = tokenFile["shellAccess"]
bot.run(tokenFile["botToken"])
