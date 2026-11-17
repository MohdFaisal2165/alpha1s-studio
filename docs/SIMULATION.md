# Alpha 1S digital twin: development plan

The next development phase connects Studio's pose workflow to a calibrated Alpha 1S model in NVIDIA Isaac Sim. The intended workflow is **design → preview → validate → approve → execute**.

The dedicated [simulation workspace](../simulation/README.md) provides the Docker configuration and manual launch commands.

## First milestone: a reproducible simulation workspace

Use the official `nvcr.io/nvidia/isaac-sim:6.2.0` container as the initial evaluation target. Pin the tested image digest when establishing the reproducible environment. Keep the simulator's caches, assets and outputs in a dedicated workspace with its own container name and ports.

Review NVIDIA's license and version-specific prerequisites before downloading and running the image. Schedule GPU work around existing simulation workloads. Begin with a compatibility check, then a single robot scene.

The candidate robot model is [andresjjn/alpha1s-ros2-twin](https://github.com/andresjjn/alpha1s-ros2-twin), reviewed at commit `c5d53fef8aa06c96a6c5bbccba55919e637902b4`. Preserve upstream attribution and license when incorporating assets. Resolve its mesh paths, expand the xacro description and import the resulting URDF into USD using the selected Isaac Sim version's importer.

## Joint calibration

Create an explicit mapping for each physical motor: controller ID, simulator joint name, axis direction, angular offset and calibrated movement limits. Studio's physical numbering groups arms as 1–6 and legs as 7–16. Verify each mapping against the real robot before enabling hardware execution. Hold the candidate model's virtual neck fixed to represent the physical 16-motor configuration.

Use named fields and explicit units in exported pose data. Convert display mirroring into controller angles before applying the simulator mapping. Store the calibration version alongside each trajectory.

## Incremental milestones

1. **Model inspection:** display the robot, check scale, joint axes and mesh alignment, and move one simulated joint at a time.
2. **Studio pose replay:** export saved poses and timed transitions into the simulator; compare the resulting posture with the operator's observations.
3. **Collision preview:** evaluate body clearance throughout each transition and report the joint/link pairs involved. Validate warnings using measured robot geometry and conservatively spaced poses.
4. **Supervised execution:** send reviewed trajectories through Studio's existing transport and operator-readiness controls. Record requested angles, acknowledgments, timing and available measured snapshots separately.
5. **Learning experiments:** introduce Isaac Lab for supported arm gestures or trajectory optimization after calibrating the model and actuator response. Select a compatible Isaac Lab version at that stage.

## Acceptance evidence

Record the container image digest, upstream asset revision, calibration, simulator settings and example pose files. For each milestone, retain reproducible launch steps, an offline demonstration and measured results. Evaluate simulation-to-hardware agreement with joint error and timing measurements; assess control latency before introducing continuous real-time tracking.

## References

- [NVIDIA Isaac Sim 6.2 container installation](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_container.html)
- [NVIDIA Isaac Sim 6.2 requirements](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/requirements.html)
- [Isaac Lab asset import workflow](https://isaac-sim.github.io/IsaacLab/main/source/how-to/import_new_asset.html)
- [Alpha 1S ROS 2 digital twin](https://github.com/andresjjn/alpha1s-ros2-twin)
