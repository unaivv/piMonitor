import json
import subprocess

import psutil

_SYSTEM_PREFIXES = (
    "systemd-", "dbus", "getty@", "serial-getty@", "user@",
    "apt-", "dpkg", "man-db", "e2scrub", "logrotate",
    "fstrim", "ifupdown", "keyboard-setup", "kmod",
    "networking", "triggerhappy", "raspi-config", "wpa_supplicant",
    "ModemManager", "avahi-daemon", "bluetooth",
)

_STATUS_ORDER = {"failed": 0, "inactive": 1, "active": 2}


def get_cpu() -> float:
    return psutil.cpu_percent(interval=1)


def get_ram() -> dict:
    ram = psutil.virtual_memory()
    return {
        "total_gb": round(ram.total / (1024 ** 3), 2),
        "used_gb": round(ram.used / (1024 ** 3), 2),
        "free_gb": round(ram.available / (1024 ** 3), 2),
        "percent": ram.percent,
    }


def get_disk(path: str) -> dict:
    disk = psutil.disk_usage(path)
    return {
        "total_gb": round(disk.total / (1024 ** 3), 2),
        "used_gb": round(disk.used / (1024 ** 3), 2),
        "free_gb": round(disk.free / (1024 ** 3), 2),
        "percent": disk.percent,
    }


def get_temperature() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except OSError:
        return None


def get_services(watched: list[str] | None = None) -> list[dict]:
    try:
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all",
             "--output=json", "--no-pager"],
            capture_output=True, text=True, timeout=10,
        )
        units = json.loads(result.stdout)
    except Exception:
        return []

    services = []
    for u in units:
        if u.get("load") != "loaded":
            continue
        name = u["unit"].removesuffix(".service")
        if watched:
            if name not in watched:
                continue
        else:
            if any(name.startswith(p) for p in _SYSTEM_PREFIXES):
                continue
        services.append({
            "name": name,
            "active": u["active"],        # active | inactive | failed
            "sub": u["sub"],              # running | stopped | dead | exited | failed
            "description": u["description"],
        })

    return sorted(
        services,
        key=lambda s: (_STATUS_ORDER.get(s["active"], 3), s["name"]),
    )


def collect(disk_configs: list[dict]) -> dict:
    metrics: dict = {
        "cpu_percent": get_cpu(),
        "ram": get_ram(),
        "disks": {},
        "temperature": get_temperature(),
    }
    for disk in disk_configs:
        try:
            metrics["disks"][disk["name"]] = get_disk(disk["path"])
        except Exception as exc:
            metrics["disks"][disk["name"]] = {"error": str(exc)}
    return metrics
