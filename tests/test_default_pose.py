import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from alpha_demo import default_pose
class DefaultTests(unittest.TestCase):
    def test_capture_all_measured_values(self):
        robot=Mock();robot.armed.is_set.return_value=True
        robot.run.side_effect=[{'status':'ok','baseline_degrees':70+i} for i in range(16)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result=default_pose.capture(robot,supported=True,legs_unloaded=True,root=root)
            self.assertEqual(default_pose.load(root),result['pose']);self.assertEqual(result['pose']['16'],85)
            self.assertEqual(robot.run.call_count,16)
    def test_support_required_and_partial_failure_preserves_default(self):
        robot=Mock();robot.armed.is_set.return_value=True
        with self.assertRaises(ValueError):default_pose.capture(robot,supported=True)
        robot.run.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir();path=root/'data/default-pose.json';path.write_text('previous')
            robot.run.side_effect=[{'status':'ok','baseline_degrees':90},{'status':'error','error':'No reply'}]
            with self.assertRaises(ValueError):default_pose.capture(robot,supported=True,legs_unloaded=True,root=root)
            self.assertEqual(path.read_text(),'previous')
    def test_full_body_pose_checks_all_limits_before_any_motion(self):
        from alpha_demo.pose_greetings import move_to_pose
        robot=Mock();robot.armed.is_set.return_value=True;robot.saved_limits={16:(80,100)};robot.limits={}
        pose={str(i):90 for i in range(1,17)};pose['16']=110
        with self.assertRaises(ValueError):move_to_pose(robot,pose)
        robot.run_pair.assert_not_called();robot.run.assert_not_called()
    def test_full_body_pose_applies_approved_targets_without_generated_angles(self):
        from alpha_demo.pose_greetings import move_to_pose
        robot=Mock();robot.armed.is_set.return_value=True;robot.saved_limits={};robot.limits={}
        robot.run_pair.return_value={'status':'ok'};robot.run.return_value={'status':'ok'}
        pose={str(i):90 for i in range(1,17)}
        move_to_pose(robot,pose)
        self.assertEqual(robot.run_pair.call_count,3);self.assertEqual(robot.run.call_count,10)
