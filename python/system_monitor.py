import os
import time
import subprocess
import re
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ProcessMetrics:
    pid: int
    wall_time: float
    cpu_time: float
    user_time: float
    sys_time: float
    cpus_utilized: float
    threads: List[int]
    memory_mb: List[float]
    timestamps: List[float]

class LinuxMonitor:
    
    def __init__(self, pid: int):
        self.pid = pid
        self.metrics = ProcessMetrics(
            pid=pid,
            wall_time=0,
            cpu_time=0,
            user_time=0,
            sys_time=0,
            cpus_utilized=0,
            threads=[],
            memory_mb=[],
            timestamps=[]
        )
    
    def measure_with_perf(self, cmd: List[str], timeout: float = 30) -> Dict:
        print(f"[Perf] Measuring: {' '.join(cmd)}")
        
        perf_cmd = ["perf", "stat", "-o", f"/tmp/perf_{self.pid}.txt"] + cmd
        
        start_wall = time.time()
        
        try:
            proc = subprocess.Popen(
            perf_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
            )
            
            stdout, stderr = proc.communicate(timeout=timeout)
            returncode = proc.returncode
            
        except subprocess.TimeoutExpired:
            print(f"Timeout after {timeout}s")
            proc.terminate()
            
            try:
                proc.wait(timeout=2) 
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            
            return {
                'program_output': '',
                'program_stderr': f'TIMEOUT after {timeout}s',
                'return_code': -1
            }
        
        end_wall = time.time()
        
        perf_metrics = self._parse_perf_file(f"/tmp/perf_{self.pid}.txt")
        self.perf_metrics = perf_metrics 
        
        self.metrics.wall_time = end_wall - start_wall
        self.metrics.cpu_time = perf_metrics.get('total_cpu_time', 0)
        self.metrics.user_time = perf_metrics.get('user_time', 0)
        self.metrics.sys_time = perf_metrics.get('sys_time', 0)
        self.metrics.cpus_utilized = perf_metrics.get('cpus_utilized', 0)
        
        self._collect_live_metrics(proc.pid if hasattr(proc, 'pid') else None)
        
        return {
            'perf': perf_metrics,
            'program_output': stdout,
            'program_stderr': stderr,
            'return_code': returncode
        }
    
    def _parse_perf_file(self, filepath: str) -> Dict:
        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except:
            return {}
        
        metrics = {}
        
        patterns = {
            'cpus_utilized': r'([\d.]+)\s+CPUs utilized',
            'wall_time': r'([\d.]+)\s+seconds time elapsed',
            'user_time': r'([\d.]+)\s+seconds user',
            'sys_time': r'([\d.]+)\s+seconds sys',
            'task_clock': r'([\d,.]+)\s+msec\s+task-clock',
            'instructions': r'([\d,.]+)\s+instructions:u',
            'cycles': r'([\d,.]+)\s+cycles:u',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                value = match.group(1).replace(',', '')
                metrics[key] = float(value)
        
        if 'user_time' in metrics and 'sys_time' in metrics:
            metrics['total_cpu_time'] = metrics['user_time'] + metrics['sys_time']
        
        if 'wall_time' in metrics and 'total_cpu_time' in metrics:
            if metrics['wall_time'] > 0:
                metrics['parallelism'] = metrics['total_cpu_time'] / metrics['wall_time']
                metrics['cpu_efficiency'] = (metrics['total_cpu_time'] / metrics['wall_time']) * 100
        
        if 'cpus_utilized' in metrics:
            metrics['cpu_percent_single_core'] = metrics['cpus_utilized'] * 100
            
            try:
                import psutil
                total_cores = psutil.cpu_count(logical=True)
                metrics['cpu_percent_total'] = (metrics['cpus_utilized'] / total_cores) * 100
                metrics['system_cores'] = total_cores
            except:
                metrics['cpu_percent_total'] = 0
                metrics['system_cores'] = 'unknown'
        
        return metrics
    
    def _collect_live_metrics(self, pid: Optional[int] = None):
        if not pid:
            return
        
        start = time.time()
        samples = 0
        
        while samples < 10:
            try:
                with open(f"/proc/{pid}/stat", "r") as f:
                    stat = f.read().split()
                    if len(stat) > 19:
                        threads = int(stat[19])
                    else:
                        threads = 0
            
                memory_kb = 0
                try:
                    with open(f"/proc/{pid}/status", "r") as f:
                        for line in f:
                            if line.startswith("VmRSS:"):
                                try:
                                    memory_kb = int(line.split()[1])
                                except (ValueError, IndexError):
                                    pass
                                break
                except (FileNotFoundError, ProcessLookupError):
                    pass
                
                self.metrics.threads.append(threads)
                self.metrics.memory_mb.append(memory_kb / 1024 if memory_kb > 0 else 0)
                self.metrics.timestamps.append(time.time() - start)
                
                samples += 1
                time.sleep(0.1)
    
            except (FileNotFoundError, ProcessLookupError):
                break
            except Exception as e:
                print(f"[WARN] Error collecting metrics: {e}")
                samples += 1
                time.sleep(0.1)
                
    def get_summary(self) -> Dict:
        summary = {
            'wall_time': self.metrics.wall_time,
            'cpu_time': self.metrics.cpu_time,
            'user_time': self.metrics.user_time,
            'sys_time': self.metrics.sys_time,
            'cpus_utilized': self.metrics.cpus_utilized,
        }
        
        perf_metrics = self._parse_perf_file(f"/tmp/perf_{self.pid}.txt")
        
        if hasattr(self, 'perf_metrics') and self.perf_metrics:
            perf = self.perf_metrics
        
            if 'cpu_percent_single_core' in perf:
                summary['cpu_percent_single_core'] = perf['cpu_percent_single_core']
            
            if 'cpu_percent_total' in perf:
                summary['cpu_percent_total'] = perf['cpu_percent_total']
            
            if 'system_cores' in perf:
                summary['system_cores'] = perf['system_cores']
        
        if self.metrics.threads:
            summary['max_threads'] = max(self.metrics.threads)
            summary['avg_threads'] = sum(self.metrics.threads) / len(self.metrics.threads)
        
        if self.metrics.memory_mb:
            summary['max_memory_mb'] = max(self.metrics.memory_mb)
            summary['avg_memory_mb'] = sum(self.metrics.memory_mb) / len(self.metrics.memory_mb)
        
        if self.metrics.wall_time > 0 and self.metrics.cpu_time > 0:
            summary['parallelism'] = self.metrics.cpu_time / self.metrics.wall_time
            summary['cpu_efficiency'] = (self.metrics.cpu_time / self.metrics.wall_time) * 100
        
        return summary
    
    def _parse_perf_output_direct(self, perf_output: str) -> Dict:
        metrics = {}
        
        patterns = {
            'cpus_utilized': r'([\d.]+)\s+CPUs utilized',
            'user_time': r'([\d.]+)\s+seconds user',
            'sys_time': r'([\d.]+)\s+seconds sys',
            'task_clock': r'([\d,.]+)\s+msec\s+task-clock',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, perf_output)
            if match:
                value = match.group(1).replace(',', '')
                metrics[key] = float(value)
        
        if 'user_time' in metrics and 'sys_time' in metrics:
            metrics['total_cpu_time'] = metrics['user_time'] + metrics['sys_time']
        
        if 'cpus_utilized' in metrics:
            metrics['cpu_percent_single_core'] = metrics['cpus_utilized'] * 100
            
            try:
                import psutil
                total_cores = psutil.cpu_count(logical=True)
                metrics['cpu_percent_total'] = (metrics['cpus_utilized'] / total_cores) * 100
                metrics['system_cores'] = total_cores
            except:
                metrics['cpu_percent_total'] = 0
                metrics['system_cores'] = 'unknown'
        
        return metrics