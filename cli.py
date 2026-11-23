#!/usr/bin/env python3
"""Color terminal setup wizard for GuardBot."""
from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV_FILE = BASE / ".env"

C = {
    "reset": "\033[0m", "bold": "\033[1m", "cyan": "\033[96m",
    "blue": "\033[94m", "green": "\033[92m", "yellow": "\033[93m",
    "red": "\033[91m", "purple": "\033[95m", "dim": "\033[2m",
}


def color(name: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return C.get(name, "") + text + C["reset"]


def banner() -> None:
    os.system("clear" if os.name == "posix" else "cls")
    print(color("cyan", r"""
╔══════════════════════════════════════════════════════════════╗
║  ██████╗ ██╗   ██╗ █████╗ ██████╗ ██████╗  ██████╗ ████████╗ ║
║ ██╔════╝ ██║   ██║██╔══██╗██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝ ║
║ ██║  ███╗██║   ██║███████║██████╔╝██║  ██║██║   ██║   ██║    ║
║ ██║   ██║██║   ██║██╔══██║██╔══██╗██║  ██║██║   ██║   ██║    ║
║ ╚██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝╚██████╔╝   ██║    ║
║  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝    ╚═╝    ║
║                 TELEGRAM CONTENT GUARD                        ║
╚══════════════════════════════════════════════════════════════╝
"""))
    print(color("purple", "                 پنل نصب و مدیریت سرور لینوکس"))
    print()


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(values: dict[str, str]) -> None:
    order = [
        "BOT_TOKEN", "OWNER_IDS", "GOOGLE_VISION_KEY", "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL", "GOOGLE_DAILY_CAP", "ANTHROPIC_DAILY_CAP",
        "DEFAULT_ENGINE", "DEFAULT_LEVEL", "AI_TEXT_ALL", "LOG_LEVEL",
    ]
    lines = [
        "# GuardBot configuration. Keep this file private; never commit it to GitHub.",
        "# API providers process submitted media/text according to their own terms.",
    ]
    for key in order:
        lines.append(f'{key}="{values.get(key, "")}"')
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(ENV_FILE, 0o600)


def ask(label: str, current: str = "", secret: bool = False, required: bool = False) -> str:
    suffix = " [موجود؛ Enter برای حفظ، CLEAR برای پاک‌کردن]" if current and secret else (f" [{current}]" if current else "")
    while True:
        prompt = f"{label}{suffix}: "
        value = getpass.getpass(prompt) if secret else input(prompt)
        value = value.strip()
        if value.upper() == "CLEAR":
            value = ""
        elif not value:
            value = current
        if required and not value:
            print(color("red", "این فیلد ضروری است."))
            continue
        return value


def choose(label: str, options: list[tuple[str, str]], default: str) -> str:
    print(color("yellow", "\n" + label))
    for key, title in options:
        mark = " ← پیش‌فرض" if key == default else ""
        print(f"  [{key}] {title}{mark}")
    valid = {key for key, _ in options}
    while True:
        value = input(f"انتخاب [{default}]: ").strip().lower() or default
        if value in valid:
            return value
        print(color("red", "گزینه نامعتبر است."))


def setup() -> None:
    banner()
    values = read_env()
    print(color("green", "مرحله ۱ از ۵ — اتصال ربات تلگرام"))
    token = ask("توکن BotFather", values.get("BOT_TOKEN", ""), secret=True, required=True)
    if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}", token):
        print(color("yellow", "هشدار: قالب توکن غیرمعمول است؛ مقدار ذخیره می‌شود، اما بعداً اعتبارش بررسی خواهد شد."))
    owners = ask("شناسه عددی مالک/مالکان (با کاما جدا کن)", values.get("OWNER_IDS", ""), required=True)
    try:
        [int(x.strip()) for x in owners.split(",") if x.strip()]
    except ValueError:
        print(color("red", "شناسه مالک باید عددی باشد."))
        return setup()

    print(color("green", "\nمرحله ۲ از ۵ — موتور تشخیص"))
    engine = choose("موتور پیش‌فرض گروه‌های جدید", [
        ("smart", "هوشمند: محلی + سرویس‌های ابری در صورت تنظیم"),
        ("hybrid", "ترکیبی: تشخیص محلی و Google Vision"),
        ("local", "فقط محلی؛ بدون ارسال رسانه به سرویس بیرونی"),
        ("cloud", "فقط Google Vision"),
        ("brain", "فقط مدل هوش مصنوعی Claude"),
    ], values.get("DEFAULT_ENGINE", "smart"))
    level = choose("میزان حساسیت", [
        ("low", "ملایم؛ کاهش مثبت کاذب"),
        ("mid", "متعادل"),
        ("high", "سخت‌گیر؛ احتمال حذف اشتباه بیشتر"),
    ], values.get("DEFAULT_LEVEL", "mid"))

    print(color("green", "\nمرحله ۳ از ۵ — کلیدهای اختیاری هوش مصنوعی"))
    print(color("dim", "بدون کلیدها، تشخیص محلی و فهرست کلمات همچنان کار می‌کند. کلیدها را در GitHub منتشر نکن."))
    gkey = ask("Google Vision API Key (اختیاری)", values.get("GOOGLE_VISION_KEY", ""), secret=True)
    bkey = ask("Anthropic API Key (اختیاری)", values.get("ANTHROPIC_API_KEY", ""), secret=True)

    print(color("green", "\nمرحله ۴ از ۵ — سقف مصرف روزانه"))
    gcap = ask("حداکثر درخواست/تصویر Google Vision در روز", values.get("GOOGLE_DAILY_CAP", "100")) or "100"
    bcap = ask("حداکثر درخواست Claude در روز", values.get("ANTHROPIC_DAILY_CAP", "250")) or "250"
    try:
        if int(gcap) < 0 or int(bcap) < 0:
            raise ValueError
    except ValueError:
        print(color("red", "سقف مصرف باید عدد صفر یا مثبت باشد."))
        return setup()

    print(color("green", "\nمرحله ۵ از ۵ — تحلیل متن"))
    all_text = choose("تحلیل همه پیام‌های متنی با Claude؟ (مصرف API می‌تواند زیاد شود)", [
        ("0", "فقط لینک‌ها و متن‌های مشکوک (پیشنهادی)"),
        ("1", "تمام پیام‌های متنی با طول حداقل ۴ نویسه"),
    ], values.get("AI_TEXT_ALL", "0"))

    values.update({
        "BOT_TOKEN": token,
        "OWNER_IDS": owners,
        "DEFAULT_ENGINE": engine,
        "DEFAULT_LEVEL": level,
        "GOOGLE_VISION_KEY": gkey,
        "ANTHROPIC_API_KEY": bkey,
        "ANTHROPIC_MODEL": values.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        "GOOGLE_DAILY_CAP": gcap,
        "ANTHROPIC_DAILY_CAP": bcap,
        "AI_TEXT_ALL": all_text,
        "LOG_LEVEL": values.get("LOG_LEVEL", "INFO"),
    })
    write_env(values)
    print(color("green", "\n✅ تنظیمات ذخیره شد. فایل .env با سطح دسترسی خصوصی 600 ساخته شد."))
    print(color("yellow", "یادآوری: فایل .env را در GitHub آپلود نکن."))


