import psutil
import time
import csv
import datetime
import argparse
import signal
import sys

PORT_SERVICE_MAP = {
    "model": [5001],
    "plotting": [5003],
}

DEFAULT_OUT = "msa_metrics.csv"  

def find_pids_by_port(port):
    """Find PIDs listening on a given port (macOS-safe, no sudo needed)."""
    pids = set()
    for proc in psutil.process_iter(["pid"]):
        try:
            # use the modern method name
            for conn in proc.net_connections(kind="inet"):
                if (
                    conn.laddr
                    and conn.laddr.port == port
                    and conn.status == psutil.CONN_LISTEN
                ):
                    pids.add(proc.pid)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return sorted(pids)


def find_processes_by_pid_or_children(root_pids):
    seen = {}
    queue = list(root_pids)
    while queue:
        pid = queue.pop()
        if pid in seen: 
            continue
        try:
            p = psutil.Process(pid)
            seen[pid] = p
            # include children (recursively), in case of gunicorn workers, etc.
            for c in p.children(recursive=True):
                if c.pid not in seen:
                    queue.append(c.pid)
        except psutil.NoSuchProcess:
            pass
    return list(seen.values())


def main():
    parser = argparse.ArgumentParser(description="Monitor CPU and memory usage.")
    parser.add_argument("--pid", type=int, nargs="*", default=[], help="One or more root PIDs to monitor")
    parser.add_argument("--port", type=int, nargs="*", help="Find and monitor processes listening on these TCP ports")
    parser.add_argument("--interval", type=float, default=0.5,
                        help="Sampling interval in seconds")
    parser.add_argument("--out", type=str, default=DEFAULT_OUT,
                        help="Output CSV filename (base name when using multiple ports)")
    parser.add_argument("--pid-port-map", type=str, help="Comma-separated port:pid pairs, e.g., '5001:1234,5003:5678'")
    args = parser.parse_args()

    targets = []
    pid_to_port = {}
    pid_to_service = {}
    port_to_processes = {}  # NEW: group processes by port

    if args.pid:
        # NEW: Parse pid-port mapping if provided
        if args.pid_port_map:
            for pair in args.pid_port_map.split(','):
                parts = pair.split(':')
                port = int(parts[0])
                # Handle multiple PIDs - split by both : and newlines
                pid_str = ':'.join(parts[1:])
                pids = [int(p.strip()) for p in pid_str.replace('\n', ':').split(':') if p.strip()]
                
                service = None
                for svc_name, ports in PORT_SERVICE_MAP.items():
                    if port in ports:
                        service = svc_name
                        break
                if service is None:
                    service = f"port{port}"
                
                if port not in port_to_processes:
                    port_to_processes[port] = []
                
                for pid in pids:  # FIXED: Loop through all PIDs for this port
                    pid_to_port[pid] = port
                    pid_to_service[pid] = service
        
        for pid in args.pid:
            try:
                p = psutil.Process(pid)
                targets.append(p)
                if pid not in pid_to_service:
                    pid_to_service[pid] = "pid_input"
                if args.pid_port_map and pid in pid_to_port:
                    port_to_processes[pid_to_port[pid]].append(p)
            except psutil.NoSuchProcess:
                print(f"[WARN] PID {pid} not found")
    elif args.port:
        # Find target processes and group by port
        for port in args.port:
            service = PORT_SERVICE_MAP.get(port, f"port{port}")
            root_pids = find_pids_by_port(port)
            procs = find_processes_by_pid_or_children(root_pids)
            port_to_processes[port] = []  # NEW
            for p in procs:
                pid_to_port[p.pid] = port
                pid_to_service[p.pid] = service
                port_to_processes[port].append(p)  # NEW
                targets.append(p)
        
        # De-duplicate
        uniq = {}
        for p in targets:
            if p.pid not in uniq:
                uniq[p.pid] = p
        targets = list(uniq.values())

    if not targets:
        print(f"[WARN] No process found. Monitoring only system-wide metrics.")
    else:
        print(f"[INFO] Monitoring {len(targets)} process(es): {[p.pid for p in targets]}")

    # NEW: Determine if we need multiple CSV files
    use_multiple_files = args.pid_port_map and len(port_to_processes) > 1
    
    if use_multiple_files:
        # Create one CSV file per port
        base_name = args.out.rsplit('.', 1)[0] if '.' in args.out else args.out
        extension = args.out.rsplit('.', 1)[1] if '.' in args.out else 'csv'
        
        csv_files = {}
        csv_writers = {}
        
        for port in sorted(port_to_processes.keys()):
            filename = f"{base_name}_{port}.{extension}"
            csv_files[port] = open(filename, "w", newline="")
            csv_writers[port] = csv.writer(csv_files[port])
            csv_writers[port].writerow([
                "timestamp",
                "cpu_total_percent",
                "mem_total_percent",
                "port",
                "service",
                "pid",
                "proc_cpu_percent",
                "proc_mem_mb"
            ])
            print(f"[INFO] Writing port {port} metrics to: {filename}")
    else:
        # Single CSV file (original behavior)
        csv_files = {None: open(args.out, "w", newline="")}
        csv_writers = {None: csv.writer(csv_files[None])}
        csv_writers[None].writerow([
            "timestamp",
            "cpu_total_percent",
            "mem_total_percent",
            "port",
            "service",
            "pid",
            "proc_cpu_percent",
            "proc_mem_mb"
        ])

    # Initialize
    psutil.cpu_percent(None)
    for p in targets:
        try:
            p.cpu_percent(None)
        except psutil.NoSuchProcess:
            pass

    def stop_handler(sig, frame):
        print("\n[INFO] Monitoring stopped.")
        for f in csv_files.values():
            f.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    # Main loop
    try:
        while True:
            ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
            total_cpu = psutil.cpu_percent(None)
            total_mem = psutil.virtual_memory().percent

            if targets:
                for p in list(targets):
                    try:
                        proc_cpu = p.cpu_percent(None)
                        proc_mem = p.memory_info().rss / (1024 * 1024)
                        port = pid_to_port.get(p.pid, "")
                        service = pid_to_service.get(p.pid, "")
                        
                        # NEW: Write to appropriate CSV file
                        if use_multiple_files:
                            writer = csv_writers.get(port)
                            if writer:
                                writer.writerow([ts, total_cpu, total_mem, port, service, p.pid, proc_cpu, proc_mem])
                        else:
                            csv_writers[None].writerow([ts, total_cpu, total_mem, port, service, p.pid, proc_cpu, proc_mem])
                    except psutil.NoSuchProcess:
                        targets.remove(p)
            else:
                # Write system-wide metrics to single file
                if use_multiple_files:
                    for writer in csv_writers.values():
                        writer.writerow([ts, total_cpu, total_mem, "", "", "", "", ""])
                else:
                    csv_writers[None].writerow([ts, total_cpu, total_mem, "", "", "", "", ""])

            for f in csv_files.values():
                f.flush()
            time.sleep(args.interval)
    finally:
        for f in csv_files.values():
            f.close()


if __name__ == "__main__":
    main()
