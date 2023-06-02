import threading
import time
from datetime import datetime, timedelta
from multiprocessing import Process
from time import monotonic

import redis
from loguru import logger

import camera
import database_work
import finder as fin

enabled = False

#02/06/2023 внесені зміни type_uuid=database_work.TypeUUID з ticket на card
class UserProfile:
    def __init__(self, uuid=None, type_uuid=database_work.TypeUUID.card, name=None, surname=None, group=None,
                 plate_number=None, direction=None, photo=None):
        self.uuid = uuid
        self.type_uuid = type_uuid
        self.name = name
        self.surname = surname
        self.group = group
        self.plate_number = plate_number
        self.direction = direction
        self.type_passage = database_work.CodeTypePassage.automatically
        self.photo = photo


def formatter(record):
    if 'func' in record['extra'] and 'data' in record['extra']:
        return "{time:YYYY-MM-DD HH:mm:ss} | {name} | {level}  | Func={extra[func]} | Data={extra[data]} | {message}\n"
    elif 'func' in record['extra']:
        return "{time:YYYY-MM-DD HH:mm:ss} | {name} | {level} | Func={extra[func]} | {message}\n"
    else:
        return "{time:YYYY-MM-DD HH:mm:ss} | {name} | {level} | {message}\n"


logger.add("logs.log", retention=timedelta(seconds=20), format=formatter,
           level='DEBUG', backtrace=True, diagnose=True, rotation="10 MB")

try:
    finder = fin.Finder()

    user_profile = UserProfile()

    redis = redis.StrictRedis(
        host='127.0.0.1',
        port=6379,
        charset="utf-8",
        decode_responses=True
    )
    
    redis.delete('camera_in')
    redis.delete('camera_out')
    print("Camera out data has been cleared.")

    timer = monotonic()

except Exception as ex:
    logger.exception(ex)

state_barrier = None
prev_uuid = {
    'uuid': '',
    'time': datetime.now()
}

STATUS_PARK = {'1000': 1,
               '0100': 2}
state = {'dts1': False, 'dts2': False, 'dts1-2': False}

connected = True


def add_to_manager(data):
    try:
        for key, value in data.items():
            redis.hset('set_colors', key, value)
    except Exception as ex:
        logger.bind(func='convert_value_plate').exception(ex)


def convert_value(struct):
    try:
        for key, value in struct.items():
            struct[key] = int(value)
    except Exception as ex:
        logger.bind(func='convert_value_plate').exception(ex)


def convert_value_plate(struct):
    try:
        if len(struct) > 0:
            for key, value in struct.items():
                struct[key] = value
            return struct
        else:
            struct = None
            return struct
    except Exception as ex:
        logger.bind(func='convert_value_plate').exception(ex)


def create_photo():
    try:
        cameras = database_work.get_settings_camera()
        if cameras:
            photo = datetime.now()
            photo = str(photo.strftime("%m_%d_%Y_%H_%M_%S"))
            cam_thread = threading.Thread(target=camera.get_picture,
                                          args=(f'{photo}', cameras))
            cam_thread.start()
            photo = f'{photo}.jpg'
            return photo
        return None
    except Exception as ex:
        logger.bind(func='convert_value_plate').exception(ex)


def set_light_and_buzzer_state(code_park, red, green, yellow, buzzer, sleep_time, target_color):
    add_to_manager({
        'id_reader': code_park,
        'red': red,
        'green': green,
        'yelow': yellow,
        'buzzer': buzzer
    })

    if sleep_time is not None:
        time.sleep(sleep_time)
        add_to_manager({
            'id_reader': code_park,
            'red': red,
            'green': green,
            'yelow': yellow,
            'buzzer': 0
        })

    redis.set('color_light', target_color)


