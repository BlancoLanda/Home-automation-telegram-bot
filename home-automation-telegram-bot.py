#!/usr/bin/python3

from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters
from telegram import ParseMode, ReplyKeyboardMarkup, ReplyKeyboardRemove
from phue import Bridge
from rgbxy import Converter
from twisted.internet import task, reactor
from datetime import datetime, timedelta
from time import time
from miio import Vacuum
import requests
import re
import threading
import pytz
import time
import logging
import schedule

# Global vars:
#Por orden: Martín, Ariadna, Mamá, Hernán
allowed_users = [6717226, 13490444, 9399188, 8477915]
sunrise_sunset_dictionary = dict()
timeout = 4  # Poll every 4 seconds
stop_polling = False
SELECT_LIGHT, SELECT_ACTION, SET_VALUE = range(3)
SELECT_ROOM, SELECT_ITERATIONS = range(2)
GO_TO = 0
FAN_SPEED = 0
b = Bridge('bridge_ip_goes_here')
vac = Vacuum("vacuum_ip_goes_here", "vacuum_token_goes_here")
# logging.basicConfig(level=logging.DEBUG)
got_sunrise_data = False
# Variables used to know if a specified call is the first in a time frame.
# (daylight - twilight - nightcall). Used to avoid unnecessary repetitive
# calls.
first_daylight_call = False
first_twilight_call = False
first_night_call = False
# Timers for the bathroom and corridor lights (Will be disabled if timers
# go to 0 without activity)
bathroom_enabled_time = 0
corridor_enabled_time = 0
#Bathroom light turned on flag
bathroom_turned_on = False
# Global bot definition
telegram_bot = None


def get_random_animal_pic(animal):
    """Get a random cat/dog pic (or video)
    from the internet.
    """
    content = ""
    url = ""
    # If animal requested is a cat, send cat pic. If it's a dog, send a dog
    # pic.
    if animal == "/gatete":
        content = requests.get('http://aws.random.cat/meow').json()
        url = content['file']
    else:
        content = requests.get('https://random.dog/woof.json').json()
        url = content['url']
    return url


def send_animal_pic_to_user(update, context):
    """Send the cat/dog pic to the requester.
    """
    image = get_random_animal_pic(update.message.text)
    requester_id = update.message.chat_id
    if requester_id in allowed_users:
        # If content is an image: Send animal's pic
        if (".jpg" in image.lower()) or (".png" in image.lower()) or (".jpeg" in image.lower()):
            context.bot.send_photo(chat_id=requester_id, photo=image)
        # If content is a video: Send animal's video
        else:
            context.bot.send_video(chat_id=requester_id,
                                   video=image, supports_streaming=True)


def home_temperature(update, context):
    """Get the current house's temperature (Hue Sensor)
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        temp = b.get_sensor(2, 'state')['temperature']
        if temp is not None:
            temperature = "*Temperatura*: %s ºC" % (temp / 100)
            context.bot.send_message(chat_id=requester_id, text=temperature.replace(
                ".", ","), parse_mode=ParseMode.MARKDOWN_V2)
        else:
            context.bot.send_message(
                chat_id=requester_id, text="El sensor está apagado, dato de temperatura inaccesible.")


def lights_list(update, context):
    """Get the current lights detected by Hue's bridge.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        text = "*Las bombillas inteligentes de casa son:*\n"
        lights = b.lights
        for light in lights:
            text = "%s \n\- %s" % (text, light.name)
        context.bot.send_message(chat_id=requester_id,
                                 text=text, parse_mode=ParseMode.MARKDOWN_V2)


def turn_all_lights_off(update, context):
    """Turn off all the lights reachable in the house.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        lights = b.lights
        for i, light in enumerate(lights):
            b.set_light(i + 1, 'on', False)


def turn_all_lights_on(update, context):
    """Turn on all the lights reachable in the house.
    """
    if requester_id in allowed_users:
        requester_id = update.message.chat_id
        lights = b.lights
        for i, light in enumerate(lights):
            b.set_light(i + 1, 'on', True)


def modify_bulb_param(update, context):
    """Get a menu with selectable options for each light:
    Turn on/off, change hue/brightness/colors, get info...
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:    
        # Following code: Make the selection list appear always with 2 fixed columns
        # so it looks better in Telegram app.
        lights = b.lights
        lights_list = []
        current_row = []
        ind = 0
        for i, light in enumerate(lights):
            current_row.append("%s: %s" % (i + 1, light.name))
            if ind == 1:
                lights_list.append(current_row)
                current_row = []
                ind = 0
            else:
                ind = ind + 1

        reply_markup = ReplyKeyboardMarkup(
            lights_list, one_time_keyboard=True, resize_keyboard=True)
        context.bot.send_message(
            chat_id=requester_id, text="Elegí una bombilla:", reply_markup=reply_markup)

        return SELECT_LIGHT

    else:
        return ConversationHandler.END


def start(update, context):
    """Welcome message from the bot to the user.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        context.bot.send_message(chat_id=requester_id, text="Hola\! Consultá la lista de comandos disponibles y animate a interactuar conmigo:\n\n*ASPIRADORA*\n\n/aspirar\_habitacion \- Aspirar una habitación \(puerta ABIERTA\) y volver a la base\n/aspiradora\_ir\_habitacion \- Llevar la aspiradora a una habitación\n/aspirar\_spot\_puerta\_cerrada \- Aspirar una habitación \(puerta CERRADA\) sin volver a la base\n/aspiradora\_base\_carga \- Llevar la aspiradora a la base de carga\n/aspiradora\_pausar \- Pausar aspiradora\n/aspiradora\_continuar\_zona \- Continuar limpieza de zona tras pausa\n/aspiradora\_potencia \- Obtener valor de potencia de aspiradora \(%\)\n/aspiradora\_establecer\_potencia \- Establecer valor de potencia de aspiradora \(%\)\n\n*LUCES Y SENSORES:*\n\n/alternar\_sensor\_pasillo \- Alternar sensor presencia y luz en pasillo\n/modificar\_luces \- Interactuá con las luces de la casa\n/encender\_luces \- Encendé todas las luces\n/apagar\_luces \- Apagá todas las luces\n/luces \- Recibí una lista de las bombillas inteligentes registradas\n/temperatura \- Recibí el valor de temperatura en el pasillo\n/luminancia \- Recibí el valor de luminancia en el pasillo\n\n*EXTRAS:*\n\n/cafe\_mama \- Solicitá un café a Martín con un aviso lumínico\n/informacion\_solar \- Recibí información solar de esta ubicación\n/perrete \- Recibí la foto de un lindo y feliz perrete\!\n/gatete \- Recibí la foto de un precioso y apuesto gatete\!\n\n*OTROS:*\n\n/cancel \- Cancelá la acción en curso\n/comandos \- Recibir esta lista de comandos", parse_mode=ParseMode.MARKDOWN_V2)


def cancel(update, context):
    """Cancel current command or a whole conversation flow.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        context.bot.send_message(
            chat_id=requester_id, text="Acción cancelada.", reply_markup=ReplyKeyboardRemove())


