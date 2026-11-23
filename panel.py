"""Telegram inline admin panel. Access is checked on every callback."""
from __future__ import annotations

import html
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError

import config
import db

log = logging.getLogger("panel")
r = Router()

ENGINES = {
    "smart": "🧠 هوشمند",
    "hybrid": "⚖️ ترکیبی",
    "local": "💻 محلی",
    "cloud": "☁️ ابری",
    "brain": "🤖 هوش مصنوعی",
}
LEVELS = {"low": "ملایم", "mid": "متعادل", "high": "سخت‌گیر"}
PUNISHMENTS = {"none": "بدون مجازات اضافه", "warn": "فقط اخطار", "mute": "میوت یک‌روزه", "ban": "مسدودسازی"}


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🔄 تازه‌سازی", "p:home")]])


def _groups_kb() -> InlineKeyboardMarkup:
    rows = []
    for g in db.groups():
        title = (g["title"] or str(g["chat_id"]))[:28]
        status = "🟢" if g["enabled"] else "⚪"
        rows.append([_btn(f"{status} {title}", f"p:g:{g['chat_id']}")])
    rows.append([_btn("🔄 تازه‌سازی", "p:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _group_kb(cid: int, g) -> InlineKeyboardMarkup:
    enabled = "روشن ✅" if g["enabled"] else "خاموش ⛔"
    admin_mode = {"skip": "نادیده‌گرفتن", "delete": "حذف خودکار", "report": "گزارش برای بررسی"}.get(g["admin_mode"], g["admin_mode"])
    chan_mode = {"delete": "حذف خودکار", "report": "گزارش برای بررسی"}.get(g["chan_mode"], g["chan_mode"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(f"🛡 فیلتر: {enabled}", f"p:t:{cid}:enabled")],
        [_btn(f"🧠 موتور: {ENGINES.get(g['engine'], g['engine'])}", f"p:m:{cid}:engine")],
        [_btn(f"🎚 حساسیت: {LEVELS.get(g['level'], g['level'])}", f"p:m:{cid}:level")],
        [_btn(f"🧩 فیلترهای رسانه‌ای", f"p:m:{cid}:filters")],
        [_btn(f"👮 رفتار با ادمین‌ها: {admin_mode}", f"p:m:{cid}:admin_mode")],
        [_btn(f"📢 رفتار در کانال: {chan_mode}", f"p:m:{cid}:chan_mode")],
        [_btn(f"⚠️ مجازات: {PUNISHMENTS.get(g['punish'], g['punish'])}", f"p:m:{cid}:punish")],
        [_btn(f"🔢 سقف اخطار: {g['warn_limit']}", f"p:m:{cid}:warn_limit")],
        [_btn(f"📨 گزارش حذف‌ها به مالک: {'روشن ✅' if g['notify'] else 'خاموش ❌'}", f"p:t:{cid}:notify")],
        [_btn("📊 آمار", f"p:stats:{cid}"), _btn("🔄 تازه‌سازی", f"p:g:{cid}")],
        [_btn("⬅️ بازگشت", "p:home")],
    ])


def _filters_kb(cid: int, g) -> InlineKeyboardMarkup:
    labels = [
        ("s_photo", "🖼 عکس"), ("s_video", "🎬 ویدیو"), ("s_gif", "🎞 گیف/انیمیشن"),
        ("s_sticker", "🎭 استیکر"), ("s_note", "⭕ ویدیو نوت"),
        ("textfilter", "🔤 کلمات ممنوعه"), ("s_ai", "🧠 تحلیل متن با هوش مصنوعی"),
    ]
    rows = []
    for field, label in labels:
        state = "✅" if g[field] else "❌"
        rows.append([_btn(f"{label}: {state}", f"p:t:{cid}:{field}")])
    rows.append([_btn("⬅️ بازگشت", f"p:g:{cid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _menu_kb(cid: int, name: str) -> InlineKeyboardMarkup:
    if name == "engine":
        choices = [(k, ENGINES[k]) for k in ENGINES]
    elif name == "level":
        choices = [(k, v) for k, v in LEVELS.items()]
    elif name == "admin_mode":
        choices = [("skip", "نادیده‌گرفتن ادمین‌ها"), ("delete", "حذف پیام ادمین"), ("report", "گزارش برای بررسی")]
    elif name == "chan_mode":
        choices = [("delete", "حذف خودکار پست کانال"), ("report", "فقط گزارش پست کانال")]
    elif name == "punish":
        choices = [(k, v) for k, v in PUNISHMENTS.items()]
    elif name == "warn_limit":
        choices = [(str(n), f"{n} اخطار") for n in (1, 2, 3, 5, 7, 10)]
    else:
        choices = []
    rows = [[_btn(label, f"p:set:{cid}:{name}:{value}")] for value, label in choices]
    rows.append([_btn("⬅️ بازگشت", f"p:g:{cid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _is_group_admin(bot, cid: int, uid: int) -> bool:
    if uid in config.OWNERS:
        return True
    try:
        member = await bot.get_chat_member(cid, uid)
        return member.status in {"administrator", "creator"}
    except TelegramAPIError:
        return False


async def _allowed(cb: CallbackQuery, cid: int) -> bool:
    if cb.from_user.id in config.OWNERS:
        return True
    if not cb.message or cb.message.chat.id != cid:
        return False
    return await _is_group_admin(cb.bot, cid, cb.from_user.id)


async def _show_group(message_or_cb, cid: int):
    chat = await message_or_cb.bot.get_chat(cid)
    g = db.group(cid, chat.title or str(cid), "channel" if chat.type == "channel" else "group")
    body = (
        f"🛡 <b>پنل نگهبان محتوا</b>\n"
        f"گپ: <b>{html.escape(chat.title or str(cid))}</b>\n"
        f"وضعیت: {'فعال ✅' if g['enabled'] else 'غیرفعال ⛔'}\n"
        f"موتور: {ENGINES.get(g['engine'], g['engine'])} | حساسیت: {LEVELS.get(g['level'], g['level'])}\n\n"
        "تنظیم موردنظر را انتخاب کن:"
    )
    if isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.message.edit_text(body, reply_markup=_group_kb(cid, g))
    else:
        await message_or_cb.answer(body, reply_markup=_group_kb(cid, g))


async def _show_home(message_or_cb):
    if isinstance(message_or_cb, CallbackQuery):
        body = "👑 <b>پنل مالک ربات</b>\nگروه یا کانال موردنظر را انتخاب کن."
        await message_or_cb.message.edit_text(body, reply_markup=_groups_kb())
    else:
        body = "👑 <b>پنل مالک ربات</b>\nگروه یا کانال موردنظر را انتخاب کن."
        await message_or_cb.answer(body, reply_markup=_groups_kb())


@r.message(Command("start"))
async def start_command(m: Message):
    if m.chat.type == "private" and m.from_user and m.from_user.id in config.OWNERS:
        await m.answer("🛡 <b>GuardBot فعال است.</b>\nبرای مدیریت گروه‌ها از پنل استفاده کن.",
                       reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_btn("👑 بازکردن پنل", "p:home")]]))
    elif m.chat.type == "private":
        await m.answer("سلام! من ربات مدیریت محتوای گروه و کانالم.")


@r.message(Command("help"))
async def help_command(m: Message):
    await m.answer("🛡 <b>راهنما</b>\n/panel — پنل تنظیمات (مالک یا ادمین گروه)\n/guardstats — آمار گروه\n/addword عبارت — افزودن عبارت ممنوعه\n/delword عبارت — حذف عبارت ممنوعه")


@r.message(Command("panel"))
async def panel_command(m: Message):
    if m.chat.type == "private":
        if m.from_user and m.from_user.id in config.OWNERS:
            await _show_home(m)
        else:
            await m.answer("⛔ دسترسی به پنل مالک فقط برای مالک ربات فعال است.")
        return
    if not m.from_user or not await _is_group_admin(m.bot, m.chat.id, m.from_user.id):
        await m.answer("⛔ فقط ادمین‌های همین گروه می‌توانند تنظیماتش را ببینند.")
        return
    await _show_group(m, m.chat.id)


@r.message(Command("addword"))
async def add_word(m: Message):
    if m.chat.type not in {"group", "supergroup"} or not m.from_user:
        return
    if not await _is_group_admin(m.bot, m.chat.id, m.from_user.id):
        return
    word = (m.text or "").partition(" ")[2].strip()
    if not word:
        await m.reply("استفاده: /addword کلمه یا عبارت")
        return
    db.add("words", word[:100])
    await m.reply("✅ عبارت به فهرست ممنوعه اضافه شد.")


@r.message(Command("delword"))
async def del_word(m: Message):
    if m.chat.type not in {"group", "supergroup"} or not m.from_user:
        return
    if not await _is_group_admin(m.bot, m.chat.id, m.from_user.id):
        return
    word = (m.text or "").partition(" ")[2].strip()
    if not word:
        await m.reply("استفاده: /delword کلمه یا عبارت")
        return
    db.rem("words", word[:100])
    await m.reply("✅ عبارت از فهرست ممنوعه حذف شد.")


@r.message(Command("guardstats"))
async def stats_command(m: Message):
    if not m.from_user or not await _is_group_admin(m.bot, m.chat.id, m.from_user.id):
        return
    g = db.group(m.chat.id, m.chat.title)
    await m.answer(f"📊 <b>آمار نگهبان</b>\nپیام‌های حذف‌شده: <b>{g['deleted']}</b>\nوضعیت فیلتر: {'فعال' if g['enabled'] else 'خاموش'}")


@r.callback_query(F.data.startswith("p:"))
async def panel_callback(cb: CallbackQuery):
    try:
        parts = (cb.data or "").split(":")
        action = parts[1]
        if action == "home":
            if cb.from_user.id in config.OWNERS:
                await _show_home(cb)
            elif cb.message and cb.message.chat.type in {"group", "supergroup"} and await _is_group_admin(
                    cb.bot, cb.message.chat.id, cb.from_user.id):
                await _show_group(cb, cb.message.chat.id)
            else:
                await cb.answer("این بخش فقط برای مدیران مجاز است.", show_alert=True)
                return
            await cb.answer()
            return

        if action == "g":
            cid = int(parts[2])
        else:
            cid = int(parts[2])
        if not await _allowed(cb, cid):
            await cb.answer("دسترسی غیرمجاز.", show_alert=True)
            return

        if action == "g":
            await _show_group(cb, cid)
        elif action == "t":
            field = parts[3]
            if field not in db.FIELDS:
                await cb.answer("تنظیم ناشناخته است.", show_alert=True)
                return
            db.toggle(cid, field)
            g = db.group(cid)
            if field in {"s_photo", "s_video", "s_gif", "s_sticker", "s_note", "textfilter", "s_ai"}:
                await cb.message.edit_reply_markup(reply_markup=_filters_kb(cid, g))
            else:
                await _show_group(cb, cid)
        elif action == "m":
            name = parts[3]
            if name == "filters":
                await cb.message.edit_reply_markup(reply_markup=_filters_kb(cid, db.group(cid)))
            else:
                await cb.message.edit_reply_markup(reply_markup=_menu_kb(cid, name))
        elif action == "set":
            name, value = parts[3], parts[4]
            allowed = {
                "engine": set(ENGINES), "level": set(LEVELS),
                "admin_mode": {"skip", "delete", "report"},
                "chan_mode": {"delete", "report"},
                "punish": set(PUNISHMENTS), "warn_limit": {"1", "2", "3", "5", "7", "10"},
            }
            if name not in allowed or value not in allowed[name]:
                await cb.answer("مقدار نامعتبر است.", show_alert=True)
                return
            db.setg(cid, name, int(value) if name == "warn_limit" else value)
            await _show_group(cb, cid)
        elif action == "stats":
            g = db.group(cid)
            await cb.message.edit_text(
                f"📊 <b>آمار {html.escape(g['title'] or str(cid))}</b>\nپیام حذف‌شده: <b>{g['deleted']}</b>\nحساسیت: {LEVELS.get(g['level'], g['level'])}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ بازگشت", f"p:g:{cid}")]])
            )
        await cb.answer()
    except (ValueError, IndexError, KeyError) as exc:
        log.warning("bad panel callback: %s", exc)
        await cb.answer("درخواست نامعتبر بود؛ پنل را دوباره باز کن.", show_alert=True)
    except TelegramAPIError as exc:
        log.warning("panel callback Telegram error: %s", exc)
        await cb.answer("تلگرام نتوانست پنل را به‌روزرسانی کند.", show_alert=True)