def check_permission(code_event, user_profile, wig, photo, reader, code_park):
    data = {'code_event': code_event,
            'wig': wig,
            'photo': photo,
            'reader': database_work.convert_object_to_dict(reader)}
    logger.bind(func='check_permission').debug('Run func')
    logger.bind(func='check_permission', data=data).info('')

    try:
        if code_event.value == database_work.CodeEvent.successful_passage.value:
            database_work.create_card_in_system(wig, database_work.CodeStatusCard.successful, datetime.now())

            if user_profile.type_uuid.value == database_work.TypeUUID.auto.value:
                user_profile.uuid = user_profile.plate_number
            else:
                user_profile.uuid = wig

            user = database_work.get_user(wig)
            group = database_work.get_group(wig)

            user_profile.type_uuid = database_work.TypeUUID.card
            user_profile.name = user.name
            user_profile.surname = user.surname
            user_profile.group = group.name_group
            user_profile.direction = reader.zone.name_zone
            user_profile.photo = photo

            redis.set('open_barrier', 1)

            set_light_and_buzzer_state(code_park, red=0, green=1, yellow=0, buzzer=1, sleep_time=0.4, target_color='green')

            logger.bind(func='check_permission', user_profile=user_profile).info('Successful passage')

        elif code_event.value == database_work.CodeEvent.exaltation.value:
            user = database_work.get_user(wig)
            group = database_work.get_group(wig)
            database_work.create_event(name=user.name, surname=user.surname, uuid=user_profile.uuid,
                                       plate_number=user_profile.plate_number,
                                       direction=reader.zone.name_zone,
                                       group=group.name_group,
                                       type_passage=database_work.CodeTypePassage.automatically,
                                       status=code_event,
                                       photo=photo)

            logger.bind(func='check_permission').info('Exaltation')

        elif code_event.value == database_work.CodeEvent.passage_not_take_place.value:

            set_light_and_buzzer_state(code_park, red=1, green=0, yellow=0, buzzer=1, sleep_time=0.6, target_color='red')

            if user_profile.type_uuid.value == database_work.TypeUUID.auto.value:
                user_profile.uuid = user_profile.plate_number
            else:
                user_profile.uuid = wig

            user = database_work.get_user(wig)
            group = database_work.get_group(wig)
            database_work.create_event(name=user.name, surname=user.surname, uuid=user_profile.uuid,
                                       plate_number=user_profile.plate_number,
                                       direction=reader.zone.name_zone,
                                       group=group.name_group,
                                       type_passage=database_work.CodeTypePassage.automatically,
                                       status=code_event,
                                       photo=photo)

            logger.bind(func='check_permission').info('Passage not take place')

        elif code_event.value == database_work.CodeEvent.not_access_to_zone.value:
            database_work.create_card_in_system(wig, database_work.CodeStatusCard.not_access_to_zone, datetime.now())

            set_light_and_buzzer_state(code_park, red=1, green=0, yellow=0, buzzer=1, sleep_time=0.6, target_color='red')

            if user_profile.type_uuid.value == database_work.TypeUUID.auto.value:
                user_profile.uuid = user_profile.plate_number
            else:
                user_profile.uuid = wig

            user = database_work.get_user(wig)
            group = database_work.get_group(wig)
            database_work.create_event(name=user.name, surname=user.surname, uuid=user_profile.uuid,
                                       plate_number=user_profile.plate_number,
                                       direction=reader.zone.name_zone,
                                       group=group.name_group,
                                       type_passage=database_work.CodeTypePassage.automatically,
                                       status=code_event,
                                       photo=photo)
            logger.bind(func='check_permission').info('Not access to zone')

        elif code_event.value == database_work.CodeEvent.not_access_to_timezone.value:
            database_work.create_card_in_system(wig, database_work.CodeStatusCard.not_access_to_zone, datetime.now())
            
            set_light_and_buzzer_state(code_park, red=1, green=0, yellow=0, buzzer=1, sleep_time=0.6, target_color='red')

            if user_profile.type_uuid.value == database_work.TypeUUID.auto.value:
                user_profile.uuid = user_profile.plate_number
            else:
                user_profile.uuid = wig

            user = database_work.get_user(wig)
            group = database_work.get_group(wig)
            database_work.create_event(name=user.name, surname=user.surname, uuid=user_profile.uuid,
                                       plate_number=user_profile.plate_number,
                                       direction=reader.zone.name_zone,
                                       group=group.name_group,
                                       type_passage=database_work.CodeTypePassage.automatically,
                                       status=code_event,
                                       photo=photo)
            logger.bind(func='check_permission').info('Not access to timezone')

        elif code_event.value == database_work.CodeEvent.not_in_base.value:
            database_work.create_card_in_system(wig, database_work.CodeStatusCard.not_in_base, datetime.now())

            set_light_and_buzzer_state(code_park, red=1, green=0, yellow=0, buzzer=1, sleep_time=0.6, target_color='red')

            if user_profile.type_uuid.value == database_work.TypeUUID.auto.value:
                user_profile.uuid = user_profile.plate_number
            else:
                user_profile.uuid = wig

            database_work.create_event(uuid=user_profile.uuid, plate_number=user_profile.plate_number,
                                       direction=reader.zone.name_zone,
                                       type_passage=database_work.CodeTypePassage.automatically,
                                       status=code_event,
                                       photo=photo)

            logger.bind(func='check_permission').info('Not in base')

    except Exception as ex:
        logger.bind(func='check_permission').exception(ex)