def error(update, context):
    """Log errors caused by updates..
    """
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def select_light(update, context):
    """Select a bulb to operate with.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        light_selected = update.message.text
        light_id = light_selected.split(":")[0]
        light_name = light_selected.split(": ")[1]

        context.user_data["light_id"] = light_id
        context.user_data["light_name"] = light_name

        action_list = [['Alternar encendido', 'Cambiar brillo'],
                       ['Cambiar saturación', 'Cambiar tono'],
                       ['Cambiar color HEX', 'Establecer color aleatorio'],
                       ['Ver parámetros actuales', 'Alternar loop de colores']]

        reply_markup = ReplyKeyboardMarkup(
            action_list, one_time_keyboard=True, resize_keyboard=True)
        context.bot.send_message(chat_id=requester_id, text="Seleccionaste '%s'. Elegí una acción:" % (
            light_selected.split(": ")[1]), reply_markup=reply_markup)

        return SELECT_ACTION
    else:
        return ConversationHandler.END


def select_action(update, context):
    """Choose an action for the selected bulb.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        selected_action = update.message.text
        return_value = ConversationHandler.END

        if selected_action == "Alternar encendido":
            context.user_data["action"] = "alternar_encendido"
            return_value = switch_light_state(update, context)
        elif selected_action == "Cambiar brillo":
            context.user_data["action"] = "cambiar_brillo"
            return_value = change_brightness(update, context)
        elif selected_action == "Cambiar saturación":
            context.user_data["action"] = "cambiar_saturacion"
            return_value = change_saturation(update, context)
        elif selected_action == "Cambiar tono":
            context.user_data["action"] = "cambiar_tono"
            return_value = change_hue(update, context)
        elif selected_action == "Cambiar color HEX":
            context.user_data["action"] = "cambiar_color_HEX"
            return_value = change_hex_color(update, context)
        elif selected_action == "Establecer color aleatorio":
            context.user_data["action"] = "color_aleatorio"
            return_value = random_color(update, context)
        elif selected_action == "Ver parámetros actuales":
            context.user_data["action"] = "comprobar_parametros"
            return_value = get_bulb_parameters(update, context)
        elif selected_action == "Alternar loop de colores":
            context.user_data["action"] = "alternar_colorloop"
            return_value = switch_colorloop(update, context)

        return return_value
    else:
        return ConversationHandler.END


def switch_light_state(update, context):
    """Turn on/off the selected bulb.
    """

    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]

    if b.get_light(light_id, 'reachable') == True:

        current_state = b.get_light(light_id, 'on')
        action = ""
        if current_state == True:
            b.set_light(light_id, 'on', False)
            action = "apagar"
        else:
            b.set_light(light_id, 'on', True)
            action = "encender"

        context.bot.send_message(chat_id=requester_id, text="Perfecto! Acabás de %s la luz '%s'" % (
            action, light_name), reply_markup=ReplyKeyboardRemove())

    else:
        context.bot.send_message(chat_id=requester_id, text="Lamentablemente la luz %s es inalcanzable. Probá a conectarla o encenderla físicamente." % (
            light_name), reply_markup=ReplyKeyboardRemove())

    # Empty cache as action is done.
    context.user_data["light_id"] = ""
    context.user_data["light_name"] = ""
    context.user_data["action"] = ""
    # End of conversation flow (ConversationHandler)
    return ConversationHandler.END


