import os
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import Future
import tkinter as tk
from alpha_demo.control_panel import ControlPanel
from alpha_demo.panel_transport import PanelRobot

class PanelUITests(unittest.TestCase):
    def setUp(self):
        vault=patch('alpha_demo.teacher_panel.TeacherPanel.key_action');vault.start();self.addCleanup(vault.stop)
        try:self.root=tk.Tk()
        except tk.TclError:self.skipTest('Desktop display unavailable')
        self.root.withdraw();self.tmp=tempfile.TemporaryDirectory()
        self.robot=PanelRobot(self.tmp.name);self.panel=ControlPanel(self.root,self.robot)
    def tearDown(self):
        if hasattr(self,'panel'):self.panel.close();self.tmp.cleanup()
    def test_four_workspaces_and_nested_limb_controls(self):
        self.assertEqual([self.panel.notebook.tab(t,'text') for t in self.panel.notebook.tabs()],['Pose Studio','Voice','Greetings','Conversation','Storage'])
        self.assertEqual(len(self.panel.joint_notebook.tabs()),4)
        for page in (self.panel.speech.page,self.panel.greetings.page,self.panel.teacher.page):
            self.panel.notebook.select(page);self.root.update()
            self.assertFalse(self.panel.motor_bar.winfo_manager())
        self.panel.notebook.select(self.panel.pose_page);self.root.update()
        self.assertEqual(self.panel.motor_bar.winfo_manager(),'pack')
    def test_each_button_routes_to_its_own_motor(self):
        self.panel.ready.set(True);self.panel.legs_ready.set(True);self.robot.armed.set()
        self.robot.limits={i:(0,180) for i in range(1,17)}
        self.panel.update_controls()
        for sid in range(1,17):
            self.panel.targets[sid].set(100)
            with patch.object(self.panel,'submit') as submit:
                self.panel.moves[sid].invoke()
                submit.assert_called_once_with(sid,100,support_confirmed=True)
                submit.reset_mock();self.panel.refreshes[sid].invoke()
                submit.assert_called_once_with(sid,setup=True,support_confirmed=True)
    def test_connect_stays_connected_during_request_and_enable_sends_nothing(self):
        from alpha_demo.bluetooth_transport import BluetoothRobot
        self.panel.robot=BluetoothRobot(self.tmp.name)
        self.panel.robot._connection=__import__('unittest.mock',fromlist=['MagicMock']).MagicMock()
        self.panel.checked=True;self.panel.ready.set(True)
        with patch.object(self.panel,'submit') as submit:
            self.panel.arm();submit.assert_not_called()
            self.assertTrue(self.panel.robot.armed.is_set())
            self.panel.future=Future();self.panel.update_controls()
            self.assertEqual(str(self.panel.check_button['state']),'normal')
            self.assertEqual(self.panel.check_button['text'],'Connected')
            self.panel.check();submit.assert_not_called()
            self.panel.future=None
        self.panel.disconnect_robot();self.assertFalse(self.panel.robot.connected)
        self.assertFalse(self.panel.checked)
    def test_all16_sliders_have_full_range_and_start_disarmed(self):
        self.assertEqual(set(self.panel.sliders),set(range(1,17)))
        for slider in self.panel.sliders.values():
            self.assertEqual(float(slider['from']),0);self.assertEqual(float(slider['to']),180)
        self.assertFalse(self.robot.armed.is_set())
        self.assertEqual(len(self.panel.scrollbars),4)
    def test_slider_does_not_send_commands(self):
        with patch.object(self.robot,'run') as run:
            self.panel.targets[3].set(150);self.panel.slider_changed(3,150)
            self.assertFalse(run.called)
    def test_leg_refresh_requires_support_check(self):
        self.robot.armed.set();self.panel.ready.set(True)
        with patch.object(self.panel,'submit') as submit,patch('alpha_demo.control_panel.messagebox.askokcancel',return_value=True):
            self.panel.refresh(16);self.assertFalse(submit.called)
            self.panel.legs_ready.set(True);self.panel.refresh(16)
            submit.assert_called_once_with(16,setup=True,support_confirmed=True)
    def test_measured_snapshot_is_not_replaced_by_target(self):
        self.robot.limits[3]=(0,180)
        def finish(result):
            f=Future();f.set_result(result);self.panel.future=f;self.panel.poll()
        finish({'status':'ok','servo':3,'holding':{'status_bytes_hex':'ffff0000'},'setup':True,'setup_limits':(0,180),'baseline_degrees':45,'measured_at':'2026-11-14T20:00:00+00:00','range_source':'Command range','move_acknowledged':True,'target':45})
        self.assertIn('45°',self.panel.measure_labels[3].get())
        finish({'status':'ok','servo':3,'holding':{'status_bytes_hex':'ffff0000'},'setup':False,'move_acknowledged':True,'target':90})
        self.assertIn('45°',self.panel.measure_labels[3].get())
        self.assertIn('STALE',self.panel.measure_labels[3].get())
        self.assertIn('90°',self.panel.last_labels[3].get())
    def test_conversation_placeholder_and_session_scrollbar(self):
        panel=self.panel.teacher
        self.assertEqual(panel.question.get(),'')
        self.assertEqual(panel.placeholder.winfo_manager(),'place')
        panel.question.set('Hello')
        self.assertFalse(panel.placeholder.winfo_manager())
        self.assertEqual(panel.transcript_scroll.winfo_manager(),'pack')
        self.assertEqual(str(panel.mic_button['image']),str(panel.mic_image))
        panel.toggle_settings();panel.toggle_settings()
    def test_transcription_populates_input_without_asking(self):
        panel=self.panel.teacher;panel.mode='transcribe'
        panel.future=Future();panel.future.set_result('Hello Alpha')
        with patch.object(panel,'ask') as ask,patch.object(panel,'perform') as perform:
            panel.poll()
            self.assertEqual(panel.question.get(),'Hello Alpha')
            ask.assert_not_called();perform.assert_not_called()
    def test_all_left_mirrors_preserve_targets_and_limits(self):
        for sid in (4,5,6):
            self.panel.targets[sid].set(130)
            self.robot.limits[sid]=(20,150)
        with patch.object(self.robot,'run') as run:
            for enabled in (True,False):
                self.panel.mirrored.set(enabled);self.panel.mirror_changed()
                for sid in (4,5,6):
                    self.assertEqual(self.panel.raw_angle(sid,self.panel.targets[sid].get()),130)
                    self.assertEqual(self.robot.limits[sid],(20,150))
                    self.assertEqual(float(self.panel.sliders[sid]['from']),30 if enabled else 20)
            run.assert_not_called()
    def test_pose_busy_feedback_and_completion_survive_invalidation(self):
        greeting=self.panel.greetings
        greeting.future=Future();greeting.mode='pose';greeting.started=__import__('time').monotonic()
        self.panel.greeting_active=True;self.panel.update_controls()
        self.assertEqual(str(self.panel.play_pose_button['state']),'disabled')
        greeting.messages.put('Moving arm pair 2 & 5…');greeting.poll()
        self.assertEqual(self.panel.status.get(),'Moving arm pair 2 & 5…')
        greeting.begin('pose',lambda: self.fail('Busy job must not run'))
        self.assertIn('wait',self.panel.status.get())
        greeting.future.set_result({});greeting.poll()
        self.assertIn('Saved pose commands accepted',self.panel.status.get())
        self.assertEqual(str(self.panel.play_pose_button['state']),'normal')
    def test_mirror_preserves_raw_target_and_sends_nothing(self):
        self.panel.targets[4].set(135)
        with patch.object(self.robot,'run') as run:
            self.panel.mirrored.set(True);self.panel.mirror_changed()
            self.assertEqual(self.panel.targets[4].get(),45)
            self.assertEqual(self.panel.raw_angle(4,45),135)
            self.assertEqual(self.panel.raw_angle(4,0),180)
            self.assertEqual(self.panel.raw_angle(4,180),0)
            self.assertEqual(self.panel.raw_angle(3,45),45)
            self.assertEqual(self.panel.raw_angle(1,45),45)
            self.assertEqual(self.panel.raw_angle(6,45),135)
            self.assertEqual(self.panel.raw_angle(4,90),90)
            run.assert_not_called()
    def test_fault_invalidates_every_motor(self):
        self.robot.limits={i:(0,180) for i in range(1,17)}
        self.robot.positions={3:{'angle':45}};self.robot.targets={3:45}
        self.robot.armed.set()
        f=Future();f.set_result({'status':'error','servo':1,'error':'Reply EE'})
        self.panel.future=f;self.panel.poll()
        self.assertFalse(self.robot.armed.is_set());self.assertFalse(self.robot.limits)
        self.assertFalse(self.robot.positions);self.assertFalse(self.robot.targets)
        self.assertIn('FAULT',self.panel.status.get())
        with patch.object(self.robot,'run') as run:
            self.panel.reset_panel();run.assert_not_called()
        self.assertIn('Reset complete',self.panel.status.get())
    def test_overdue_keeps_worker_and_blocks_new_requests(self):
        f=Future();self.panel.future=f;self.panel.started=0
        self.robot.armed.set();self.panel.poll()
        self.assertIs(self.panel.future,f);self.assertFalse(self.robot.armed.is_set())
        with patch.object(self.panel.pool,'submit') as submit:
            self.panel.submit();submit.assert_not_called()
        f.set_result({'status':'ok'})
        self.panel.poll()
        self.assertTrue(self.panel.fault);self.assertFalse(self.robot.limits)

    def test_apply_and_read_use_no_confirmation_popups(self):
        self.robot.armed.set();self.panel.ready.set(True)
        self.robot.limits[4]=(0,180)
        self.panel.mirrored.set(True);self.panel.targets[4].set(45)
        with patch.object(self.panel,'submit') as submit,patch('alpha_demo.control_panel.messagebox.askokcancel',side_effect=AssertionError('Unexpected popup')):
            self.panel.move(4);submit.assert_called_once_with(4,135,support_confirmed=True)
            submit.reset_mock();self.panel.refresh(4)
            submit.assert_called_once_with(4,setup=True,support_confirmed=True)
    def test_invalid_target_stays_inline_and_never_submits(self):
        self.robot.armed.set();self.panel.ready.set(True);self.robot.limits[3]=(0,180)
        self.panel.targets[3].set(181)
        with patch.object(self.panel,'submit') as submit,patch('alpha_demo.control_panel.messagebox.showerror',side_effect=AssertionError('Unexpected popup')):
            self.panel.move(3);submit.assert_not_called()
        self.assertIn('Invalid target',self.panel.status.get())
    def test_single_angle_distinguishes_measurement_from_command(self):
        self.panel.measured[4]=(135,'2026-11-15T12:00:00+00:00')
        self.panel.update_angle(4)
        self.assertIn('135°',self.panel.angle_labels[4].get())
        self.assertIn('measured at',self.panel.angle_labels[4].get())
        self.panel.mirrored.set(True);self.panel.update_angle(4)
        self.assertIn('45° (raw 135°)',self.panel.angle_labels[4].get())
        self.panel.acknowledged[4]=120;self.panel.dirty.add(4);self.panel.update_angle(4)
        self.assertIn('60° (raw 120°)',self.panel.angle_labels[4].get())
        self.assertIn('position unverified',self.panel.angle_labels[4].get())
        self.panel.reset_panel();self.assertIn('not read',self.panel.angle_labels[4].get())
    def test_checkbox_hover_is_readable_and_title_is_simple(self):
        from tkinter import ttk
        style=ttk.Style(self.root)
        for states in [('active',),('active','selected'),('selected',),()]:
            self.assertNotEqual(style.lookup('TCheckbutton','background',states),style.lookup('TCheckbutton','foreground',states))
            self.assertEqual(style.lookup('TCheckbutton','foreground',states),'#ffffff' if 'active' in states else '#e5edf8')
        self.assertEqual(self.root.title(),'Alpha 1S Studio -Pose, Voice, Greeting and Conversation')
    def test_speech_tab_never_calls_robot_or_plays_on_startup(self):
        self.assertEqual(self.panel.notebook.tab(1,'text'),'Voice')
        self.assertEqual(str(self.panel.speech.reconnect['state']),'disabled')
        self.assertFalse(self.panel.speech.active)
        with patch.object(self.robot,'run') as run:
            self.panel.notebook.select(1);self.panel.scroll(1,None)
            self.panel.speech.text.insert('end',' New greeting.')
            self.root.update();run.assert_not_called()
    def test_speech_edit_invalidates_old_clip(self):
        speech=self.panel.speech
        speech.generated_text=speech.current_text();speech.clip={'mp3':'old.mp3'}
        speech.text.insert('end',' changed');speech.edited()
        self.assertIsNone(speech.clip)

    def test_speech_locks_motor_controls_and_releases_on_finish(self):
        speech=self.panel.speech;self.panel.ready.set(True)
        speech.acquire()
        self.assertTrue(self.panel.speech_active)
        with patch.object(self.panel.pool,'submit') as submit:
            self.panel.submit();submit.assert_not_called()
        self.assertEqual(str(self.panel.check_button['state']),'disabled')
        speech.phase='reconnect';speech.finish()
        self.assertFalse(self.panel.speech_active)
        self.assertFalse(self.robot.lock.locked())

    def test_send_requires_support_and_never_opens_popup(self):
        with patch.object(self.panel.speech.pool,'submit') as submit:
            self.panel.speech.send();submit.assert_not_called()
        self.assertIn('Supported',self.panel.speech.status.get())

    def test_upload_and_playback_transitions_are_inline(self):
        speech=self.panel.speech;self.panel.ready.set(True);speech.acquire()
        speech.phase='upload';speech.future=Future()
        speech.future.set_result(({'name':'S123ABCD','playback_attempted':False},{'mp3':'test'}))
        speech.poll()
        self.assertEqual(speech.phase,'reconnect')
        self.assertEqual(str(speech.reconnect['state']),'normal')
        self.assertTrue(speech.active)
        speech.phase='play';speech.future=Future();speech.future.set_result({})
        speech.poll()
        self.assertFalse(speech.active)
        self.assertIn('Playback accepted',speech.status.get())


    def test_greeting_has_three_primary_actions_and_inline_feedback(self):
        greeting=self.panel.greetings
        self.assertIn('Record pose',greeting.record_button['text'])
        self.assertIn('Save greeting',greeting.save_button['text'])
        self.assertIn('Play greeting',greeting.play['text'])
        self.assertFalse(hasattr(greeting,'options'))
        greeting.pose=None
        with patch.object(greeting.pool,'submit') as submit:
            greeting.save();submit.assert_not_called()
        self.assertIn('Pose Studio',greeting.status.get())

    def test_record_requires_support_and_never_silently_fails(self):
        greeting=self.panel.greetings;self.panel.ready.set(False)
        with patch.object(greeting.pool,'submit') as submit:
            greeting.record();submit.assert_not_called()
        self.assertIn('supported',greeting.status.get())

    def test_capture_completion_updates_pose_and_unlocks_controls(self):
        greeting=self.panel.greetings;greeting.mode='record';greeting.started=0
        greeting.future=Future();greeting.future.set_result({str(i):90 for i in range(1,7)})
        self.panel.greeting_active=True;greeting.poll()
        self.assertEqual(greeting.pose['6'],90)
        self.assertIn('Save greeting',greeting.status.get())
        self.assertFalse(self.panel.greeting_active);self.assertFalse(self.robot.armed.is_set())

    def test_changed_message_cannot_play_old_audio(self):
        greeting=self.panel.greetings
        greeting.profiles={'f':{'name':'Faisal','text':'old','pose':{'1':90},'audio':'FAISAL01'}}
        greeting.pose={'1':90};greeting.text.delete('1.0','end');greeting.text.insert('1.0','new')
        with patch.object(greeting.pool,'submit') as submit:
            greeting.execute();submit.assert_not_called()
        self.assertIn('Save greeting',greeting.status.get())

    def test_greeting_blocks_motor_and_speech_requests(self):
        self.panel.greeting_active=True;self.panel.ready.set(True);self.panel.update_controls()
        with patch.object(self.panel.pool,'submit') as submit:
            self.panel.submit();submit.assert_not_called()
        with self.assertRaises(ValueError):self.panel.speech.acquire()
        self.panel.greeting_active=False

    def test_greeting_scroll_and_simple_layout(self):
        self.panel.notebook.select(2);self.root.update()
        self.assertFalse(self.panel.motor_bar.winfo_manager())
        self.assertFalse(self.panel.robot_sidebar.winfo_manager())
        with patch.object(self.panel.greetings.canvas,'yview_scroll') as greeting_scroll:
            self.panel.scroll(1,None);greeting_scroll.assert_called_once_with(1,'units')
        self.panel.notebook.select(0);self.root.update()
        self.assertEqual(self.panel.motor_bar.winfo_manager(),'pack')

    def test_failed_record_does_not_save_partial_pose(self):
        greeting=self.panel.greetings;greeting.mode='record';greeting.pose=None
        greeting.future=Future();greeting.future.set_exception(ValueError('joint read failed'))
        greeting.poll();self.assertIsNone(greeting.pose)
        self.assertIn('joint read failed',greeting.status.get())

    def test_stop_disarms_remaining_pose_commands(self):
        self.robot.armed.set();self.panel.greetings.stop()
        self.assertFalse(self.robot.armed.is_set())

    def test_greetings_default_is_available_speaker(self):
        greeting=self.panel.greetings
        self.assertEqual(greeting.speaker.get(),'Robot speaker — Bluetooth')
        self.assertEqual(tuple(greeting.speaker_box['values']),('Robot speaker — Bluetooth',))

    def test_play_failure_keeps_saved_profile_and_shows_recovery(self):
        greeting=self.panel.greetings
        profile={'name':'Faisal','text':'Hello','pose':{str(i):90 for i in range(1,7)},'audio':'a'}
        greeting.profiles={'f':profile};greeting.person.set('Faisal');greeting.load_person()
        greeting.mode='play';greeting.future=Future()
        greeting.future.set_exception(ValueError('Motor 1 did not confirm (0xEE).'))
        greeting.poll()
        self.assertEqual(greeting.profiles['f'],profile)
        self.assertEqual(greeting.pose,profile['pose'])
        self.assertIn('Saved greetings are unchanged',greeting.status.get())

    def test_switch_to_bluetooth_updates_greeting_without_io(self):
        from alpha_demo.bluetooth_transport import BluetoothRobot
        with patch('alpha_demo.bluetooth_transport.Session') as session:
            self.panel.connection.set('Bluetooth');self.panel.change_connection()
            self.assertIsInstance(self.panel.robot,BluetoothRobot)
            self.assertEqual(self.panel.greetings.speaker.get(),'Robot speaker — Bluetooth')
            self.assertFalse(self.panel.robot.armed.is_set());session.assert_not_called()
    def test_cannot_switch_transport_while_armed(self):
        old=self.panel.robot;old.armed.set()
        self.panel.connection.set('Bluetooth');self.panel.change_connection()
        self.assertIs(self.panel.robot,old);self.assertEqual(self.panel.connection.get(),'USB')
    def test_wireless_speech_upload_is_explicitly_blocked(self):
        self.panel.connection.set('Bluetooth');self.panel.change_connection()
        with patch.object(self.panel.speech.pool,'submit') as submit:
            self.panel.speech.send();submit.assert_not_called()
        self.assertTrue(any(word in self.panel.speech.status.get() for word in ('USB','Supported')))