def check_state_inputs(status):
    #logger.bind(func='check_state_inputs').debug('Run func')
    logger.bind(func='check_state_inputs', data=f'Data - {status}').info('')
    try:
        if status['dts1'] and not status['dts2']:
            state['dts1'] = True
        if status['dts1'] and status['dts2']:
            redis.set('color_light', 'white')
            state['dts1-2'] = True
        if status['dts2'] and not status['dts1']:
            state['dts2'] = True
        if state['dts1'] and state['dts2'] and state['dts1-2'] and (not status['dts1'] and not status['dts2']):
            return True
    except Exception as ex:
        logger.bind(func='check_state_inputs').exception(ex)


def check_barrier(status):
    global state_barrier
    try:
        if state_barrier != status:
            state_barrier = status
            logger.bind(func='check_barrier', state_barrier=status).info('State barrier updated')
            database_work.write_state_barrier(status)
    except Exception as ex:
        logger.bind(func='check_barrier').exception(ex)


def clean_state_inputs():
    #logger.bind(func='clean_state_inputs').debug('Run func')
    logger.bind(func='clean_state_inputs').info('')
    try:
        for key in state.keys():
            state[key] = False
    except Exception as ex:
        logger.bind(func='clean_state_inputs').exception(ex)


def park_mode(code_park):
    
    logger.bind(func='park_mode', data=f'Code park {code_park}').info('')

    global user_profile

    wig_temp = None
    enabled = False
    status_temp = None
    
    try:
        wig = redis.get(f'wig{code_park}')
        redis.set(f'wig{code_park}', '00')
        while True:
            time.sleep(0.2)
            status_inputs = redis.hgetall("status")
            convert_value(status_inputs)

            check_barrier(status_inputs['barrier'])

            wig = redis.get(f'wig{code_park}')
            redis.set(f'wig{code_park}', '00')

            if status_temp != status_inputs or wig_temp != wig:
                #logger.bind(func='park_mode', data=status_inputs).info('State inputs')
                #logger.bind(func='park_mode', data=wig).info('State wiegand')

                status_temp = status_inputs
                wig_temp = wig

            if check_state_inputs(status_inputs):
                clean_state_inputs()

                print(user_profile.uuid)

                if user_profile.uuid != None:
                    database_work.create_event(name=user_profile.name, surname=user_profile.surname,
                                               uuid=user_profile.uuid,
                                               plate_number=user_profile.plate_number,
                                               direction=user_profile.direction,
                                               group=user_profile.group,
                                               type_passage=database_work.CodeTypePassage.automatically,
                                               status=database_work.CodeEvent.successful_passage,
                                               photo=user_profile.photo)
                    
                    logger.bind(func='park_mode', data='Successful passage', user_profile=user_profile).info('Processing successful passage event')


                elif user_profile.type_passage.value == database_work.CodeTypePassage.manually.value:
                    reader = database_work.get_reader(code_park)
                    photo = create_photo()
                    database_work.create_event(direction=reader.zone.name_zone,
                                               type_passage=database_work.CodeTypePassage.manually,
                                               status=database_work.CodeEvent.successful_passage,
                                               photo=user_profile.photo)
                    
                    logger.bind(func='park_mode', data='Manual passage').info('Processing manual passage event')
    
                else:
                    reader = database_work.get_reader(code_park)
                    photo = create_photo()
                    database_work.create_event(direction=reader.zone.name_zone,
                                               type_passage=database_work.CodeTypePassage.automatically,
                                               status=database_work.CodeEvent.unauthorized_travel,
                                               photo=photo)
                    
                    logger.bind(func='park_mode', data='Unauthorized travel').info('Processing unauthorized travel event')

                #database_work.decrement_seets()
                user_profile = UserProfile()

                redis.set('close_barrier', 1)
                redis.delete('camera_in')
                redis.delete('camera_out')
                enabled = False
                
                set_light_and_buzzer_state(code_park, red=1, green=0, yellow=0, buzzer=1, sleep_time=0.6, target_color='white')

                break

            if (not status_inputs['dts1'] and not status_inputs['dts2']) and not all(
                    flag == False for flag in state.values()):
                
                
                clean_state_inputs()
                redis.set('close_barrier', 1)
                enabled = False

                redis.delete('camera_in')
                redis.delete('camera_out')
                
                set_light_and_buzzer_state(code_park, red=1, green=0, yellow=0, buzzer=1, sleep_time=0.6, target_color='white')

                break

            delta = datetime.now() - prev_uuid['time']
            # додано вибір камери in out в залежності від park_mode
            if code_park == 1:
                plate_number = redis.hgetall("camera_in")
                logger.bind(func='park_mode', data=f"Plate number: {plate_number}, Code park: {code_park}, Camera: camera_in").info('Processing plate_number')
            elif code_park == 2:
                plate_number = redis.hgetall("camera_out")
                logger.bind(func='park_mode', data=f"Plate number: {plate_number}, Code park: {code_park}, Camera: camera_out").info('Processing plate_number')

            else:
                plate_number = None
                logger.bind(func='park_mode', data=f"Invalid code park: {code_park}").warning('Processing plate_number')

            plate_number = convert_value_plate(plate_number)

            if plate_number != None:
                photo = create_photo()
                reader = database_work.get_reader(code_park)
                code_event = database_work.check_auto(plate_number)

                wig_tmp = database_work.get_card(plate_number=plate_number['plate_number'])
                wig_tmp = wig_tmp.uuid if wig_tmp else plate_number['plate_number']
                user_profile.type_uuid = database_work.TypeUUID.auto
                user_profile.plate_number = plate_number['plate_number']

                logger.bind(func='park_mode', data=f"User profile: {user_profile}, Code park: {code_park}").info('Processing plate_number')

                check_permission(code_event, user_profile, wig_tmp, photo, reader, code_park)

                redis.delete('camera_in')
                redis.delete('camera_out')

            if (wig != '00' and prev_uuid['uuid'] != wig) or (wig != '00' and delta > timedelta(seconds=1)):
                database_work.create_card_in_system(wig, database_work.CodeStatusCard.exaltation, datetime.now())
                
                photo = create_photo()
                reader = database_work.get_reader(code_park)
                code_event = database_work.check_card(wig, reader.zone)
                user_profile.type_uuid = database_work.TypeUUID.card

                logger.bind(func='park_mode', data=f"User profile: {user_profile}, Identifier: {wig}").info('Processing card')

                check_permission(code_event, user_profile, wig, photo, reader, code_park)

                prev_uuid['uuid'] = wig
                prev_uuid['time'] = datetime.now()

                redis.delete('camera_in')
                redis.delete('camera_out')

            if status_inputs['button'] and enabled == False:
                
                logger.bind(func='park_mode', data='Button pressed').info('Processing button press')
                photo = create_photo()
                user_profile.photo = photo
                user_profile.type_passage = database_work.CodeTypePassage.manually

                redis.delete('camera_in')
                redis.delete('camera_out')

                redis.set('open_barrier', 1)

                set_light_and_buzzer_state(code_park, red=0, green=1, yellow=0, buzzer=1, sleep_time=0.4, target_color='green')

                enabled = True



    except Exception as ex:
        logger.exception(ex)


