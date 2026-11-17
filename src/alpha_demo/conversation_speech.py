"""Fresh one-sentence audio: verified USB upload, unplug detection, Bluetooth playback."""
from pathlib import Path
import json
import time
from . import robot_speech, speech, paired_speech
from .teacher import spoken_sentence
from .config import bluetooth_address
from .bluetooth_transport import BluetoothRobot


def check_cancel(cancel):
    if cancel.is_set():
        raise ValueError('Stopped. No further playback will be requested.')


def alpha_usb_present():
    """Read sysfs only; check both Alpha HID and storage identities."""
    for path in Path('/sys/bus/usb/devices').glob('*'):
        try:
            if (path/'idVendor').read_text().strip()=='0483' and (path/'idProduct').read_text().strip() in ('5750','5720'):
                return True
        except FileNotFoundError:
            continue  # Normal during disconnect; permission errors must not mean absent.
    return False


def wait_for_playback_interface(cancel, progress, timeout=120, *, clock=time.monotonic):
    """Wait for physical USB removal without issuing device commands."""
    progress('Upload verified. Unplug USB and leave it unplugged; Alpha will speak over Bluetooth. Stop cancels playback.')
    deadline=clock()+timeout
    while clock()<deadline:
        check_cancel(cancel)
        if not alpha_usb_present():
            # Give firmware time to return to wireless control; no automatic retries.
            cancel.wait(2)
            check_cancel(cancel)
            return
        cancel.wait(.25)
    raise TimeoutError('USB was not unplugged within two minutes. Audio is saved; no playback was sent.')


class _PlaybackGuard:
    def __init__(self,cancel):self.cancel=cancel;self.enabled=True
    def is_set(self):return self.enabled and not self.cancel.is_set()
    def clear(self):self.enabled=False


def play_uploaded(job,cancel,pose=None):
    """Use the previously verified full-path speaker route, once per fresh job."""
    address=bluetooth_address()
    if not address:raise ValueError('Configure the paired Bluetooth address before fresh speech.')
    stored=json.loads((Path(job['directory'])/'job.json').read_text())
    if stored.get('status')!='uploaded' or stored.get('playback_attempted'):
        raise ValueError('This fresh recording is not ready for playback; no retry.')
    if stored.get('name')!=job.get('name') or stored.get('sha256')!=job.get('sha256'):
        raise ValueError('Fresh audio job changed; playback blocked.')
    check_cancel(cancel)
    robot=BluetoothRobot(robot_speech.ROOT/'reports/panel',address=address)
    prepared=robot.prepare_robot_audio(job['name'])
    check_cancel(cancel)
    job.update(status='playback_attempting',playback_attempted=True,playback_transport='bluetooth')
    robot_speech.save_job(job)
    robot.armed=_PlaybackGuard(cancel)
    try:
        if pose is not None:
            from .pose_greetings import move_to_pose
            with robot.sequence():
                move_to_pose(robot,pose)
                result=robot.play_robot_audio(prepared)
        else:result=robot.play_robot_audio(prepared)
        job.update(status='playback_accepted',result=result)
    except Exception as exc:
        job.update(status='playback_uncertain',error=str(exc));raise
    finally:
        robot.disarm();robot_speech.save_job(job)
    return job


