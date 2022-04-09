from concurrent.futures import thread
from picamera import PiCamera
from discord.ext import commands
from discord.ext import tasks
import gpiozero

# from picamera import PiCamera
from http.server import BaseHTTPRequestHandler, HTTPServer
import discord, json, random, time, sys, threading, asyncio

with open("template-embed.json") as file:
    embedData = json.load(file)

with open("setting.json") as file:
    setting = json.load(file)

bot = commands.Bot(
    description=setting["global"]["description"],
    command_prefix=setting["global"]["prefix"],
)

camera = PiCamera()
firstConnection = True
event = False


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
    # Camera warm-up time
    camera.capture(name)
    return name


@bot.event
async def on_ready():
    global firstConnection, channel, event
    if firstConnection:
        sys.stdout.write("ok \n")
        channel = bot.get_channel(setting["global"]["channel"])
        print(channel)

        sys.stdout.write(
            "logged in as {} \nat {}\n".format(
                bot.user, time.strftime("%Hh %Mmin %Ssec")
            )
        )
        gpioInit()
        firstConnection = False
        await channel.send(embed=makeEmbed(embedData["start"]))

    else:
        sys.stdout.write(
            "> reconnected at {}\n".format(time.strftime("%Hh %Mmin %Ssec"))
        )
    sys.stdout.write(" - - - event - - - \n")
    return


async def alert_pic():
    """take a picture"""
    global channel
    await channel.send(
        content="alert ! \n a {}".format(time.strftime("%Hh %Mmin %Ssec")),
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
        print('> executed " {} " command in {}'.format(" ".join(arg), ctx.channel))
    else:
        embed.add_field(name="denied access", value="you can't use this command")
    await ctx.send(embed=embed)


# gpio setup
@tasks.loop(seconds=0.5)
async def eventLoop():
    for elem in ils:
        if elem[0].is_pressed != elem[1]:
            await alert_pic()


def gpioInit():
    global ils
    ils = []
    for elem in setting["alarm"]["ils"]:
        ils.append([gpiozero.Button(elem["port"]), elem["close"]])

    eventLoop.start()


with open("token.json") as file:
    shellAccess = json.load(file)["shellAccess"]
    bot.run(json.load(file)["botToken"])