def write_card_mode():
    logger.bind(func='write_card_mode').debug('Run func')
    try:
        while True:
            time.sleep(0.2)
            controller = database_work.get_controller()
            wig = redis.get(f'wig1')
            redis.set(f'wig1', '00')
            wig2 = redis.get('wig2')
            if wig2 != '00' :
                wig = wig2
                wig2 = '00'
                redis.set(f'wig2', '00')

            if not controller.reader_mode:
                logger.bind(func='write_card_mode').debug('Exit')
                break

            if wig != '00':
                add_to_manager({'id_reader': 1,
                                'red': 0,
                                'green': 1,
                                'yelow': 0,
                                'buzzer': 1})
                time.sleep(0.5)
                add_to_manager({'id_reader': 1,
                                'red': 1,
                                'green': 0,
                                'yelow': 0,
                                'buzzer': 0})

                time.sleep(2)
                resp = database_work.create_card(wig)

                if resp == 1:
                    logger.bind(func='write_card_mode').info('Card successfully created')
                    add_to_manager({'id_reader': 1,
                                    'red': 0,
                                    'green': 1,
                                    'yelow': 0,
                                    'buzzer': 1})
                    time.sleep(1)
                    add_to_manager({'id_reader': 1,
                                    'red': 1,
                                    'green': 0,
                                    'yelow': 0,
                                    'buzzer': 0})

                if resp == 3:
                    logger.bind(func='write_card_mode').info('Сard already exists')
                    add_to_manager({'id_reader': 1,
                                    'red': 0,
                                    'green': 0,
                                    'yelow': 0,
                                    'buzzer': 1})
                    time.sleep(0.3)
                    add_to_manager({'id_reader': 1,
                                    'red': 1,
                                    'green': 0,
                                    'yelow': 0,
                                    'buzzer': 0})

                if resp == 2:
                    logger.bind(func='write_card_mode').info('Сard did not register in the hub')
                    add_to_manager({'id_reader': 1,
                                    'red': 1,
                                    'green': 0,
                                    'yelow': 0,
                                    'buzzer': 1})
                    time.sleep(0.2)
                    add_to_manager({'id_reader': 1,
                                    'red': 1,
                                    'green': 0,
                                    'yelow': 0,
                                    'buzzer': 0})
                    time.sleep(0.2)
                    add_to_manager({'id_reader': 1,
                                    'red': 1,
                                    'green': 0,
                                    'yelow': 0,
                                    'buzzer': 1})
                    time.sleep(0.2)
                    add_to_manager({'id_reader': 1,
                                    'red': 1,
                                    'green': 0,
                                    'yelow': 0,
                                    'buzzer': 0})

    except Exception as ex:
        logger.exception(ex)