def speak_fresh(text,cancel,progress,*,reconnect_timeout=120,gesture=None,voice_settings=None):
    """Caller serializes UI operations and confirms USB/support before calling.

    Stop lets an in-progress card write finish to protect the filesystem, then
    prevents playback. No computer audio, reset command or playback retry.
    """
    text=spoken_sentence(text)
    if not bluetooth_address():raise ValueError('Configure the paired Bluetooth address before fresh speech.')
    check_cancel(cancel)
    progress('Generating a fresh one-sentence recording…')
    if voice_settings and voice_settings.get('voice')!='Local':
        from .expressive_voice import synthesize
        clip=synthesize(text,robot_speech.ROOT/'data/conversation-speech',**voice_settings)
    else:clip=speech.synthesize(text,robot_speech.ROOT/'data/conversation-speech')
    check_cancel(cancel)
    job=robot_speech.new_job(clip,text)
    job['temporary']=True
    if gesture and gesture.get('key'):
        import math
        seconds=clip.get('seconds')
        if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not 0<seconds<=180:
            raise ValueError('Recording duration is unavailable; paired upload stopped.')
        job['audio_seconds']=seconds
        paired_speech.attach(job,gesture['key'])
    robot_speech.save_job(job)
    progress('Uploading the fresh recording to Alpha…')
    robot_speech.prepare_upload(job,progress)
    check_cancel(cancel)
    wait_for_playback_interface(cancel,progress,reconnect_timeout)
    check_cancel(cancel)
    progress('Playing the new answer through Alpha’s speaker over Bluetooth…')
    if gesture and gesture.get('key'):
        result=play_paired(job,cancel,progress)
    elif gesture and gesture.get('profile'):
        result=play_uploaded(job,cancel,pose=gesture['profile']['pose'])
    else:result=play_uploaded(job,cancel)
    return {'message':'Bluetooth playback accepted. Reconnect USB before your next fresh answer.', 'job':result,'text':text}


def play_paired(job,cancel,progress=lambda message:None,*,replay=False):
    if alpha_usb_present():raise ValueError('Unplug USB before paired playback.')
    check_cancel(cancel)
    robot=BluetoothRobot(robot_speech.ROOT/'reports/panel',address=bluetooth_address())
    robot.armed=_PlaybackGuard(cancel)
    try:
        progress('Playing speech and the selected gesture together…')
        check_cancel(cancel)
        return paired_speech.play(robot,job,job.get('audio_seconds',job.get('probe_audio_seconds')),replay=replay)
    finally:robot.disarm()


def replay_saved(text,cancel,*,voice=None,style=None):
    """An explicit new user request may replay an exact verified recording."""
    from .greetings import saved_audio
    matches=[name for name,item in saved_audio().items() if item['text'].strip()==text.strip() and (voice is None or item.get('voice','Local')==voice) and (style is None or item.get('style','neutral')==style)]
    if not matches:raise ValueError('This message has not been uploaded. Connect USB to save it first.')
    if alpha_usb_present():raise ValueError('Unplug USB and leave it unplugged for Bluetooth playback.')
    check_cancel(cancel)
    address=bluetooth_address()
    if not address:raise ValueError('Configure the paired Bluetooth address first.')
    robot=BluetoothRobot(robot_speech.ROOT/'reports/panel',address=address)
    robot.armed=_PlaybackGuard(cancel)
    try:return robot.play_robot_audio(robot.prepare_robot_audio(matches[-1]))
    finally:robot.disarm()


def has_saved(text,voice,style,gesture=None):
    if gesture and gesture.get('key'):
        return paired_speech.find_saved(text,voice,style,gesture['key']) is not None
    from .greetings import saved_audio
    return any(item['text'].strip()==text.strip() and item.get('voice','Local')==voice and item.get('style','neutral')==style for item in saved_audio().values())

def replay_response(text,cancel,gesture,settings):
    """Explicit replay of matching uploaded speech, with an approved gesture."""
    if alpha_usb_present():raise ValueError('Unplug USB before Bluetooth replay.')
    if gesture and gesture.get('key'):
        job=paired_speech.find_saved(text,settings['voice'],settings['style'],gesture['key'])
        if job is None:raise ValueError('This speech-and-gesture pair needs a USB upload first.')
        result=play_paired(job,cancel,replay=True)
        return {'message':'Saved speech and gesture replayed together over Bluetooth.','job':result,'text':text}
    if not has_saved(text,settings['voice'],settings['style']):raise ValueError('Recording is no longer available; USB upload required.')
    check_cancel(cancel)
    robot=BluetoothRobot(robot_speech.ROOT/'reports/panel',address=bluetooth_address())
    robot.armed=_PlaybackGuard(cancel)
    try:
        if gesture and gesture.get('profile'):
            from .pose_greetings import move_to_pose
            move_to_pose(robot,gesture['profile']['pose'])
    finally:robot.disarm()
    check_cancel(cancel)
    replay_saved(text,cancel,voice=settings['voice'],style=settings['style'])
    return {'message':'Saved reply replayed over Bluetooth with the selected gesture. No new upload needed.','text':text}
