import time
import calendar
import requests
import os
import ast
import speech_recognition as sr
import paramiko

from PIL import Image  # works only in local env
from naoqi import ALProxy
from scipy.io.wavfile import write  # TODO: used?
from dialog import Dialog  # custom dialogs
from actions import Actions #costum Actions

# get current timestamp
def getTimestamp():
    return str(calendar.timegm(time.gmtime()))


# get Behavior names
def getBehaviors(managerProxy):
  '''
  Know which behaviors are on the robot 
  '''
  names = managerProxy.getInstalledBehaviors()
  print('Behaviors on the robot: ', names)
  names = managerProxy.getRunningBehaviors()
  print('Running behaviors: ', names)


def launchAndStopBehavior(MANAGERPROXY, behaviorName, time_for_behavior):
  '''
  Launch and stop a behavior, if possible. 
  '''
  # Check that the behavior exists.
  if (MANAGERPROXY.isBehaviorInstalled(behaviorName)):

    # Check that it is not already running.
    if (not MANAGERPROXY.isBehaviorRunning(behaviorName)):
      # Launch behavior. This is a blocking call, use post if you do not
      # want to wait for the behavior to finish.
      MANAGERPROXY.post.runBehavior(behaviorName)
      time.sleep(time_for_behavior)
    else:
      print('Behavior is already running.')

  else:
    print('Behavior not found.')
    return

  names = MANAGERPROXY.getRunningBehaviors()
  print('Running behaviors:')
  print(names)

  # Stop the behavior.
  if (MANAGERPROXY.isBehaviorRunning(behaviorName)):
    MANAGERPROXY.stopBehavior(behaviorName)
    time.sleep(1.0)
  else:
    print('Behavior is already stopped.')

  names = MANAGERPROXY.getRunningBehaviors()
  print('Running behaviors:')
  print(names)