def read_from_atm():
    logger.bind(func='read_from_atm').debug('Run func')
    #prev_free_seets = None
    redis.set("action", 0)

    database_work.write_controller_in_hub()

    controller = database_work.get_controller()

    logger.bind(func='read_from_atm', data=f'{database_work.convert_object_to_dict(controller)}').info('')

    write_card_mode()

    redis.set('color_light', 'white')

    redis.delete('camera_in')
    redis.delete('camera_out')
    timer = monotonic()
    status_temp = None
    while connected:
        time.sleep(0.2)

        try:
            status_inputs = redis.hgetall("status")
            convert_value(status_inputs)

            check_barrier(status_inputs['barrier'])

            # free_seets = database_work.get_free_seets()

            if status_temp != status_inputs:
                logger.bind(func='read_from_atm', data=status_inputs).info('State inputs')

                status_temp = status_inputs

            if status_inputs['button'] and monotonic() - timer > 7:
                timer = monotonic()
                print(f"Button")
                photo = create_photo()
                user_profile.photo = photo
                user_profile.type_passage = database_work.CodeTypePassage.manually
                redis.set('open_barrier', 1)

            # if free_seets > 0:
            if status_inputs['dts1']:
                park_mode(1)

            if status_inputs['dts2']:
                park_mode(2)

            # if 0 < free_seets != prev_free_seets:
            #     prev_free_seets = free_seets


        except Exception as ex:
            logger.exception(ex)


if __name__ == "__main__":
    try:
        logger.debug('Run script')
        database_work.write_controller_in_hub()
        add_to_manager({'id_reader': 1,
                        'red': 1,
                        'green': 0,
                        'yelow': 0,
                        'buzzer': 0})
        add_to_manager({'id_reader': 2,
                        'red': 1,
                        'green': 0,
                        'yelow': 0,
                        'buzzer': 0})

        atm_process = Process(target=read_from_atm)

        atm_process.start()

    except Exception as ex:
        logger.exception(ex)
