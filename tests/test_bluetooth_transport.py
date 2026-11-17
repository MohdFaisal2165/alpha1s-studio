import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from alpha_demo.bluetooth_transport import BluetoothRobot,Session,encode

class WirelessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.robot=BluetoothRobot(self.tmp.name)
        self.robot.armed.set();self.robot.limits={i:(0,180) for i in range(1,17)}
    def tearDown(self):self.tmp.cleanup()
    def fake(self,replies):
        session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
        pending=iter(replies)
        def respond(command,params=b'\0'):
            if command==0x2a:return params+bytes.fromhex('15092501')
            value=next(pending)
            if isinstance(value,Exception):raise value
            return value
        session.exchange.side_effect=respond
        return session
    def test_verified_wire_frames(self):
        self.assertEqual(encode(1).hex(),'fbbf06010007ed')
        self.assertEqual(encode(0x21,b'\x01').hex(),'fbbf06210128ed')
    def test_pair_moves_without_read_or_legs(self):
        session=self.fake([b'\x01\x00',b'\x04\x00'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session),patch('alpha_demo.bluetooth_transport.time.sleep') as wait:
            result=self.robot.run_pair({1:90,4:100},support_confirmed=True)
        self.assertEqual(result['status'],'ok');self.assertIsNone(result['holding'])
        self.assertEqual([c.args for c in session.exchange.call_args_list if c.args[0]==0x22],[(0x22,bytes([1,90,100,0,100])),(0x22,bytes([4,100,100,0,100]))])
        wait.assert_called_once_with(3)
    def test_pair_fault_stops_second_motor(self):
        session=self.fake([b'\x01\x03'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session):
            result=self.robot.run_pair({1:90,4:100},support_confirmed=True)
        self.assertEqual(result['status'],'error');self.assertEqual(session.exchange.call_count,3)
        self.assertFalse(self.robot.armed.is_set());self.assertEqual(self.robot.targets,{})
        self.assertIn('no reply from servo',result['error'])
        self.assertIn('speech were not sent',result['error'])
        self.assertTrue(result['movement_unconfirmed'])
        self.assertEqual(result['attempted_target'],90)
        self.assertIn('may have moved',result['error'])
    def test_refresh_restores_read_angle(self):
        session=self.fake([b'\x06\x53',b'\x06\x00'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session),patch('alpha_demo.bluetooth_transport.time.sleep'):
            result=self.robot.run(6,setup=True,support_confirmed=True)
        self.assertEqual(result['baseline_degrees'],83)
        self.assertEqual(session.exchange.call_args_list[2].args,(0x22,bytes([6,83,100,0,100])))
    def test_invalid_read_does_not_move(self):
        session=self.fake([b'\x06\xff'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session):r=self.robot.run(6,setup=True,support_confirmed=True)
        self.assertEqual(r['status'],'error');self.assertEqual(session.exchange.call_count,2)
    def test_support_and_limits_before_connect(self):
        with patch('alpha_demo.bluetooth_transport.Session') as session:
            for call in (lambda:self.robot.run(1,181,support_confirmed=True),lambda:self.robot.run(1,90),lambda:self.robot.run(6,setup=True)):
                with self.assertRaises(ValueError):call()
            session.assert_not_called()
    def test_audio_uses_full_path_and_restores(self):
        session=self.fake([b'\x00']*3)
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session),patch('alpha_demo.bluetooth_transport.time.sleep'):
            self.robot.play_robot_audio(('SB223F2A',4))
        self.assertEqual([c.args for c in session.exchange.call_args_list],[(0x21,b'\x01'),(3,b'MUSIC/SB223F2A.MP3'),(0x21,b'\x00')])
        self.assertFalse(self.robot.recovery_path.exists())
    def test_audio_failure_restores_no_replay(self):
        session=self.fake([b'\x00',TimeoutError('missing'),b'\x00'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session):
            with self.assertRaises(TimeoutError):self.robot.play_robot_audio(('SB223F2A',4))
        self.assertEqual(session.exchange.call_count,3);self.assertFalse(self.robot.recovery_path.exists())
    def test_flag_rejection_never_plays(self):
        session=self.fake([b'\x01',b'\x00'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session):
            with self.assertRaises(ValueError):self.robot.play_robot_audio(('SB223F2A',4))
        self.assertEqual([c.args[0] for c in session.exchange.call_args_list],[0x21,0x21])
    def test_restore_failure_persists_block(self):
        session=self.fake([b'\x00',b'\x00',TimeoutError('missing')])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session),patch('alpha_demo.bluetooth_transport.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'restoration'):self.robot.play_robot_audio(('SB223F2A',4))
        self.assertTrue(self.robot.recovery_path.exists())
        with patch('alpha_demo.bluetooth_transport.Session') as second:
            self.assertEqual(self.robot.run()['status'],'error');second.assert_not_called()
    def test_socket_validates_fragmented_reply(self):
        sock=Mock();wire=encode(1,b'Alpha 1S');sock.recv.side_effect=[wire[:3],wire[3:]]
        log={'exchanges':[]};session=Session('address',log,lambda:None);session.sock=sock
        self.assertEqual(session.exchange(1),b'Alpha 1S')
    def test_socket_bad_checksum_rejected(self):
        sock=Mock();sock.recv.return_value=bytes.fromhex('fbbf06010008ed')
        session=Session('address',{'exchanges':[]},lambda:None);session.sock=sock
        with self.assertRaisesRegex(ValueError,'checksum'):session.exchange(1)

    def test_response_check_blocks_pair_before_any_move(self):
        session=self.fake([])
        session.exchange.side_effect=[bytes.fromhex('0115092501'),bytes.fromhex('0488888888')]
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session):
            result=self.robot.run_pair({1:90,4:90},support_confirmed=True)
        self.assertEqual(result['status'],'error')
        self.assertEqual([c.args[0] for c in session.exchange.call_args_list],[0x2a,0x2a])
        self.assertFalse(self.robot.armed.is_set())

    def test_response_check_blocks_release(self):
        session=self.fake([]);session.exchange.side_effect=[bytes.fromhex('0688888888')]
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session):
            result=self.robot.run(6,setup=True,support_confirmed=True)
        self.assertEqual(result['status'],'error')
        self.assertEqual([c.args[0] for c in session.exchange.call_args_list],[0x2a])

    def test_session_sets_settle_deadline_after_identity(self):
        session=Session('address',{'exchanges':[]},lambda:None)
        with patch('alpha_demo.bluetooth_transport.socket.socket'),patch.object(session,'exchange',side_effect=[b'Alpha 1S',b'2016070416',b'Alpha1_V2.0']),patch('alpha_demo.bluetooth_transport.time.monotonic',return_value=10):
            with session:self.assertEqual(session.servo_ready_at,11)

    def test_servo_wait_before_send_and_spacing_after_reply(self):
        session=Session('address',{'exchanges':[]},lambda:None)
        session.sock=Mock();session.sock.recv.return_value=encode(0x2a,bytes.fromhex('0115092501'))
        session.servo_ready_at=11
        events=[]
        session.sock.sendall.side_effect=lambda data:events.append('send')
        with patch('alpha_demo.bluetooth_transport.time.monotonic',return_value=10),patch('alpha_demo.bluetooth_transport.time.sleep',side_effect=lambda seconds:events.append(seconds)):
            self.assertEqual(session.exchange(0x2a,b'\x01'),bytes.fromhex('0115092501'))
        self.assertEqual(events,[1,'send'])
        self.assertEqual(session.servo_ready_at,10.2)

    def test_stop_during_settle_blocks_motor_write(self):
        session=Session('address',{'exchanges':[]},lambda:None);session.sock=Mock();session.servo_ready_at=11
        session.before_servo_write=self.robot.require_armed
        with patch('alpha_demo.bluetooth_transport.time.monotonic',return_value=10),patch('alpha_demo.bluetooth_transport.time.sleep',side_effect=lambda seconds:self.robot.disarm()):
            with self.assertRaisesRegex(ValueError,'Stopped'):session.exchange(0x22,bytes([1,100,100,0,100]))
        session.sock.sendall.assert_not_called()

    def test_sequence_keeps_one_connection_for_pairs_and_audio(self):
        session=self.fake([b'\x01\x00',b'\x04\x00',b'\x02\x00',b'\x05\x00',b'\x03\x00',b'\x06\x00',b'\x00',b'\x00',b'\x00'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session) as factory,patch('alpha_demo.bluetooth_transport.time.sleep'):
            with self.robot.sequence():
                for pair in ((1,4),(2,5),(3,6)):
                    self.assertEqual(self.robot.run_pair(dict.fromkeys(pair,90),support_confirmed=True)['status'],'ok')
                self.robot.play_robot_audio(('SB223F2A',4))
        factory.assert_called_once();session.__exit__.assert_called_once()
        self.assertIsNone(self.robot._sequence)

    def test_sequence_fault_closes_without_speech(self):
        session=self.fake([b'\x01\x03'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session) as factory:
            with self.assertRaisesRegex(ValueError,'no reply'):
                with self.robot.sequence():
                    result=self.robot.run_pair({1:90,4:90},support_confirmed=True)
                    if result['status']!='ok':raise ValueError(result['error'])
                    self.robot.play_robot_audio(('SB223F2A',4))
        factory.assert_called_once();session.__exit__.assert_called_once()
        self.assertIsNone(self.robot._sequence);self.assertFalse(self.robot.armed.is_set())
        self.assertNotIn(3,[c.args[0] for c in session.exchange.call_args_list])

class PersistentWirelessTests(unittest.TestCase):
    setUp=WirelessTests.setUp
    fake=WirelessTests.fake
    def tearDown(self):
        self.robot.disconnect();WirelessTests.tearDown(self)
    def test_connect_read_apply_share_one_session_until_disconnect(self):
        session=self.fake([b'\x03\x5a',b'\x03\x00',b'\x03\x00'])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session) as factory,patch('alpha_demo.bluetooth_transport.time.sleep'):
            self.assertEqual(self.robot.connect()['status'],'ok')
            self.assertTrue(self.robot.connected)
            self.assertEqual(self.robot.run(3,setup=True,support_confirmed=True)['status'],'ok')
            self.assertEqual(self.robot.run(3,95,support_confirmed=True)['status'],'ok')
            factory.assert_called_once();session.__exit__.assert_not_called()
            self.robot.disarm();self.assertTrue(self.robot.connected)
            self.robot.disconnect();session.__exit__.assert_called_once()
            self.assertFalse(self.robot.connected)
            self.assertFalse(self.robot.limits)
    def test_failure_closes_and_requires_explicit_connect(self):
        session=self.fake([TimeoutError('lost')])
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session) as factory:
            self.robot.connect()
            result=self.robot.run(3,90,support_confirmed=True)
            self.assertEqual(result['status'],'error');self.assertFalse(self.robot.connected)
            self.robot.armed.set();self.robot.limits[3]=(0,180)
            result=self.robot.run(3,90,support_confirmed=True)
            self.assertEqual(result['status'],'error');self.assertIn('Click Connect',result['error'])
            factory.assert_called_once()
    def test_all16_single_joint_requests_preserve_id_and_touch_no_other_motor(self):
        for sid in range(1,17):
            with self.subTest(sid=sid):
                self.robot.armed.set();self.robot.limits[sid]=(0,180)
                session=self.fake([bytes([sid,83]),bytes([sid,0]),bytes([sid,0])])
                with patch('alpha_demo.bluetooth_transport.Session',return_value=session),patch('alpha_demo.bluetooth_transport.time.sleep'):
                    self.robot.connect()
                    self.assertEqual(self.robot.run(sid,setup=True,support_confirmed=True)['status'],'ok')
                    self.assertEqual(self.robot.run(sid,100,support_confirmed=True)['status'],'ok')
                    for call in session.exchange.call_args_list:
                        self.assertIn(call.args[0],(0x2a,0x24,0x22))
                        self.assertEqual(call.args[1][0],sid)
                    self.robot.disconnect()
    def test_manual_connection_holds_exclusive_lock_between_operations(self):
        session=self.fake([])
        other=BluetoothRobot(self.tmp.name)
        with patch('alpha_demo.bluetooth_transport.Session',return_value=session) as factory:
            self.assertEqual(self.robot.connect()['status'],'ok')
            self.assertEqual(other.run()['status'],'error')
            factory.assert_called_once()
            self.robot.disconnect()
            self.assertEqual(other.run()['status'],'ok')