class Functions:
    '''
    Stored all functions in this class, to call them in the main.py script.
    '''

    # Take picture + emotion detection
    @staticmethod
    def emotionDetectionWithPic(NAOIP, PORT, BASE_API, text, camera, resolution, colorSpace, images_folder):
        naoImage = Functions.takePicture(NAOIP, PORT, camera, resolution, colorSpace, images_folder) # take picture
        response_ed = requests.get(BASE_API + '/emotiondetection/' + naoImage) # get response 
        while response_ed.status_code != 200: # Error message: cant identify a person
            text.say('I cannot see you properly, please look at my head.') # Error meessage
            os.remove(os.path.join(images_folder, naoImage)) # remove picture to safe storage
            try: # try again
                naoImage = Functions.takePicture(NAOIP, PORT, camera, resolution, colorSpace, images_folder)
                response_ed = requests.get(BASE_API + '/emotiondetection/' + naoImage)
            except ValueError:
                print(response_ed)
        result_ed = ast.literal_eval(response_ed.json())
        return result_ed, naoImage

    # take picture
    @staticmethod
    def takePicture(IP, PORT, camera, resolution, colorSpace, location):
        camProxy = ALProxy('ALVideoDevice', IP, PORT)
        videoClient = camProxy.subscribeCamera('python_client', camera, resolution, colorSpace, 5)
        naoImage = camProxy.getImageRemote(videoClient)
        camProxy.unsubscribe(videoClient)
        imageName = 'image_' + getTimestamp() + '.png' # create imagename
        im = Image.frombytes('RGB', (naoImage[0], naoImage[1]), naoImage[6]) # naoImage[0] = width, naoImage[1] = height, naoImage[6] = image data as ASCII char array
        im.save(location + os.sep + imageName, 'PNG') # safe image 
        print('Image: ' + imageName + ' successfully saved @ ' + location)
        return imageName

    #Record audio 
    @staticmethod
    def record_audio(NAOIP, PORT, t):
        recorderProxy = ALProxy('ALAudioRecorder', NAOIP, PORT)
        leds = ALProxy('ALLeds',NAOIP,PORT) # TODO: not used
        recorderProxy.stopMicrophonesRecording()
        nao_recordings_path = '/home/nao/nao_solutions/wavs/'
        audioName = 'name_' + getTimestamp() + '.wav'
        remoteaudiofilepath = nao_recordings_path + audioName
        channels = (1, 0, 0, 0); # python tuple, C++ code uses AL:ALValue --> only 1 
        print('Started Dialog...')
        recorderProxy.startMicrophonesRecording('/home/nao/nao_solutions/wavs/' + audioName, 'wav', 16000, channels)
        time.sleep(t)
        recorderProxy.stopMicrophonesRecording()
        return remoteaudiofilepath


    # Speech2Text using google speech recognition
    @staticmethod
    def speech_recognition(remoteaudiofile, NAOIP, PASSWD, NAME):
        transport = paramiko.Transport((NAOIP, 22)) # set up paramiko
        transport.connect(username=NAME, password=PASSWD) # connect paramiko
        sftp = transport.open_sftp_client() # open sftp client
        audio_file = sftp.open(remoteaudiofile) # open audiofile path
        r = sr.Recognizer() # initliaze speech_recognition
        with sr.AudioFile(audio_file) as file:
            audio_file = r.listen(file)
            try:
                text_data = str(r.recognize_google(audio_file))
                print('recognized text: ', text_data)
                return text_data
            except sr.UnknownValueError as uve: # Error handling
                print('Error ', uve)
            finally:
                sftp.remove(remoteaudiofile) # remove audio file on NAO

    ##########################
    # Name 2 Text Functions #
    ##########################

    '''
    In this functions the name is recorded.
    '''

    @staticmethod
    def record_name(NAOIP, PORT, PASSWD, NAME, text, record_name_time):
        text.say(Dialog.say_name)
        recording = Functions.record_audio(NAOIP, PORT, record_name_time)
        name_of_user = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
        return name_of_user

    @staticmethod
    def name_loop(NAOIP, PORT, PASSWD, NAME, text, record_name_time, name_of_user):
        while name_of_user == None:
            text.say(Dialog.sorry_message[0])
            time.sleep(1)
            name_of_user = Functions.record_name(NAOIP, PORT, PASSWD, NAME, text, record_name_time)
        return name_of_user

    @staticmethod
    def confirm(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, name_of_user):
        text.say(Dialog.confirmation_message_with_name(name_of_user))
        recording = Functions.record_audio(NAOIP, PORT, record_confirm_time)
        confirmation = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
        while confirmation not in ['yes', 'no']:
            text.say(Dialog.sorry_message[0])
            time.sleep(1)
            text.say(Dialog.confirm_loop_with_name(name_of_user))
            recording = Functions.record_audio(NAOIP, PORT, record_confirm_time)
            confirmation = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
        return confirmation

    @staticmethod
    def knowledgebase_entry(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, confirmation, name_of_user):
        while confirmation in ['yes', 'no']:
            if confirmation == 'yes':
                text.say(Dialog.knownledge_base_entry(name_of_user))
                break
            elif confirmation == 'no':
                text.say(Dialog.sorry_message[2])
                recording = Functions.record_audio(NAOIP, PORT, 5)
                name_of_user = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
                name_of_user = Functions.name_loop(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, name_of_user)
                confirmation = Functions.confirm(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, name_of_user)
        return name_of_user

    # FINAL MEGA FUNCTION 
    @staticmethod
    def get_and_save_name(NAOIP, PORT, PASSWD, NAME, text):
        name_of_user = Functions.record_name(NAOIP, PORT, PASSWD, NAME, text, 5)
        name_of_user = Functions.name_loop(NAOIP, PORT, PASSWD, NAME, text, 5, name_of_user)
        confirmation = Functions.confirm(NAOIP, PORT, PASSWD, NAME, text, 3, name_of_user)
        final_name = Functions.knowledgebase_entry(NAOIP, PORT, PASSWD, NAME, text, 3, confirmation, name_of_user)
        return final_name


    ########################
    # DELETE USER FUNCTION #
    ########################

    '''
    This is the delete user Function.
    '''

    @staticmethod
    def delete_user(NAOIP, PORT, BASE_API, PASSWD, NAME, text, user_name, img_id, data_save_approval):
        text.say(Dialog.user_selection[0])
        recording = Functions.record_audio(NAOIP, PORT, 2)
        user_selection = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
        while user_selection not in ['yes', 'no', 'nope']:
            text.say(Dialog.confirm_user_deletion_loop(user_name))
            recording = Functions.record_audio(NAOIP, PORT, 2)
            user_selection = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
            print('INFO delete_user() - user_selection: ', user_selection)
        if user_selection == 'yes':
            text.say(Dialog.user_selection[1])
            requests.get(BASE_API + '/deleteperson/' + img_id)
            text.say(Dialog.user_selection[2])
            data_save_approval = False
        else:
            text.say(Dialog.no_deletion(user_name))
        return data_save_approval


    ###############################
    # ADD NAME TO KNOWNLEDGE BASE #
    ###############################
    '''
    Ask user for saving the data.
    '''
    @staticmethod
    def data_saving(NAOIP, PORT, BASE_API, PASSWD, NAME, text, user_name, naoImage, default_approval):
        text.say('Is it okay for you, if I save your data for face recognition and analytics?')
        recording = Functions.record_audio(NAOIP, PORT, 2)
        user_selection = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
        print('user_selection:', user_selection)
        while user_selection not in ['yes', 'no', 'nope']:
            text.say(Dialog.confirm_user_deletion_loop(user_name))
            recording = Functions.record_audio(NAOIP, PORT, 2)
            user_selection = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
            print('INFO: ', user_selection)
        if user_selection == 'yes':
            text.say('Very good! Next time I will remember your name')
            requests.get(BASE_API + '/addname/' + user_name + '/' + naoImage)
            default_approval = True
        else:
            default_approval = False
            text.say('Okay, thats too bad. After this session all your data will be cleaned.')
        return default_approval


    #############################
    # MANUAL EMOTION DETECTION #
    #############################

    '''
    Functions for manual emotion detection.
    '''

    @staticmethod
    def emotion_recording(NAOIP, PORT, PASSWD, NAME, text, record_name_time):
        text.say(Dialog.emotion_recording[0])
        recording = Functions.record_audio(NAOIP, PORT, record_name_time)
        print('EMOTION RECORDING IS HERE')
        emotion_rating = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
        try:
            emotion_rating = emotion_rating.split(' ')[1]
            print('before casting:', emotion_rating)
            emotion_rating=Functions.str_to_number(emotion_rating)
            print('after casting:', emotion_rating)
        except:
            emotion_rating = 'not_valid'
        return emotion_rating

    @staticmethod
    def emotion_recording_loop(NAOIP, PORT, PASSWD, NAME, text, record_name_time, emotion_rating, name_of_user):
        while emotion_rating not in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']: # TODO change to range(1,11)
            text.say(Dialog.invalid_emotion(name_of_user))
            recording = Functions.record_audio(NAOIP, PORT, record_name_time)
            emotion_rating = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
            try:
                emotion_rating = emotion_rating.split(' ')[1]
                print('before casting:', emotion_rating)
                emotion_rating=Functions.str_to_number(emotion_rating)
                print('after casting:', emotion_rating)
            except:
                emotion_rating = 'not_valid'
        return emotion_rating

    @staticmethod
    def confirm_emotion(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, emotion_rating, name_of_user):
        text.say(Dialog.emotion_confirmation(name_of_user, emotion_rating))
        recording = Functions.record_audio(NAOIP, PORT, record_confirm_time)
        confirmation = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
        return confirmation

    @staticmethod
    def confirm_emotion_loop(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, confirmation, emotion_rating):
        while confirmation not in ['yes', 'no']:
            text.say(Dialog.sorry_message[0])
            time.sleep(1)
            text.say(Dialog.emotion_invalid_confirmation(emotion_rating))
            recording = Functions.record_audio(NAOIP, PORT, record_confirm_time)
            confirmation = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
        return confirmation

    @staticmethod
    def final_rating(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, confirm_rating,emotion_rating, name_of_user):
        while confirm_rating in ['yes', 'no']:
            if confirm_rating == 'yes':
                text.say(Dialog.emotion_recording[1])
                break
            elif confirm_rating == 'no':
                text.say(Dialog.emotion_recording[2])
                recording = Functions.record_audio(NAOIP, PORT, 2)
                emotion_rating = Functions.speech_recognition(recording, NAOIP, PASSWD, NAME)
                emotion_rating = Functions.emotion_recording_loop(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, emotion_rating, name_of_user)
                confirm_rating = Functions.confirm_emotion(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, emotion_rating, name_of_user)
                confirm_rating = Functions.confirm_emotion_loop(NAOIP, PORT, PASSWD, NAME, text, record_confirm_time, confirm_rating, emotion_rating)
        emotion_rating = int(emotion_rating)
        return emotion_rating

    @staticmethod
    def manual_emotion(NAOIP, PORT, PASSWD, NAME, text, name_of_user):
        emotion_rating = Functions.emotion_recording(NAOIP, PORT, PASSWD, NAME, text, 4)
        emotion_rating = Functions.emotion_recording_loop(NAOIP, PORT, PASSWD, NAME, text, 4, emotion_rating, name_of_user)
        confirm_rating = Functions.confirm_emotion(NAOIP, PORT, PASSWD, NAME, text, 2, emotion_rating, name_of_user)
        confirm_rating = Functions.confirm_emotion_loop(NAOIP, PORT, PASSWD, NAME, text, 2, confirm_rating, emotion_rating)
        final_emotion_rating = Functions.final_rating(NAOIP, PORT, PASSWD, NAME, text, 2, confirm_rating, emotion_rating, name_of_user)
        return final_emotion_rating


    #############################
    # EMOTIONMATCHING FUNCTIONS #
    #############################

    '''
    Nao makes an action.
    '''

    @staticmethod
    def action(MOTIONPROXY, POSTUREPROXY, SOUNDPROXY, MANAGERPROXY, text, emotion_number, emotion, name_of_user):
        if emotion_number in range(1,6):
            if emotion in ['happy', 'surprise']:
                text.say('You seem to be lying! ')
                text.say(Dialog.random_joke(name_of_user))
                SOUNDPROXY.post.playFile('/home/nao/nao_solutions/sound_effects/badumtss.wav', 1, 0.0) 
                # action Confused?
                time_for_bow = 5
                launchAndStopBehavior(MANAGERPROXY, 'bow', time_for_bow)
                #Actions.hulahoop(MOTIONPROXY, POSTUREPROXY)
                Actions.dance(MOTIONPROXY)
            else:
                text.say('Let me try to cheer you up! ')
                text.say(Dialog.random_joke(name_of_user))
                SOUNDPROXY.post.playFile('/home/nao/nao_solutions/sound_effects/badumtss.wav', 1, 0.0) 
                time_for_bow = 5
                launchAndStopBehavior(MANAGERPROXY, 'bow', time_for_bow)
                Actions.dance(MOTIONPROXY)
        else:
            if emotion in ['happy', 'surprise']:
                text.say('I am glad that you are in a good mood! ')
                text.say(Dialog.random_joke(name_of_user))
                SOUNDPROXY.post.playFile('/home/nao/nao_solutions/sound_effects/badumtss.wav', 1, 0.0) 
                # action Excited?
                # hulahoop(NAOIP, PORT)
                #launchAndStopBehavior(MANAGERPROXY, 'bow', time_for_bow)
                Actions.dance(MOTIONPROXY)
            else:
                text.say('Hmm your expression earlier told me otherwise. ')
                text.say(Dialog.random_joke(name_of_user))
                SOUNDPROXY.post.playFile('/home/nao/nao_solutions/sound_effects/badumtss.wav', 1, 0.0) 
                Actions.dance(MOTIONPROXY)
                
    # If Emotion ... NAO say "...." 
    @staticmethod
    def emotionchange(emotion, emotion2, text):
        negative = ['angry', 'disgust', 'fear', 'sad']
        neutral = ['neutral']
        positive = ['happy', 'surprise']
        if emotion in positive and emotion2 in positive:
            text.say('I am glad I could keep you happy.')
        elif emotion in positive and emotion2 not in positive:
            text.say('Looks like I made your mood worse. Sorry about that!')
        elif emotion in negative and emotion2 in negative or emotion in neutral and emotion2 in neutral:
            text.say('Looks like I could not change your mood.')
        elif emotion in negative or neutral and emotion2 in positive:
            text.say('I am glad I could brighten up your mood.')
        elif emotion in negative or neutral and emotion2 in negative:
            text.say('I hope your mood will get better anytime soon.')

    # Str to integer cast 
    @staticmethod
    def str_to_number(number):
        if number in ['pen', '10', 'ten']:
            number = '10'
        elif number in ['wine', '9', 'mine', 'nine']:
            number = '9'
        elif number in ['eight', '8', 'ate']:
            number = '8'
        elif number in ['seven', '7', 'heaven']:
            number = '7'
        elif number in ['six', '6']:
            number = '6'
        elif number in ['fife', '5', 'five']:
            number = '5'
        elif number in ['four', '4', 'for']:
            number = '4'
        elif number in ['three', 'tree', '3', 'free']:
            number = '3'
        elif number in ['too', 'to', 'two', '2']:
            number = '2'
        elif number in ['on', 'one', '1']:
            number = '1'
        else:
            number = 'not_valid'
        return number