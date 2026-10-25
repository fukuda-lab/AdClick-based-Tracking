import os
import time
import psutil


def cleanup_driver(driver=None, driver_path=None, timeout=5):
    my_pid = os.getpid()

    if driver is not None:
        try:
            driver.quit()
        except Exception as e:
            pass
    time.sleep(1)

    def get_driver_children():
        try:
            parent = psutil.Process(my_pid)

            result = []

            for p in parent.children(recursive=True):
                try:
                    cmdline = p.cmdline()
                    cmd = " ".join(cmdline).lower()
                    name = (p.name() or "").lower()
                    if ("chromedriver" in name or "chromedriver" in cmd or name == "chrome" or "/chrome" in cmd):
                        result.append(p)
                except (psutil.NoSuchProcess,psutil.AccessDenied,):
                    pass
            return result
        except (psutil.NoSuchProcess,psutil.AccessDenied,):
            return []

    children = get_driver_children()
    for p in children:
        try:
            if p.status() == psutil.STATUS_ZOMBIE:
                continue
            p.terminate()
        except (psutil.NoSuchProcess,psutil.AccessDenied,):
            pass

    if children:
        _, alive = psutil.wait_procs(children, timeout=timeout,)
    else:
        alive = []
    for p in alive:
        try:
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                p.kill()

        except (psutil.NoSuchProcess,psutil.AccessDenied,):
            pass
    reaped = []

    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            reaped.append(pid)

        except ChildProcessError:
            break

        except OSError:
            break
    remaining_zombies = []

    try:
        parent = psutil.Process(my_pid)

        for p in parent.children(recursive=True):
            try:
                if p.status() == psutil.STATUS_ZOMBIE:
                    remaining_zombies.append(p.pid)

            except (psutil.NoSuchProcess,psutil.AccessDenied,):
                pass

    except (psutil.NoSuchProcess,psutil.AccessDenied,):
        pass

    if driver_path:
        try:
            if os.path.exists(driver_path):
                os.remove(driver_path)
                print(f"[CLEANUP] Removed {driver_path}",flush=True,)

        except Exception as e:
            print(f"[CLEANUP] Cannot remove {driver_path}: {e}",flush=True,)