def change_brightness(update, context):
    """Change the brightness value of the selected bulb.
    """
    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]

    if b.get_light(light_id, 'reachable') == True:

        current_brightness = b.get_light(light_id, 'bri')
        context.bot.send_message(chat_id=requester_id, text="Brillo actual de %s: %s. Introducí a continuación un valor numérico del 1 (Mínimo) al 254 (Máximo):" % (
            light_name, current_brightness),  reply_markup=ReplyKeyboardRemove())

        return SET_VALUE

    else:
        context.bot.send_message(chat_id=requester_id, text="Lamentablemente la luz %s es inalcanzable. Probá a conectarla o encenderla físicamente." % (
            light_name), reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END


def change_saturation(update, context):
    """Change the saturation value of the selected bulb.
    """
    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]

    if b.get_light(light_id, 'reachable') == True:

        current_saturation = b.get_light(light_id, 'sat')
        context.bot.send_message(chat_id=requester_id, text="Saturación actual de %s: %s. Introducí a continuación un valor numérico del 0 (Mínimo: Menos saturado/blanco) al 254 (Máximo: Más saturado/colorido):" %
                                 (light_name, current_saturation),  reply_markup=ReplyKeyboardRemove())

        return SET_VALUE

    else:
        context.bot.send_message(chat_id=requester_id, text="Lamentablemente la luz %s es inalcanzable. Probá a conectarla o encenderla físicamente." % (
            light_name), reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END


def change_hex_color(update, context):
    """Change the color of the selected bulb given a hexadecimal color string.
    """
    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]

    if b.get_light(light_id, 'reachable') == True:

        context.bot.send_message(
            chat_id=requester_id, text="Introducí a continuación un valor hexadecimal. Ejemplo: #385A80:\n\nSelector de colores HEX: https://www.google.com/search?q=hex+color+picker", reply_markup=ReplyKeyboardRemove())

        return SET_VALUE

    else:
        context.bot.send_message(chat_id=requester_id, text="Lamentablemente la luz %s es inalcanzable. Probá a conectarla o encenderla físicamente." % (
            light_name), reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END

def change_hue(update, context):
    """Change the hue value of the selected bulb.
    """
    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]

    if b.get_light(light_id, 'reachable') == True:

        current_hue = b.get_light(light_id, 'hue')
        context.bot.send_message(chat_id=requester_id, text="Tono actual de %s: %s. Introducí a continuación un valor numérico del 0 al 65535:\n\nNota: 0 y 65535 = Tonos rojos. 21845 = Tonos verdes. 43690 = Tonos azules." % (
            light_name, current_hue), reply_markup=ReplyKeyboardRemove())

        return SET_VALUE

    else:
        context.bot.send_message(chat_id=requester_id, text="Lamentablemente la luz %s es inalcanzable. Probá a conectarla o encenderla físicamente." % (
            light_name), reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END


def switch_colorloop(update, context):
    """Turn on/off the looping color effect for the selected bulb.
    """
    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]

    if b.get_light(light_id, 'reachable') == True:

        effect = b.get_light(light_id, 'effect')
        action = ""
        if effect:
            if effect == 'none':
                # Set the saturation to the max value, because if the value is low,
                # the colorloop will not be noticed (always white).
                b.set_light(light_id, 'on', True)
                b.set_light(light_id, 'sat', 254)
                b.set_light(light_id, 'effect', 'colorloop')
                action = "activado"
            else:
                b.set_light(light_id, 'effect', 'none')
                action = "desactivado"
            context.bot.send_message(chat_id=requester_id, text="Perfecto! Efecto de loop de colores %s en %s " % (
                action, light_name), reply_markup=ReplyKeyboardRemove())
        else:
            context.bot.send_message(chat_id=requester_id, text="I'm sorry bro. %s no soporta el efecto de loop de colores." % (
                light_name), reply_markup=ReplyKeyboardRemove())
        return SET_VALUE

    else:
        context.bot.send_message(chat_id=requester_id, text="Lamentablemente la luz %s es inalcanzable. Probá a conectarla o encenderla físicamente." % (
            light_name), reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END


def random_color(update, context):
    """Set a random color for the selected bulb.
    """
    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]

    if b.get_light(light_id, 'reachable') == True:

        converter = Converter()
        xy = converter.get_random_xy_color()
        b.set_light(light_id, 'on', True)
        b.set_light(light_id, 'xy', xy)
        current_bri_scale_1 = b.get_light(light_id, 'bri') / 254
        hex_value = converter.xy_to_hex(xy[0], xy[1], current_bri_scale_1)
        context.bot.send_message(chat_id=requester_id, text="Hecho! El color (formato Hexadecimal) seleccionado aleatoriamente para '%s' fue #%s" % (
            light_name, hex_value), reply_markup=ReplyKeyboardRemove())

    else:
        context.bot.send_message(chat_id=requester_id, text="Lamentablemente la luz %s es inalcanzable. Probá a conectarla o encenderla físicamente." % (
            light_name), reply_markup=ReplyKeyboardRemove())

    # Empty cache as action is done.
    context.user_data["light_id"] = ""
    context.user_data["light_name"] = ""
    context.user_data["action"] = ""
    # End of conversation flow (ConversationHandler)
    return ConversationHandler.END


def get_bulb_parameters(update, context):
    """Get the parameters of the selected bulb.
    """
    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]
    reachable = b.get_light(light_id, 'reachable')
    if reachable == False:
        context.bot.send_message(chat_id=requester_id, text="Parámetros actuales de '%s' (ID %s):\n\nAlcanzable: False" % (
            light_name, light_id), reply_markup=ReplyKeyboardRemove())
    else:
        on = b.get_light(light_id, 'on')
        bri = b.get_light(light_id, 'bri')
        hue = b.get_light(light_id, 'hue')
        sat = b.get_light(light_id, 'sat')
        effect = b.get_light(light_id, 'effect')
        xy = b.get_light(light_id, 'xy')
        bri_scale_1 = bri / 254
        converter = Converter()
        hexvalue = converter.xy_to_hex(xy[0], xy[1], bri_scale_1)
        ct = b.get_light(light_id, 'ct')
        colormode = b.get_light(light_id, 'colormode')
        mode = b.get_light(light_id, 'mode')
        text = "Parámetros actuales de '%s' (ID %s):\n\nAlcanzable: %s\nEncendida: %s\nBrillo: %s\nTono: %s\nSaturación: %s\nEfecto: %s\nx: %s\ny: %s\nColor (Hexadecimal): #%s\nTemperatura de color (Mired): %s\nModo de color: %s\nModo: %s" % (
            light_name, str(light_id), str(reachable), str(on), str(bri), str(hue), str(sat), effect, str(xy[0]), str(xy[1]), hexvalue, str(ct), colormode, mode)
        context.bot.send_message(
            chat_id=requester_id, text=text, reply_markup=ReplyKeyboardRemove())

    # Empty cache as action is done.
    context.user_data["light_id"] = ""
    context.user_data["light_name"] = ""
    context.user_data["action"] = ""
    # End of conversation flow (ConversationHandler)
    return ConversationHandler.END