def show_status() -> None:
    v = read_env()
    print(color("cyan", "وضعیت پیکربندی"))
    print("توکن ربات:", "تنظیم‌شده" if v.get("BOT_TOKEN") else "تنظیم‌نشده")
    print("مالک:", v.get("OWNER_IDS", "تنظیم‌نشده"))
    print("موتور:", v.get("DEFAULT_ENGINE", "smart"))
    print("حساسیت:", v.get("DEFAULT_LEVEL", "mid"))
    print("Google Vision:", "فعال" if v.get("GOOGLE_VISION_KEY") else "بدون کلید")
    print("Claude:", "فعال" if v.get("ANTHROPIC_API_KEY") else "بدون کلید")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="run setup wizard")
    args = parser.parse_args()
    if args.setup:
        setup()
        return
    while True:
        banner()
        print(color("green", " [S] راه‌اندازی / تغییر تنظیمات"))
        print(" [1] نمایش وضعیت تنظیمات (بدون نمایش کلیدها)")
        print(" [2] راهنمای دسترسی‌های تلگرام")
        print(" [Q] خروج")
        choice = input("\nدکمه را بزن و Enter کن: ").strip().lower()
        if choice == "s":
            setup()
            input("\nبرای بازگشت Enter بزن...")
        elif choice == "1":
            show_status()
            input("\nبرای بازگشت Enter بزن...")
        elif choice == "2":
            print("\nربات را در گروه ادمین کن و مجوز Delete Messages بده.")
            print("برای کانال نیز باید ادمین با مجوز حذف پیام باشد.")
            print("برای گروه‌ها، ادمین‌کردن ربات باعث می‌شود پیام‌های عادی را دریافت کند.")
            input("\nبرای بازگشت Enter بزن...")
        elif choice == "q":
            break
        else:
            print(color("red", "گزینه نامعتبر است."))


if __name__ == "__main__":
    main()
