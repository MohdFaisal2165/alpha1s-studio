# Alpha 1S simulation workspace

This Docker Compose configuration prepares a dedicated Isaac Sim development environment for the [digital-twin milestones](../docs/SIMULATION.md). Status: configuration prepared; GPU compatibility and asset import are the next scheduled checks.

## Separation from existing projects

- Compose project: `alpha1s-studio-sim`, with project-scoped volumes and a separate bridge network.
- Isaac Sim version: `6.2.0`; Python and simulator dependencies live in the container.
- Dedicated caches, logs, configuration and generated data live in named Docker volumes.
- `workspace/` supplies read-only input assets and scripts. Generated assets can be saved under `/isaac-sim/.local/share/ov/data/alpha1s` and copied out with `docker cp` using the Alpha container ID.
- CPU allocation is capped at 6 cores and RAM at 16 GiB. GPU selection defaults to device 0 and can be changed with `ALPHA_SIM_GPU_ID`.
- Startup is manual. The configuration exposes zero host ports and mounts only this workspace plus project volumes. Robot device access remains in Studio.

GPU compute and VRAM remain shared host resources: Docker separation does not reserve exclusive GPU capacity or cap GPU memory. Run compatibility checks and simulations only during an agreed idle window or on a separate GPU host. Existing drivers, Docker services and other simulation containers stay as configured.

## Validate configuration now

From this directory:

```bash
./sim.sh validate
```

This parses configuration without downloading images or starting containers.

## First scheduled GPU session

Review the [NVIDIA container instructions and license](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_container.html). After accepting the terms and arranging GPU availability:

```bash
export ALPHA_SIM_ACCEPT_EULA=Y
export ALPHA_SIM_GPU_READY=1
./sim.sh check
./sim.sh shell
```

The first run downloads the image. A successful compatibility check should report `System checking result: PASSED`. Confirm the dedicated data directory is writable before importing assets. Record the resolved image digest and compatibility result with the experiment.

The manual profile opens a development shell. Build and inspect the Alpha model in a headless scene first; choose a separately reviewed display/streaming configuration when interactive viewing is needed.

## Candidate model

Use [andresjjn/alpha1s-ros2-twin](https://github.com/andresjjn/alpha1s-ros2-twin) at revision `c5d53fef8aa06c96a6c5bbccba55919e637902b4` as the initial model candidate. Preserve its license and attribution. Follow the calibration and joint-mapping steps in the roadmap before connecting simulation output to hardware.