def process_action(update, context):
    """Process the selected action for the selected bulb.
    """
    requester_id = update.message.chat_id
    light_id = int(context.user_data["light_id"])
    light_name = context.user_data["light_name"]
    action = context.user_data["action"]

    if action == "cambiar_brillo":

        input_value = update.message.text
        if not input_value.isdigit():
            context.bot.send_message(
                chat_id=requester_id, text="El valor introducido no es un número. Introducilo de nuevo.")
            return SET_VALUE
        elif int(input_value) < 1 or int(input_value) > 254:
            context.bot.send_message(
                chat_id=requester_id, text="El valor introducido no está en el rango de valores de brillo. Introducilo de nuevo.")
            return SET_VALUE
        else:
            b.set_light(light_id, 'on', True)
            b.set_light(light_id, 'bri', int(input_value))
            context.bot.send_message(chat_id=requester_id, text="Perfecto! Brillo de '%s' establecido a %s." % (
                light_name, input_value))

    if action == "cambiar_saturacion":

        input_value = update.message.text
        if not input_value.isdigit():
            context.bot.send_message(
                chat_id=requester_id, text="El valor introducido no es un número. Introducilo de nuevo.")
            return SET_VALUE
        elif int(input_value) < 0 or int(input_value) > 254:
            context.bot.send_message(
                chat_id=requester_id, text="El valor introducido no está en el rango de valores de saturación. Introducilo de nuevo.")
            return SET_VALUE
        else:
            b.set_light(light_id, 'on', True)
            b.set_light(light_id, 'sat', int(input_value))
            context.bot.send_message(chat_id=requester_id, text="Perfecto! Saturación de '%s' establecida a %s." % (
                light_name, input_value))

    if action == "cambiar_color_HEX":

        pattern = re.compile('^(#\w{6}|\w{6})$')

        input_value = update.message.text
        if not pattern.match(input_value):
            context.bot.send_message(
                chat_id=requester_id, text="El valor introducido no es un valor hexadecimal de 6 caracteres. Introducilo de nuevo.")
            return SET_VALUE
        else:
            input_value = input_value.replace("#", "")
            converter = Converter()
            xy = converter.hex_to_xy(input_value)
            b.set_light(light_id, 'on', True)
            b.set_light(light_id, 'xy', xy)
            context.bot.send_message(chat_id=requester_id, text="Perfecto! Tono de '%s' establecido a #%s." % (
                light_name, input_value))

    if action == "cambiar_tono":

        input_value = update.message.text
        if not input_value.isdigit():
            context.bot.send_message(
                chat_id=requester_id, text="El valor introducido no es un número. Introducilo de nuevo.")
            return SET_VALUE
        elif int(input_value) < 0 or int(input_value) > 65535:
            context.bot.send_message(
                chat_id=requester_id, text="El valor introducido no está en el rango de valores de saturación. Introducilo de nuevo.")
            return SET_VALUE
        else:
            b.set_light(light_id, 'on', True)
            b.set_light(light_id, 'hue', int(input_value))
            context.bot.send_message(chat_id=requester_id, text="Perfecto! Tono de '%s' establecido a %s." % (
                light_name, input_value))

    # Empty cache as action is done.
    context.user_data["light_id"] = ""
    context.user_data["light_name"] = ""
    context.user_data["action"] = ""
    # End of conversation flow (ConversationHandler)
    return ConversationHandler.END


def request_coffee(update, context):
    """Sequence to send a light alert to my desktop bulb when
    my mother is lazy and wants to drink a cup of coffee :)
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:

        # My desktop's bulb ID
        light_id = 3

        if b.get_light(light_id, 'reachable') == True:

            # Get the previous color
            converter = Converter()
            xy = b.get_light(light_id, 'xy')
            current_brightness_scale_1 = b.get_light(light_id, 'bri') / 254
            hex_value = converter.xy_to_hex(
                xy[0], xy[1], current_brightness_scale_1)
            on = b.get_light(light_id, 'on')
            context.bot_data["coffee_previous_hex_value"] = hex_value
            context.bot_data["coffee_previous_on"] = str(on)
            context.bot_data["coffee_requester_id"] = requester_id

            # Set the new color (strong red)
            xy = converter.hex_to_xy('7C0A02')
            if on == False:
                b.set_light(light_id, 'on', True)
            b.set_light(light_id, 'xy', xy)

            context.bot.send_message(
                chat_id=requester_id, text="Acabás de solicitarle un café a Martín encendiendo su lámpara de mesa con el color rojo.\n\nVas a recibir otro mensaje cuando acepte la petición.")
            context.bot.send_message(
                chat_id='6717226', text="Solicitud de café recibida. Pulsa en /ok_cafe para aceptarla.")
        else:

            context.bot.send_message(
                chat_id=requester_id, text="Lamentablemente la luz %s es inalcanzable. Imposible solicitarle café con su lámpara." % (light_name))


def ok_cafe(update, context):
    """I accept my mother's coffee petitions so she knows it's on the way.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        # Id escritorio Martín
        light_id = 3

        # Get previous data
        coffee_previous_hex_value = context.bot_data["coffee_previous_hex_value"]
        coffee_previous_on = context.bot_data["coffee_previous_on"]
        previous_on_bool = True if coffee_previous_on.lower() == 'true' else False
        coffee_requester_id = context.bot_data["coffee_requester_id"]

        # Send confirmation
        context.bot.send_message(chat_id=coffee_requester_id,
                                 text="Martín acaba de aceptar tu petición de café, en menos de un minuto lo tenés!")
        context.bot.send_message(chat_id=requester_id,
                                 text="Gracias por confirmar la petición de café")
        # Recover previous data
        converter = Converter()
        xy = converter.hex_to_xy(coffee_previous_hex_value)
        b.set_light(light_id, 'xy', xy)
        b.set_light(light_id, 'on', previous_on_bool)

        # Empty cache as action is done.
        context.bot_data["coffee_previous_hex_value"] = ""
        context.bot_data["coffee_previous_on"] = ""
        context.bot_data["coffee_requester_id"] = ""


def home_luminance(update, context):
    """Get the current house's luminance (Hue Sensor)
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:

        lightlevel = b.get_sensor(4, 'state')['lightlevel']
        lux = round(10**((lightlevel - 1) / 10000))
        if not lux == None:
            context.bot.send_message(chat_id=requester_id, text="*Nivel de luz:*\n\n%s \(%s lux\)" %
                                     (lightlevel, lux), parse_mode=ParseMode.MARKDOWN_V2)
        else:
            context.bot.send_message(
                chat_id=requester_id, text="El sensor está apagado, dato de luminancia inaccesible.")


def switch_sensor_routine(update, context):
    """Turn on/off the corridor and bathroom automated sensor routine
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:

        global stop_polling
        action = ""
        if stop_polling == False:
            stop_polling = True
            action = "Desactivada"
        else:
            stop_polling = False
            action = "Activada"
        context.bot.send_message(
            chat_id=requester_id, text="%s la rutina de sensor de presencia y luminancia en el pasillo.\nSi querés entender como funciona, pulsá en /explicacion" % (action))


