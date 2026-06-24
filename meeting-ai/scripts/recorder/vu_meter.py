"""
VU-метры для отображения уровня звука в реальном времени.
Поддержка двух каналов (ПК + микрофон).
"""
import math

# ANSI цвета
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"
BLINK = "\033[5m"


def vu_meter_bar(level: float, width: int = 30) -> str:
    """Рисует один ASCII VU-метр"""
    filled = int(level * width)

    bar = ""
    for i in range(width):
        if i < filled:
            ratio = i / width
            if ratio < 0.6:
                bar += f"{GREEN}█{RESET}"
            elif ratio < 0.85:
                bar += f"{YELLOW}█{RESET}"
            else:
                bar += f"{RED}█{RESET}"
        else:
            bar += f"{DIM}░{RESET}"

    db = -60 if level < 0.001 else int(20 * math.log10(max(level, 1e-10)))
    db_str = f"{db:>4} dB"

    return f"{bar} {db_str}"


def dual_vu_meter(pc_level: float, mic_level: float, width: int = 25) -> str:
    """
    Рисует два VU-метра для ПК и микрофона.
    Возвращает строку для вывода.
    """
    pc_bar = vu_meter_bar(pc_level, width)
    mic_bar = vu_meter_bar(mic_level, width)

    return (
        f"  {CYAN}ПК{RESET}  {pc_bar}\n"
        f"  {CYAN}МИК{RESET} {mic_bar}"
    )


def format_duration(seconds: float) -> str:
    """Форматирование длительности"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"