import logging
import requests

logger = logging.getLogger(__name__)


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(self, message: str) -> None:
        try:
            resp = requests.post(
                self._url,
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)

    def format_alert(self, label: str, value: float, threshold: float, unit: str = "%") -> str:
        return (
            f"🚨 <b>piMonitor — Alerta</b>\n"
            f"<b>{label}</b>: {value}{unit} (límite: {threshold}{unit})\n"
            f"Verificá el estado de tu Raspberry Pi."
        )

    def format_status(self, metrics: dict) -> str:
        lines = ["📊 <b>Estado Raspberry Pi</b>\n"]
        lines.append(f"🖥️ CPU: {metrics['cpu_percent']}%")

        ram = metrics["ram"]
        lines.append(f"🧠 RAM: {ram['percent']}% — {ram['used_gb']}/{ram['total_gb']} GB")

        for name, disk in metrics["disks"].items():
            if "error" in disk:
                lines.append(f"💾 {name}: ⚠️ {disk['error']}")
            else:
                lines.append(
                    f"💾 {name}: {disk['percent']}% — {disk['free_gb']} GB libres de {disk['total_gb']} GB"
                )

        if metrics["temperature"] is not None:
            lines.append(f"🌡️ Temperatura: {metrics['temperature']}°C")

        return "\n".join(lines)