def time_in_range(start, end, x):
    """Return true if x is in the range [start, end]"""
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end


def get_current_time():
    """Get the current time.
    """
    now = datetime.now()
    tz = pytz.timezone('Europe/Madrid')
    dt = datetime.now(tz).strftime("%H:%M:%S")
    dt = (datetime.strptime(dt, '%H:%M:%S')).time()
    return dt


def get_current_sunlight_state():
    """Get the current state based on the sun (Daylight, Twilight or night)
    """

    now = get_current_time()
    sunrise_time = sunrise_sunset_dictionary['sunrise_time']
    sunset_time = sunrise_sunset_dictionary['sunset_time']
    civil_twilight_begin_time = sunrise_sunset_dictionary[
        'civil_twilight_begin_time']
    civil_twilight_end_time = sunrise_sunset_dictionary[
        'civil_twilight_end_time']
    nautical_twilight_begin_time = sunrise_sunset_dictionary[
        'nautical_twilight_begin_time']
    nautical_twilight_end_time = sunrise_sunset_dictionary[
        'nautical_twilight_end_time']
    astronomical_twilight_begin_time = sunrise_sunset_dictionary[
        'astronomical_twilight_begin_time']
    night_time = sunrise_sunset_dictionary['night_time']

    if time_in_range(sunrise_time, sunset_time, now) == True:
        return "daylight"
    elif time_in_range(sunset_time, night_time, now) == True:
        return "twilight"
    elif time_in_range(night_time, sunrise_time, now) == True:
        return "night"

def get_sunlight_state(update,context):
    state = get_current_sunlight_state()
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        context.bot.send_message(chat_id=requester_id, text=state)    

def sensor_routine_behaviour():
    """Logic of the behaviour for the corridor and bathroom
    when presence is detected with the motion sensor.
    """

    # If still there's no sunlight data, wait. Another thread is getting them.
    while got_sunrise_data == False:
        pass
    current_sunlight_state = get_current_sunlight_state()
    on = is_on(2)
    detected_movement = is_movement_detected()
    global corridor_enabled_time
    global bathroom_enabled_time
    global bathroom_turned_on

    if detected_movement == True:
        if on == False:
            global first_daylight_call
            global first_twilight_call
            global first_night_call
            b.set_light(2, 'on', True)
            corridor_enabled_time = time.time()
            # If daylight: set light white and max brightness.
            if current_sunlight_state == 'daylight' and first_daylight_call == False:
                first_daylight_call = True
                # Turn off bathroom light, max brightness and then turn it off.
                b.set_light(4, 'on', True)
                b.set_light(4, 'bri', 254)
                b.set_light(4, 'on', False)
                # Set max brightness with white color.
                b.set_light(2, 'on', True)
                b.set_light(2, 'xy', [0.31352, 0.32979])
                b.set_light(2, 'bri', 254)
                first_night_call = False
            if current_sunlight_state == 'twilight' and first_twilight_call == False:
                first_twilight_call = True
                b.set_light(2, 'xy', [0.45186, 0.40863])
                b.set_light(2, 'bri', 254)
                first_daylight_call = False
            if current_sunlight_state == 'night':
                if first_night_call == False:
                    first_night_call = True
                    b.set_light(2, 'xy', [0.50562, 0.41521])
                    b.set_light(2, 'bri', 254)
                    b.set_light(4, 'on', True)
                    b.set_light(4, 'bri', 25)
                    first_twilight_call = False
                # Turn on bathroom light.
                b.set_light(4, 'on', True)
                bathroom_turned_on = True
                bathroom_enabled_time = time.time()
        # If on, reset timers.
        else:
            corridor_enabled_time = time.time()
            if current_sunlight_state == 'night':
                bathroom_enabled_time = time.time()
    # If no movement...
    else:
        time_since_last_corridor_enabled_time = int(
            time.time() - corridor_enabled_time)
        time_since_last_bathroom_enabled_time = int(
            time.time() - bathroom_enabled_time)
        if on == True and time_since_last_corridor_enabled_time > 30:
            b.set_light(2, 'on', False)
        if current_sunlight_state == 'night':
            if bathroom_turned_on == True and time_since_last_bathroom_enabled_time > 300:
                b.set_light(4, 'on', False)
                bathroom_turned_on = False


def is_on(id):
    """Check if the input bulb is on.
    """
    try:
        on = b.get_light(id, 'on')
    except:
        # In rare cases, the bridge is unable to get the state. In this
        # exceptional case, bulb is considered turned off.
        on = False
    return on


def is_movement_detected():
    """Check if sensor detected presence.
    """
    try:
        presence = b.get_sensor(3, 'state')['presence']
    except:
        # In rare cases, the bridge is unable to get the state. In this
        # exceptional case, presence is considered not detected.
        presence = False
    return presence


def sensor_routine_do_work():
    """Work of the sensor routine thread.
    """
    global stop_polling
    if stop_polling == False:
        sensor_routine_behaviour()
    else:
        pass


def sensor_routine_twisted():
    """Twisted sensour routine initialization (each 3 seconds).
    """
    l = task.LoopingCall(sensor_routine_do_work)
    l.start(timeout)  # call every 3 seconds
    reactor.run(installSignalHandlers=0)


