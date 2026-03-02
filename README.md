# DBG_threads - Multi-threaded Program Monitor & Analyzer

Automated system for testing and monitoring multi-threaded C++ programs with performance metrics collection, deadlock detection, and data race detection.


## Quick Start

```bash
git clone https://github.com/Potato3852/DBG_threads
cd DBG_threads
chmod +x run.sh
```

## Run all files in cpp/ with default settings (4 threads)
```bash
./run.sh
```

## Run with N threads(for example 12)
```bash
./run.sh 12
```

## Run specific file(choose your files after number of threads in <name> or <name>.cpp format)
```bash
./run.sh 8 race_demo
./run.sh 4 normal.cpp deadlock_demo.cpp
```

## Smart compilation - recompiles only when source changes

### Performance metrics via perf stat:

- Wall time & CPU time

- CPUs utilized & Parallelism

- Thread efficiency (% of theoretical max)

- CPU usage (% of single core & total system)

### Deadlock detection - monitors /proc/[pid]/task/ states

- Detects in ~1.5 seconds

- 3 consecutive checks = confirmed deadlock

### Others:

- Data race detection - analyzes program output

- Flexible execution - run all files or specific ones

- Progress visualization - real-time monitoring with progress bars

-Auto-reports - saved in results/report.txt

## Example Output
```bash
=== Running: Race Condition Demo ===
Shell PID: 140890
Target PID (race_demo): 140891
Program finished normally

Results:
--------------------------------------------------
Wall time:                37.943 s
CPU time:                 325.597 s
CPUs utilized:            8.64 cores
Parallelism:              8.58x
Thread efficiency:        71.5% of 12 threads
CPU usage:                864.1% of 1 core
CPU load (1 core):        864.1%
System usage:             72.0% of 12 cores

Detections:              🔴 DATA RACE 
--------------------------------------------------
```
# Dataset
We use dataset from https://github.com/JaKooLit/Wallpaper-Bank/
Thank you a lot!!!

# FAQ
Q: Why no metrics for deadlock_demo?
A: The program terminates too quickly (~1.5s). Perf needs minimum time to collect accurate metrics.

Q: How to add my own demo?
A: Just add a .cpp file to the cpp/ folder. It should accept thread count as first argument.

Q: Why does it say "Very low CPU usage"?
A: This is a warning when a program runs >3s but uses <5% CPU - could indicate inefficiency or deadlock.

Author`s comment: The file system_monitor.py is not in use now, because I switched to a simpler solution, but I left it as a memento of the previous Legacy version.

# Contributing
Created by:
- Potato3852 
- klayyy122
- my brother DeepSeek.
