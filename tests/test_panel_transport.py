import json
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from alpha_demo.panel_transport import PanelRobot,move_packet

PAD=lambda x:bytes.fromhex(x).ljust(64,b'\0')
HW=PAD('f11f0b416c706861315f56322e3067ed')
STATUS=PAD('effeffff0000feed')
ACK=PAD('f44faaed')
MOVE=PAD('faaf0301aa000000aeed')

def framed(data):
    b=bytes(data)
    return (b'\xfa\xaf'+b+bytes([sum(b)&255,237])).ljust(64,b'\0')

class PanelTransportTests(unittest.TestCase):
    def test_all16_command_ranges(self):
        for sid in range(1,17):
            for angle in (0,90,180):
                b=move_packet(sid,angle)
                self.assertEqual(b[2],sid);self.assertEqual(b[4],angle)
                self.assertEqual(b[8],sum(b[2:8])&255)
        for sid,angle in ((0,90),(17,90),(3,-1),(6,181),(True,90),(3,90.0)):
            with self.assertRaises(ValueError):move_packet(sid,angle)
        with self.assertRaises(ValueError):move_packet(7,90,{7:(-1,181)})

    def run_fake(self,action,replies):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'hidraw7';p.mkdir();(p/'dev').write_text('239:7')
            robot=PanelRobot(Path(d)/'logs');robot.armed.set();robot.limits={3:(0,180)}
            writes=[]
            def write(fd,b):writes.append(b[1:11]);return len(b)
            with patch('alpha_demo.panel_transport.find_device',return_value=p), \
                 patch('alpha_demo.panel_transport.os.open',return_value=99), \
                 patch('alpha_demo.panel_transport.os.fstat',return_value=SimpleNamespace(st_mode=stat.S_IFCHR,st_rdev=__import__('os').makedev(239,7))), \
                 patch('alpha_demo.panel_transport.fcntl.flock'), \
                 patch('alpha_demo.panel_transport.os.close'), \
                 patch('alpha_demo.panel_transport.os.write',side_effect=write), \
                 patch('alpha_demo.panel_transport.os.read',side_effect=replies), \
                 patch('alpha_demo.panel_transport.select.select',side_effect=lambda r,w,e,t: (r,[],[]) if t==2 else ([],[],[])), \
                 patch('alpha_demo.panel_transport.time.sleep'):
                result=action(robot)
            return result,writes,robot

    def test_no_release_during_normal_move(self):
        r,w,_=self.run_fake(lambda x:x.run(3,90),[HW,STATUS,ACK,MOVE,STATUS,ACK])
        self.assertEqual(r['status'],'ok')
        self.assertEqual(sum(b[:2]==b'\xfa\xaf' and b[3]==1 for b in w),1)
        self.assertFalse(any(b[:2]==b'\xfa\xaf' and b[3]==2 for b in w))

    def test_failure_never_retries(self):
        r,w,robot=self.run_fake(lambda x:x.run(3,90),[HW,STATUS,ACK,bytes(64),ACK])
        self.assertEqual(r['status'],'error');self.assertFalse(robot.armed.is_set())
        self.assertEqual(sum(b[:2]==b'\xfa\xaf' and b[3]==1 for b in w),1)

    def test_disabled_joint_blocks_motion(self):
        disabled=PAD('effefbff0000faed')
        r,w,_=self.run_fake(lambda x:x.run(3,90),[HW,disabled])
        self.assertEqual(r['status'],'error')
        self.assertFalse(any(b[:2]==b'\xfa\xaf' for b in w))

    def test_setup_restores_same_position_then_limits_range(self):
        read=framed([1,170,0,90,0,89]);move=framed([1,1,170,0,0,0])
        r,w,robot=self.run_fake(lambda x:x.run(1,setup=True,support_confirmed=True),[HW,STATUS,ACK,read,move,STATUS,ACK])
        self.assertEqual(r['status'],'ok');self.assertEqual(robot.limits[1],(0,180))
        moves=[b for b in w if b[:2]==b'\xfa\xaf' and b[3]==1]
        self.assertEqual(len(moves),1);self.assertEqual(moves[0][4],89)

    def test_failed_setup_does_not_enable_motor(self):
        r,w,robot=self.run_fake(lambda x:x.run(1,setup=True,support_confirmed=True),[HW,STATUS,ACK,bytes(64),ACK])
        self.assertEqual(r['status'],'error');self.assertNotIn(1,robot.limits)
        self.assertFalse(any(b[:2]==b'\xfa\xaf' and b[3]==1 for b in w))

    def test_support_confirmation_required_before_open(self):
        with tempfile.TemporaryDirectory() as d:
            robot=PanelRobot(d);robot.armed.set();robot.limits[7]=(0,180)
            with patch('alpha_demo.panel_transport.find_device') as find:
                with self.assertRaises(ValueError):robot.run(7,90)
                with self.assertRaises(ValueError):robot.run(7,setup=True)
                self.assertFalse(find.called)

    def test_leg_refresh_restores_measured_angle_and_enables_full_slider(self):
        read=framed([16,170,0,100,0,99]);move=framed([16,1,170,0,0,0])
        r,w,robot=self.run_fake(lambda x:x.run(16,setup=True,support_confirmed=True),[HW,STATUS,ACK,read,move,STATUS,ACK])
        self.assertEqual(r['status'],'ok');self.assertEqual(robot.limits[16],(0,180))
        self.assertEqual(robot.positions[16]['angle'],99)
        self.assertEqual(robot.targets[16],99)
        self.assertIn('measured_at',r)

    def test_measurement_not_overwritten_by_target(self):
        def action(robot):
            robot.positions[3]={'angle':45,'at':'old'}
            return robot.run(3,90)
        r,w,robot=self.run_fake(action,[HW,STATUS,ACK,MOVE,STATUS,ACK])
        self.assertEqual(robot.positions[3]['angle'],45)
        self.assertEqual(robot.targets[3],90)

    def test_saved_limits_do_not_restore_stale_position(self):
        with tempfile.TemporaryDirectory() as d:
            logdir=Path(d)/'logs';robot=PanelRobot(logdir)
            robot.positions[1]={'angle':90,'at':'old'};robot.limits[1]=(0,180)
            robot.set_limits(1,20,160)
            restarted=PanelRobot(logdir)
            self.assertEqual(restarted.saved_limits[1],(20,160))
            self.assertEqual(restarted.limits,{})
            self.assertEqual(restarted.positions,{})

    def test_disarmed_and_unmeasured_joint_refused(self):
        with tempfile.TemporaryDirectory() as d:
            robot=PanelRobot(d)
            with patch('alpha_demo.panel_transport.find_device') as find:
                with self.assertRaises(ValueError):robot.run(3,90)
                robot.armed.set()
                with self.assertRaises(ValueError):robot.run(3,90)
                self.assertFalse(find.called)

    def test_pair_sends_both_before_one_settle_and_disconnect(self):
        def action(robot):
            robot.limits[6]=(0,180)
            with patch('alpha_demo.panel_transport.time.sleep') as settle:
                result=robot.run_pair({3:100,6:80},support_confirmed=True)
                settle.assert_called_once_with(3)
            return result
        r,w,robot=self.run_fake(action,[HW,STATUS,ACK,MOVE,framed([6,1,170,0,0,0]),STATUS,ACK])
        self.assertEqual(r['status'],'ok')
        self.assertEqual([b[2] for b in w if b[:2]==b'\xfa\xaf'],[3,6])
        self.assertEqual([b[:2] for b in w],[b'\xf1\x1f',b'\xef\xfe',b'\xf4\x4f',b'\xfa\xaf',b'\xfa\xaf',b'\xef\xfe',b'\xf4\x4f'])
        self.assertEqual(robot.targets,{3:100,6:80})

    def test_pair_failed_first_ack_blocks_second_motor(self):
        def action(robot):
            robot.limits[6]=(0,180)
            return robot.run_pair({3:100,6:80},support_confirmed=True)
        r,w,robot=self.run_fake(action,[HW,STATUS,ACK,bytes(64),ACK])
        self.assertEqual(r['status'],'error');self.assertFalse(robot.armed.is_set())
        self.assertEqual([b[2] for b in w if b[:2]==b'\xfa\xaf'],[3])

    def test_pair_validates_both_targets_before_device_open(self):
        with tempfile.TemporaryDirectory() as d:
            robot=PanelRobot(d);robot.armed.set();robot.limits={3:(0,180),6:(0,100)}
            with patch('alpha_demo.panel_transport.find_device') as find:
                for targets,support in (({3:90,6:120},True),({1:90,6:90},True),({3:90,6:90},False)):
                    with self.assertRaises(ValueError):robot.run_pair(targets,support_confirmed=support)
                find.assert_not_called()