def get_sunrise_sunset_data():
    """Get daylight data from Sunrise-Sunset API.
    """
    now = datetime.now()
    f = requests.get(
        'http://api.sunrise-sunset.org/json?lat=42.2248695&lng=-8.7267509&formatted=0&date=%s-%s-%s' % (now.year, now.month, now.day))
    data = f.text
    sunrise = data[34:42]
    sunset = data[71:79]
    solar_noon = data[112:120]
    civil_twilight_begin = data[182:190]
    civil_twilight_end = data[231:239]
    nautical_twilight_begin = data[285:293]
    nautical_twilight_end = data[337:345]
    astronomical_twilight_begin = data[395:403]
    astronomical_twilight_end = data[451:459]
    night = astronomical_twilight_end
    offset = 1
    # Check if right now we have UTC+1 or UTC+2
    dst = is_dst(timezone="Europe/Madrid")
    if (dst == True):
        offset = 2
    sunrise_time = (datetime.strptime(sunrise, '%H:%M:%S') +
                    timedelta(hours=offset)).time()
    sunset_time = (datetime.strptime(sunset, '%H:%M:%S') +
                   timedelta(hours=offset)).time()
    solar_noon_time = (datetime.strptime(
        solar_noon, '%H:%M:%S') + timedelta(hours=offset)).time()
    civil_twilight_begin_time = (datetime.strptime(
        civil_twilight_begin, '%H:%M:%S') + timedelta(hours=offset)).time()
    civil_twilight_end_time = (datetime.strptime(
        civil_twilight_end, '%H:%M:%S') + timedelta(hours=offset)).time()
    nautical_twilight_begin_time = (datetime.strptime(
        nautical_twilight_begin, '%H:%M:%S') + timedelta(hours=offset)).time()
    nautical_twilight_end_time = (datetime.strptime(
        nautical_twilight_end, '%H:%M:%S') + timedelta(hours=offset)).time()
    astronomical_twilight_begin_time = (datetime.strptime(
        astronomical_twilight_begin, '%H:%M:%S') + timedelta(hours=offset)).time()
    night_time = (datetime.strptime(night, '%H:%M:%S') +
                  timedelta(hours=offset)).time()

    global sunrise_sunset_dictionary
    sunrise_sunset_dictionary['sunrise_time'] = sunrise_time
    sunrise_sunset_dictionary['sunset_time'] = sunset_time
    sunrise_sunset_dictionary['solar_noon_time'] = solar_noon_time
    sunrise_sunset_dictionary[
        'civil_twilight_begin_time'] = civil_twilight_begin_time
    sunrise_sunset_dictionary[
        'civil_twilight_end_time'] = civil_twilight_end_time
    sunrise_sunset_dictionary[
        'nautical_twilight_begin_time'] = nautical_twilight_begin_time
    sunrise_sunset_dictionary[
        'nautical_twilight_end_time'] = nautical_twilight_end_time
    sunrise_sunset_dictionary[
        'astronomical_twilight_begin_time'] = astronomical_twilight_begin_time
    sunrise_sunset_dictionary['night_time'] = night_time

    global got_sunrise_data
    got_sunrise_data = True


def get_sunrise_sunset_data_sch():
    """Daylight information obtainment schedule (once a day at 00:00:00).
    """
    schedule.every().day.at("00:05").do(get_sunrise_sunset_data)
    while True:
        schedule.run_pending()
        time.sleep(1)


def is_dst(dt=None, timezone="UTC"):
    """Check if, right now, this timezone has daylight savings or not.
    """
    if dt is None:
        dt = datetime.utcnow()
    timezone = pytz.timezone(timezone)
    timezone_aware_date = timezone.localize(dt, is_dst=None)
    return timezone_aware_date.tzinfo._dst.seconds != 0


def explanation(update, context):
    """Shows explanation of the sensor routine to the user.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        context.bot.send_message(chat_id=requester_id, text="Durante el día, la luz del pasillo se enciende si la intensidad lumínica es baja y se detecta presencia, con una temperatura de color de 6500K.\nDurante el crepúsculo, igual con una temperatura de 2800K.\nDe noche, igual con una temperatura de 2200K.\n\nLa idea es que las temperaturas de cada franja horaria coincidan aproximadamente con las del horario solar.")


def solar_information(update, context):
    """Get updated sunlight information for my region.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        sunrise_time = sunrise_sunset_dictionary['sunrise_time']
        solar_noon_time = sunrise_sunset_dictionary['solar_noon_time']
        sunset_time = sunrise_sunset_dictionary['sunset_time']
        night_time = sunrise_sunset_dictionary['night_time']

        text = "*INFORMACIÓN SOLAR DE HOY*\n\n*Amanecer:* %s\n*Mediodía solar:* %s\n*Puesta de sol:* %s\n*Noche:* %s" % (
            sunrise_time, solar_noon_time, sunset_time, night_time)
        context.bot.send_message(chat_id=requester_id,
                                 text=text, parse_mode=ParseMode.MARKDOWN_V2)

def vacuum_zone(update,context):
    """Start vacuum cleaning (Xiaomi Mi Vacuum V1) in a specific zone of the house:
    Bedrooms, bathroom, toilet, living room, kitchen...
    """
    requester_id = update.message.chat_id
    if requester_id in allowed_users:
        rooms_list = [["1: Hab. Azul", "2: Hab. Hernán"], ["3: Hab. Martín", "4: Hab. Mamá"], ["5: Cocina", "6: Baño pequeño"], ["7: Baño grande", "8: Living"], ["9: Pasillo"]]

        reply_markup = ReplyKeyboardMarkup(
            rooms_list, one_time_keyboard=True, resize_keyboard=True)
        context.bot.send_message(
            chat_id=requester_id, text="Elegí una habitación:", reply_markup=reply_markup)

        return SELECT_ROOM
    else:
        return ConversationHandler.END

