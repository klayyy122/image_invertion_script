import subprocess
import time
from pathlib import Path
import argparse
import sys
import os
import signal
from typing import Optional

class ProgressBar:
    
    @staticmethod
    def show(iteration, total, prefix='', suffix='', length=50, fill='X'):
        percent = ("{0:.1f}").format(100 * (iteration / float(total)))
        filled_length = int(length * iteration // total)
        bar = fill * filled_length + 'o' * (length - filled_length)
        
        sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
        sys.stdout.flush()
        
        if iteration == total: 
            sys.stdout.write('\n')
    
    @staticmethod
    def animate_loading(text="loading", duration=1):
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        
        end_time = time.time() + duration
        i = 0
        
        while time.time() < end_time:
            sys.stdout.write(f"\r{text} {frames[i % len(frames)]}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
        
        sys.stdout.write(f"\r{text} ✅\n")
        sys.stdout.flush()

class SimpleController:
    def __init__(self, threads=4, specific_files=None):
        self.threads = threads
        self.base_dir = Path(__file__).parent.parent
        self.build_dir = self.base_dir / "build"
        self.results_dir = self.base_dir / "results"
        
        self.build_dir.mkdir(exist_ok=True)
        self.results_dir.mkdir(exist_ok=True)
        
        self.files_to_compile = self._discover_demos(specific_files)
        
    def _discover_demos(self, specific_files=None):
        cpp_dir = self.base_dir / "cpp"
        files_to_compile = []
        
        if specific_files:
            for file_name in specific_files:
                cpp_file = cpp_dir / f"{file_name}.cpp"
                if cpp_file.exists():
                    files_to_compile.append({
                        'name': file_name.replace('_', ' ').title(),
                        'program': self.build_dir / file_name,
                        'source': cpp_file,
                        'args': [str(self.threads)]
                    })
                else:
                    print(f"File not found: {cpp_file}")
        else:
            for cpp_file in cpp_dir.glob("*.cpp"):
                if cpp_file.name.startswith("stb_"):
                    continue
                    
                file_name = cpp_file.stem
                files_to_compile.append({
                    'name': file_name.replace('_', ' ').title(),
                    'program': self.build_dir / file_name,
                    'source': cpp_file,
                    'args': [str(self.threads)]
                })
        
        print(f"Found {len(files_to_compile)} file(s): {[d['name'] for d in files_to_compile]}")
        return files_to_compile
    
    def compile_cpp(self):
        print(f"Compile {len(self.files_to_compile)} .cpp file(s) for {self.threads} threads")
        
        if not self.files_to_compile:
            print("No demos to compile!")
            return
        
        total_files = len(self.files_to_compile)
        compiled_count = 0
        skipped_count = 0
        
        for i, file in enumerate(self.files_to_compile, 1):
            source_path = file['source']
            target_path = file['program']
            
            need_compile = True
            
            if target_path.exists():
                if target_path.stat().st_mtime > source_path.stat().st_mtime:
                    need_compile = False
                    status = "UP-TO-DATE, skipping...."
                    skipped_count += 1
                else:
                    status = "REBUILD (source newer)"
            else:
                status = "COMPILE (no executable)"
            
            ProgressBar.show(i, total_files, prefix='Progress:', suffix=f'{source_path.name} -> {target_path.name}\n')
            
            if not need_compile:
                continue 
            
            cmd = [
                'g++',
                '-std=c++17',
                '-pthread',
                '-O2',
                '-o',
                str(target_path),
                str(source_path)
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"Successfully compiled: {target_path.name}")
                else:
                    print(f"Compile error in {target_path.name}:")
                    print(result.stderr)
                
            except Exception as e:
                print(f"Exception compiling {target_path.name}: {e}")
                
        print(f"Compilation summary:")
        print(f"Total files: {total_files}")
        print(f"Compiled: {compiled_count}")
        print(f"Skipped (up-to-date): {skipped_count}\n")
                
    def check_deadlock_by_thread_states(self, pid: int) -> bool:
        try:
            task_dir = f"/proc/{pid}/task"
            if not os.path.exists(task_dir):
                return False
            
            thread_states = []
            
            for tid in os.listdir(task_dir):
                status_file = os.path.join(task_dir, tid, "status")
                
                if os.path.exists(status_file):
                    with open(status_file, 'r') as f:
                        for line in f:
                            if line.startswith("State:"):
                                state = line.split()[1]
                                thread_states.append(state)
                                break
            
            if not thread_states:
                return False

            all_blocked = all(state in ['D', 'S'] for state in thread_states)
            return all_blocked
            
        except Exception as e:
            print(f"Error checking thread states: {e}")
            return False
    
    def run_single_demo(self, file, demo_num, total_demo):
        print(f"\n=== Running: {file['name']} ===")

        if not file['program'].exists():
            print("Executable not found")
            return None
        
        cmd = [str(file['program'])] + file['args']
        
        BASE_TIMEOUT = 300 # if your programm slower than 5 minutes - fuck you!!!
        
        shell_cmd = ' '.join(cmd)
        perf_cmd = ["perf", "stat", "sh", "-c", shell_cmd]
        
        start_time = time.time()
        
        try:
            proc = subprocess.Popen(
                perf_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid
            )
            
            pid = proc.pid
            print(f"Shell PID: {pid}")
            
            target_pid = None
            time.sleep(0.3)
            
            target_pid = self._find_child_pid_simple(pid, file['program'].name)
            
            if target_pid:
                print(f"Target PID ({file['program'].name}): {target_pid}")
            else:
                print(f"Could not find target PID, using shell PID")
                target_pid = pid
            
            deadlock_detected = False
            timeout_occurred = False
            
            last_check_time = 0
            consecutive_deadlock_checks = 0
            
            while True:
                if proc.poll() is not None:
                    print("Program finished normally")
                    break
                
                elapsed = time.time() - start_time
                if elapsed > BASE_TIMEOUT:
                    print(f"Global timeout ({BASE_TIMEOUT}s) reached")
                    timeout_occurred = True
                    break
                
                current_time = time.time()
                if current_time - last_check_time > 0.5:
                    last_check_time = current_time
                    
                    if target_pid and self.check_deadlock_by_thread_states(target_pid):
                        consecutive_deadlock_checks += 1
                        print(f"Threads blocked ({consecutive_deadlock_checks}/3 checks)")
                        
                        if consecutive_deadlock_checks >= 3:
                            print("🔴 DEADLOCK DETECTED! Terminating...")
                            deadlock_detected = True
                            break
                    else:
                        consecutive_deadlock_checks = 0
                
                time.sleep(0.3)
            
            if deadlock_detected or timeout_occurred:
                print("Terminating entire process group...")
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    time.sleep(0.5)
                    
                    if proc.poll() is None:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    
                    proc.wait(timeout=2)
                    print("Process group terminated successfully")
                except Exception as e:
                    print(f"Error killing process group: {e}")

                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            
            stdout, stderr = proc.communicate()
            return_code = proc.returncode
            
            if deadlock_detected:
                return_code = -1
            elif timeout_occurred:
                return_code = -2
            
            runtime = time.time() - start_time
            
            perf_output = stderr
            perf_metrics = self._parse_perf_output(perf_output)
            
            output = stdout + stderr
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        wall_time = runtime
        cpu_utilized = perf_metrics.get('cpus_utilized', 0) if perf_metrics else 0
        
        # Final deadlock check
        
        if not deadlock_detected:
            if wall_time > 10.0 and cpu_utilized < 0.1:
                print(f"DEADLOCK DETECTED BY METRICS!")
                print(f"Reason: worked {wall_time:.1f}s but used only {cpu_utilized:.2f} cores")
                deadlock_detected = True
            
            if "DEADLOCK" in output:
                print(f"DEADLOCK DETECTED BY OUTPUT")
                deadlock_detected = True
            
            if timeout_occurred and cpu_utilized < 0.2:
                print(f"DEADLOCK DETECTED BY TIMEOUT + LOW CPU")
                deadlock_detected = True
        
        data_race_detected = "DATA RACE" in output or "race" in output.lower()
        
        # Show Metrics
        print(f"\nResults:")
        print("-"*50)
        
        print(f"{'Wall time:':<25} {wall_time:.3f} s")
        
        if perf_metrics and 'cpus_utilized' in perf_metrics:
            cpu_time = perf_metrics.get('cpu_time', 0)
            print(f"{'CPU time:':<25} {cpu_time:.3f} s")
            
            cpus_used = cpu_utilized
            print(f"{'CPUs utilized:':<25} {cpus_used:.2f} cores")
            
            if wall_time > 0 and cpu_time > 0:
                parallelism = cpu_time / wall_time
                print(f"{'Parallelism:':<25} {parallelism:.2f}x")
                
                if self.threads > 0:
                    efficiency = (parallelism / self.threads) * 100
                    print(f"{'Thread efficiency:':<25} {efficiency:.1f}% of {self.threads} threads")
            
            cpu_percent = cpu_utilized * 100
            print(f"{'CPU usage:':<25} {cpu_percent:.1f}% of 1 core")
            
            if wall_time > 3.0 and cpu_percent < 5.0 and not deadlock_detected:
                print(f"{'Warning:':<25} Very low CPU usage ({cpu_percent:.1f}%)")
        
        if 'cpu_percent_single_core' in perf_metrics:
            print(f"{'CPU load (1 core):':<25} {perf_metrics['cpu_percent_single_core']:.1f}%")
        
        if 'cpu_percent_total' in perf_metrics and 'system_cores' in perf_metrics:
            print(f"{'System usage:':<25} {perf_metrics['cpu_percent_total']:.1f}% of {perf_metrics['system_cores']} cores")
        
        print(f"\n{'Detections:':<25}", end="")
        if data_race_detected:
            print("🔴 DATA RACE", end=" ")
        if deadlock_detected:
            print("🔴 DEADLOCK", end=" ")
        if timeout_occurred and not deadlock_detected:
            print("⏰ TIMEOUT", end=" ")
        if not data_race_detected and not deadlock_detected and not timeout_occurred:
            print("✅ OK", end="")
        print()
        
        print("-"*50)
        
        return {
            'name': file['name'],
            'exit_code': return_code,
            'stdout': stdout,
            'stderr': stderr,
            'runtime': wall_time,
            'metrics': perf_metrics,
            'deadlock': deadlock_detected,
            'data_race': data_race_detected,
            'timeout': timeout_occurred
        }

    def _find_child_pid_simple(self, parent_pid: int, program_name: str) -> Optional[int]:
        try:
            children_path = f"/proc/{parent_pid}/task/{parent_pid}/children"
            
            if os.path.exists(children_path):
                with open(children_path, 'r') as f:
                    content = f.read().strip()
                
                if content:
                    child_pids = [pid for pid in content.split() if pid]
                    
                    for child_pid in child_pids:
                        cmdline_path = f"/proc/{child_pid}/cmdline"
                        if os.path.exists(cmdline_path):
                            with open(cmdline_path, 'r', encoding='utf-8', errors='ignore') as f:
                                cmdline = f.read().replace('\x00', ' ')
                            
                            if program_name in cmdline:
                                return int(child_pid)
        
        except (FileNotFoundError, PermissionError, ValueError):
            pass
        
        try:
            result = subprocess.run(
                ['ps', '-o', 'pid=', '--ppid', str(parent_pid)],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode == 0:
                child_pids = [pid.strip() for pid in result.stdout.split('\n') if pid.strip()]
                
                for child_pid in child_pids:
                    result2 = subprocess.run(
                        ['ps', '-p', child_pid, '-o', 'cmd='],
                        capture_output=True,
                        text=True,
                        timeout=1
                    )
                    
                    if result2.returncode == 0 and program_name in result2.stdout:
                        return int(child_pid)
        
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return None
                    
    def _parse_perf_output(self, perf_output: str) -> dict:
        import re
        
        metrics = {
            'cpus_utilized': 0,
            'cpu_time': 0,
            'user_time': 0,
            'sys_time': 0,
            'total_cpu_time': 0,
            'wall_time': 0
        }
        
        patterns = {
            'cpus_utilized': r'([\d.]+)\s+CPUs  CPUs_utilized',
            'user_time': r'([\d.]+)\s+seconds user',
            'sys_time': r'([\d.]+)\s+seconds sys',
            'wall_time': r'([\d.]+)\s+seconds time elapsed',
            'task_clock': r'([\d,.]+)\s+msec\s+task-clock',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, perf_output)
            if match:
                value = match.group(1).replace(',', '')
                try:
                    metrics[key] = float(value)
                except:
                    pass
        
        if metrics['user_time'] > 0 or metrics['sys_time'] > 0:
            metrics['total_cpu_time'] = metrics['user_time'] + metrics['sys_time']
            metrics['cpu_time'] = metrics['total_cpu_time']
        
        if metrics['wall_time'] > 0 and metrics['cpu_time'] > 0:
            metrics['parallelism'] = metrics['cpu_time'] / metrics['wall_time']
        
        if metrics['cpus_utilized'] > 0:
            metrics['cpu_percent_single_core'] = metrics['cpus_utilized'] * 100
            
            try:
                import psutil
                total_cores = psutil.cpu_count(logical=True)
                metrics['system_cores'] = total_cores
                metrics['cpu_percent_total'] = (metrics['cpus_utilized'] / total_cores) * 100
            except:
                metrics['cpu_percent_total'] = 0
                metrics['system_cores'] = 'unknown'
        
        return metrics
             
    def run_all_demos(self):
        print("Run all demos")
        
        results = []
        total_demos = len(self.files_to_compile)
        
        for i, file in enumerate(self.files_to_compile, 1):
            ProgressBar.show(i, total_demos, prefix='[System] Progress:', suffix=f'Demo {i}/{total_demos}')
            
            result = self.run_single_demo(file, i, total_demos)
            if result:
                results.append(result)
                
            if i < total_demos:
                time.sleep(1)
            
        return results
    
    def generate_report(self, results):
        print("=== Report ===")
        
        report_path = self.results_dir / "report.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("Report\n")
            f.write("Theme: Threads\n")
            f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*50 + "\n\n")
            
            for result in results:
                f.write(f"Demo: {result['name']}\n")
                f.write(f"Status: {'SUCCESS' if result['exit_code'] == 0 else 'ERROR'}\n")
                
                metrics = result.get('metrics', {})
                
                if 'wall_time' in metrics:
                    f.write(f"Wall time: {metrics['wall_time']:.3f}s\n")
                
                if 'cpu_time' in metrics:
                    f.write(f"CPU time: {metrics['cpu_time']:.3f}s\n")
                
                if 'cpus_utilized' in metrics:
                    f.write(f"CPUs utilized: {metrics['cpus_utilized']:.2f}\n")
                
                if 'parallelism' in metrics:
                    f.write(f"Parallelism: {metrics['parallelism']:.2f}x\n")
                
                if 'max_threads' in metrics:
                    f.write(f"Max threads: {metrics['max_threads']}\n")
                
                output = result['stdout'] + result['stderr']
                if "DATA RACE" in output:
                    f.write("Detected data race\n")
                if "DEADLOCK" in output:
                    f.write("Detected deadlock\n")
                if "No data race" in output:
                    f.write("Okay\n")
                
                f.write("\n")
        
        print(f"Report was seved in: {report_path}")
        
        print("\nResults:")
        for result in results:
            status = "okay" if result.get('exit_code') == 0 else "bad"
            name = result.get('name', 'Unknown')

            duration = result.get('metrics', {}).get('wall_time', 0)

            cpu_info = ""
            if 'cpus_utilized' in result.get('metrics', {}):
                cpu_info = f", CPU: {result['metrics']['cpus_utilized']:.1f} cores"
            
            print(f"{status} {name:25} {duration:6.2f}s{cpu_info}")        
            
    def main(self):
        self.compile_cpp()
        
        results = self.run_all_demos()
        
        if results:
            self.generate_report(results)
        
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--threads', '-t', type=int, default=4, help='Number of threads(default: 4)')
    parser.add_argument('--file', '-f', action='append', help='Specific .cpp file to run (without .cpp extension)')
    parser.add_argument('--compile-only', action='store_true', help='Only compile, don\'t run')
    
    args = parser.parse_args()
    
    controller = SimpleController(threads=args.threads, specific_files=args.file)
    controller.compile_cpp()
    
    if not args.compile_only:
        results = controller.run_all_demos()
        
        if results:
            controller.generate_report(results)
            
if __name__ == "__main__":
    main()