def select_room(update,context):
    """Gets the selected room and asks for the number of vacuum cleaning iterations.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        room_selected = update.message.text
        room_id = room_selected.split(":")[0]
        room_name = room_selected.split(": ")[1]

        context.user_data["room_id"] = room_id
        context.user_data["room_name"] = room_name

        iteration_list = [['1', '2'],
                       ['3', '4']]

        reply_markup = ReplyKeyboardMarkup(
            iteration_list, one_time_keyboard=True, resize_keyboard=True)
        context.bot.send_message(chat_id=requester_id, text="Seleccionaste '%s'. Elegí cuantas veces querés que se aspire:" % (
            room_name), reply_markup=reply_markup)

        return SELECT_ITERATIONS
    else:
        return ConversationHandler.END

def select_iterations(update,context):
    """Gets the selected iterations and starts the vacuum cleaning process.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        room_selected = update.message.text
        room_id = context.user_data["room_id"]
        room_name = context.user_data["room_name"]
        iterations = int(update.message.text)

        context.bot.send_message(chat_id=requester_id, text="Recibido! Me dirijo a limpiar '%s' en exactamente %s iteraciones.\nAsegurate de que la habitación está COMPLETAMENTE ORDENADA y la puerta ABIERTA!" % (
            room_name, iterations), reply_markup=ReplyKeyboardRemove())

        if room_name == "Hab. Azul":
            vac.zoned_clean([[28530,23423,32080,27373,iterations]])
        elif room_name == "Hab. Hernán":
            vac.zoned_clean([[35911,27254,38411,30004,iterations]])
        elif room_name == "Hab. Martín":
            vac.zoned_clean([[34843,23311,38293,27261,iterations]])
        elif room_name == "Hab. Mamá":
            vac.zoned_clean([[32188,23411,34788,27261,iterations]])
        elif room_name == "Cocina":
            vac.zoned_clean([[32666,30864,35916,34014,iterations]])
        elif room_name == "Baño pequeño":
            vac.zoned_clean([[34803,28260,35853,30060,iterations]])
        elif room_name == "Baño grande":
            vac.zoned_clean([[32802,28303,34752,30753,iterations]])
        elif room_name == "Living":
            vac.zoned_clean([[25674,27410,30974,30610,iterations],[25307,24536,28507,27386,iterations]])
        elif room_name == "Pasillo":
            vac.zoned_clean([[31000,27365,32600,31965,iterations],[32621,27349,35871,28349,iterations]])

        # Empty cache as action is done.
        context.user_data["room_id"] = ""
        context.user_data["room_name"] = ""
        # End of conversation flow (ConversationHandler)
        return ConversationHandler.END

def go_to(update,context):
    """Makes the Vacuum go to the desired destination.
    """    

    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        room_selected = update.message.text
        room_id = room_selected.split(":")[0]
        room_name = room_selected.split(": ")[1]

        context.bot.send_message(chat_id=requester_id, text="Recibido! Me dirijo a '%s'.\nCuando llegue, usá el comando /aspirar_spot_puerta_cerrada para comenzar a limpiar la habitación (Cerrando la puerta previamente y quitando objetos que puedan trabar la aspiradora).\nUsá /aspiradora_base_carga para volver a la base de carga." % (
            room_name), reply_markup=ReplyKeyboardRemove())

        if room_name == "Hab. Azul":
            vac.goto(30900,25950)
        elif room_name == "Hab. Hernán":
            vac.goto(37200,28050)
        elif room_name == "Hab. Martín":
            vac.goto(36900,25550)
        elif room_name == "Hab. Mamá":
            vac.goto(33250,26100)
        elif room_name == "Cocina":
            vac.goto(34000,32500)
        elif room_name == "Baño pequeño":
            vac.goto(35400,29300)
        elif room_name == "Baño grande":
            vac.goto(33800,30150)
        elif room_name == "Living":
            vac.goto(27100,28250)
        elif room_name == "Pasillo":
            vac.goto(31850,27900)

        # End of conversation flow (ConversationHandler)
        return ConversationHandler.END

def vacuum_spot(update,context):
    """Vacuum the current spot where the vacuum is.
    Does not try to go back to the dock when finished.
    """     
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        context.bot.send_message(chat_id=requester_id, text="Recibido! Procedo a limpiar esta habitación. No olvides cerrar la puerta!\nSi querés dar otra pasada, repetí el comando cuando termine\nSi querés que vuelva a la base de carga cuando termine, usá /aspiradora_base_carga.")

        vac.spot()

def vacuum_dock(update,context):
    """Send vacuum back to the dock.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        context.bot.send_message(chat_id=requester_id, text="Recibido! De vuelta a la base de carga...")
        vac.home()

def vacuum_pause(update,context):
    """Send vacuum back to the dock.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        context.bot.send_message(chat_id=requester_id, text="Recibido! Aspiradora pausada.")
        vac.pause()

def vacuum_resume_zoned_clean(update,context):
    """Send vacuum back to the dock.
    """
    requester_id = update.message.chat_id

    if requester_id in allowed_users:
        context.bot.send_message(chat_id=requester_id, text="Recibido! La aspiradora continúa con la limpieza de zona.")
        vac.resume_zoned_clean()

def vacuum_fan_speed(update,context):
    """Asks the user for a custom fan speed [0-100]
    """
    requester_id = update.message.chat_id
    if requester_id in allowed_users:
        context.bot.send_message(
            chat_id=requester_id, text="Introducí un valor de potencia del 0 al 100 (Modo turbo = 90):")
        return FAN_SPEED
    else:
        return ConversationHandler.END

def vacuum_set_fan_speed(update,context):
    """Sets the vacuum fan speed [0-100]
    """
    requester_id = update.message.chat_id
    input_value = update.message.text
    if int(input_value) < 0 or int(input_value) > 100:
        context.bot.send_message(
            chat_id=requester_id, text="El valor introducido no está en el rango [0-100]. Introducilo de nuevo.")
        return FAN_SPEED
    else:
        vac.set_fan_speed(int(input_value))
        context.bot.send_message(chat_id=requester_id, text="Perfecto! Potencia establecida a %s." % ( input_value ))

    # End of conversation flow (ConversationHandler)
    return ConversationHandler.END

def vacuum_get_fan_speed(update,context):
    """Gets the vacuum fan speed value
    """    
    requester_id = update.message.chat_id
    fan_speed = vac.fan_speed()
    if requester_id in allowed_users:
        context.bot.send_message(chat_id=requester_id, text="El valor de potencia de la aspiradora es: %s " % ( str(fan_speed) ))

def ping_back_requester_id(update,context):
    """Used once to get the user ID of each family member
    """
    requester_id = update.message.chat_id
    context.bot.send_message(
        chat_id='6717226', text=requester_id)

def announce_new_commands(update,context):
    """Make a global announcement to allowed users
    """     
    for cid in allowed_users:
        announce_text = "Hola\! Dejo la lista de comandos tras los últimos cambios:\n\n*ASPIRADORA*\n\n/aspirar\_habitacion \- Aspirar una habitación \(puerta ABIERTA\) y volver a la base\n/aspiradora\_ir\_habitacion \- Llevar la aspiradora a una habitación\n/aspirar\_spot\_puerta\_cerrada \- Aspirar una habitación \(puerta CERRADA\) sin volver a la base\n/aspiradora\_base\_carga \- Llevar la aspiradora a la base de carga\n/aspiradora\_pausar \- Pausar aspiradora\n/aspiradora\_continuar\_zona \- Continuar limpieza de zona tras pausa\n/aspiradora\_potencia \- Obtener valor de potencia de aspiradora \(%\)\n/aspiradora\_establecer\_potencia \- Establecer valor de potencia de aspiradora \(%\)\n\n*LUCES Y SENSORES:*\n\n/alternar\_sensor\_pasillo \- Alternar sensor presencia y luz en pasillo\n/modificar\_luces \- Interactuá con las luces de la casa\n/encender\_luces \- Encendé todas las luces\n/apagar\_luces \- Apagá todas las luces\n/luces \- Recibí una lista de las bombillas inteligentes registradas\n/temperatura \- Recibí el valor de temperatura en el pasillo\n/luminancia \- Recibí el valor de luminancia en el pasillo\n\n*EXTRAS:*\n\n/cafe\_mama \- Solicitá un café a Martín con un aviso lumínico\n/informacion\_solar \- Recibí información solar de esta ubicación\n/perrete \- Recibí la foto de un lindo y feliz perrete\!\n/gatete \- Recibí la foto de un precioso y apuesto gatete\!\n\n*OTROS:*\n\n/cancel \- Cancelá la acción en curso\n/comandos \- Recibir esta lista de comandos" 
        context.bot.send_message(chat_id=cid, text=announce_text, parse_mode=ParseMode.MARKDOWN_V2)
def main():
    """Main function. Initialization of Telegram bot and its handlers.
    """

    b.connect()

    # Create the EventHandler and pass it the bot's token.
    updater = Updater(
        'telegram_bot_token_goes_here', use_context=True)

    # I make the bot globally accesible so I can send messages even without
    # Telegram user interaction.
    global telegram_bot
    telegram_bot = updater.bot

    # Initial sunrise/sunset data obtaining. Successive interactions will be
    # made everyday at 00:00:00 (scheduled thread)
    get_sunrise_sunset_data()

    # Get the dispatcher to register handlers:
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("comandos", start))
    dp.add_handler(CommandHandler("cancel", cancel))
    dp.add_handler(CommandHandler("cafe_mama", request_coffee))
    dp.add_handler(CommandHandler("ok_cafe", ok_cafe))
    dp.add_handler(CommandHandler("gatete", send_animal_pic_to_user))
    dp.add_handler(CommandHandler("perrete", send_animal_pic_to_user))
    dp.add_handler(CommandHandler("temperatura", home_temperature))
    dp.add_handler(CommandHandler("luces", lights_list))
    dp.add_handler(CommandHandler("encender_luces", turn_all_lights_on))
    dp.add_handler(CommandHandler("apagar_luces", turn_all_lights_off))
    dp.add_handler(CommandHandler("luminancia", home_luminance))
    dp.add_handler(CommandHandler(
        "alternar_sensor_pasillo", switch_sensor_routine))
    dp.add_handler(CommandHandler("explicacion", explanation))
    dp.add_handler(CommandHandler("informacion_solar", solar_information))
    dp.add_handler(CommandHandler("aspirar_spot_puerta_cerrada", vacuum_spot))
    dp.add_handler(CommandHandler("aspiradora_base_carga", vacuum_dock))
    dp.add_handler(CommandHandler("aspiradora_pausar", vacuum_pause))
    dp.add_handler(CommandHandler("aspiradora_continuar_zona", vacuum_resume_zoned_clean))
    dp.add_handler(CommandHandler("aspiradora_potencia", vacuum_get_fan_speed))
    dp.add_handler(CommandHandler("horario", get_sunlight_state))
    dp.add_handler(CommandHandler("id", ping_back_requester_id))
    dp.add_handler(CommandHandler("anunciar_comandos", announce_new_commands))

    conv_handler_lights = ConversationHandler(
        entry_points=[CommandHandler("modificar_luces", modify_bulb_param)],

        states={
            SELECT_LIGHT: [MessageHandler(Filters.regex('^(\d+: .+)$'), select_light)],

            SELECT_ACTION: [MessageHandler(Filters.text, select_action)],

            SET_VALUE: [MessageHandler(Filters.text, process_action)]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler("cancel", cancel)]

    )

    dp.add_handler(conv_handler_lights)

    conv_handler_rooms = ConversationHandler(
        entry_points=[CommandHandler("aspirar_habitacion", vacuum_zone)],

        states={
            SELECT_ROOM: [MessageHandler(Filters.regex('^(\d+: .+)$'), select_room)],

            SELECT_ITERATIONS: [MessageHandler(Filters.regex('^(\d+)$'), select_iterations)]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler("cancel", cancel)]

    )

    dp.add_handler(conv_handler_rooms)

    conv_handler_goto = ConversationHandler(
        entry_points=[CommandHandler("aspiradora_ir_habitacion", vacuum_zone)],

        states={
            SELECT_ROOM: [MessageHandler(Filters.regex('^(\d+: .+)$'), go_to)]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler("cancel", cancel)]

    )

    dp.add_handler(conv_handler_goto)

    conv_handler_fan_speed = ConversationHandler(
        entry_points=[CommandHandler("aspiradora_establecer_potencia", vacuum_fan_speed)],

        states={
            FAN_SPEED: [MessageHandler(Filters.regex('^(\d+)$'), vacuum_set_fan_speed)]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler("cancel", cancel)]

    )

    dp.add_handler(conv_handler_fan_speed)


    # Log all errors

    dp.add_error_handler(error)

    # Start bot:

    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process
    # receives SIGINT, SIGTERM or SIGABRT:

    updater.idle()

if __name__ == '__main__':
    sensor_routine_thread = threading.Thread(
        target=sensor_routine_twisted, daemon=True)
    sensor_routine_thread.start()
    get_sunrise_sunset_data_thread = threading.Thread(
        target=get_sunrise_sunset_data_sch, daemon=True)
    get_sunrise_sunset_data_thread.start()
    main()
