import asyncio, hashlib, html, logging, os, re, shutil, tempfile, time
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (ChatPermissions, ChatMemberUpdated, Message,
                           InlineKeyboardMarkup as M, InlineKeyboardButton as B)
import config, db, detect, panel

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("guard")
GROUPS = {"group", "supergroup"}
r, ch = Router(), Router()
r.message.filter(F.chat.type.in_(GROUPS))
r.edited_message.filter(F.chat.type.in_(GROUPS))
LINK = re.compile(r"(https?://|t\.me/|telegram\.me/|@\w{4,}|\b[\w-]+\.[a-z]{2,}\b)", re.I)
TEXT_HINTS = ("porn", "xxx", "nude", "sex", "gore", "rape", "violence", "kill", "murder",
              "پورن", "سکس", "برهنه", "لخت", "خشونت", "قتل", "اعدام", "خون", "تجاوز", "جنسی")
EMOJI_HINTS = ("🔞", "🍆", "🍑", "💦", "🔪", "🩸", "💀", "🪓", "⚰", "🧨", "🔫", "🗡")
_adm, _tasks = {}, set()


async def is_admin(bot, cid, uid):
    if uid in config.OWNERS or uid == 1087968824:
        return True
    t = _adm.get((cid, uid))
    if t and time.time() - t[0] < 120:
        return t[1]
    try:
        ok = (await bot.get_chat_member(cid, uid)).status in ("administrator", "creator")
    except TelegramAPIError:
        ok = False
    _adm[(cid, uid)] = (time.time(), ok)
    return ok


def media(m, g):
    """-> (enabled, file_id, is_image, thumb_id, size, unique_id) | None"""
    th = lambda x: x.thumbnail.file_id if getattr(x, "thumbnail", None) else None
    if m.photo:
        p = m.photo[-1]
        return g["s_photo"], p.file_id, True, None, p.file_size or 0, p.file_unique_id
    for attr, flag in (("video", "s_video"), ("animation", "s_gif"), ("video_note", "s_note")):
        x = getattr(m, attr)
        if x:
            return g[flag], x.file_id, False, th(x), x.file_size or 0, x.file_unique_id
    if m.sticker:
        s = m.sticker
        if s.is_animated:  # .tgs -> thumbnail only
            return g["s_sticker"], th(s), True, None, 0, s.file_unique_id
        return g["s_sticker"], s.file_id, not s.is_video, th(s), s.file_size or 0, s.file_unique_id
    d = m.document
    if d and d.mime_type:
        if d.mime_type.startswith("image/"):
            return g["s_photo"], d.file_id, True, None, d.file_size or 0, d.file_unique_id
        if d.mime_type.startswith("video/"):
            return g["s_video"], d.file_id, False, th(d), d.file_size or 0, d.file_unique_id
    return None


async def inspect(bot, m, g):
    info = media(m, g)
    if not info or not info[0] or not info[1]:
        return None
    _, fid, is_img, thumb, size, uid = info
    key = f"{uid}:{g['engine']}:{g['level']}"
    c = db.seen_get(key)
    if c:
        return bool(c["bad"]), c["reason"], c["why"]
    tmp = tempfile.mkdtemp()
    try:
        paths = []
        if size <= 19 * 1024 * 1024:
            src = os.path.join(tmp, "src")
            await bot.download(fid, destination=src)
            paths = [src] if is_img else await detect.frames(src, tmp)
        if not paths and thumb:
            t = os.path.join(tmp, "th.jpg")
            await bot.download(thumb, destination=t)
            paths = [t]
        if not paths:
            return None
        bad, reason, why, deg = await detect.scan(paths, g["engine"], g["level"])
        if not deg:
            db.seen_put(key, bad, reason, why)
        return bad, reason, why
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def judge(bot, m, g):
    """-> (reason, why) | None"""
    txt = m.text or m.caption or ""
    low = txt.lower()
    if g["textfilter"] and low and any(w.casefold() in low for w in db.words()):
        return "کلمه ممنوعه", ""
    if m.sticker and m.sticker.set_name in db.packs():
        return "استیکر ممنوعه", ""
    try:
        res = await inspect(bot, m, g)
        if res and res[0]:
            return res[1], res[2]
        entities = (m.entities or []) + (m.caption_entities or [])
        hidden_link = any(getattr(e, "type", "") in {"url", "text_link"} for e in entities)
        normalized = low.translate(str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه"})).replace("\u200c", "")
        compact = re.sub(r"[^a-z0-9\u0600-\u06ff]", "", normalized)
        hinted = any(h in normalized or h in compact for h in TEXT_HINTS)
        emoji_hint = any(symbol in txt for symbol in EMOJI_HINTS)
        # AI is called for URLs/hidden URLs, suspicious language and selected emoji,
        # avoiding a paid API request for every ordinary chat message.
        # Set AI_TEXT_ALL=1 to scan every text.
        scan_all_text = os.getenv("AI_TEXT_ALL", "0") == "1"
        if g["s_ai"] and (len(txt) >= 4 or emoji_hint) and (scan_all_text or LINK.search(txt) or hidden_link or hinted or emoji_hint):
            key = "t:" + hashlib.md5(f"{txt}{g['level']}".encode()).hexdigest()
            c = db.seen_get(key)
            if c:
                return (c["reason"], c["why"]) if c["bad"] else None
            bad, reason, why, deg = await detect.brain_text(txt, g["level"])
            if not deg:
                db.seen_put(key, bad, reason, why)
            if bad:
                return reason, why
    except Exception as e:
        log.warning("judge failed: %s", e)
    return None


async def report(bot, m, reason, why, buttons=True, note=""):
    cid = m.chat.id
    who = m.from_user.full_name if m.from_user else (m.author_signature or "کانال/ادمین")
    head = (f"🚨 <b>{html.escape(m.chat.title or '')}</b>\nدلیل: {html.escape(reason)}\nفرستنده: {html.escape(who)}"
            + (f"\n🧠 {html.escape(why)}" if why else "") + note)
    mk = M(inline_keyboard=[[B(text="🗑 حذف", callback_data=f"rd:{cid}:{m.message_id}"),
                             B(text="✅ نادیده", callback_data=f"ri:{cid}:{m.message_id}")]]) if buttons else None
    for o in config.OWNERS:
        if buttons:
            try: await bot.copy_message(o, cid, m.message_id)
            except TelegramAPIError: pass
        try: await bot.send_message(o, head, reply_markup=mk)
        except TelegramAPIError: pass


async def _later(msg, s=12):
    await asyncio.sleep(s)
    try: await msg.delete()
    except TelegramAPIError: pass


async def punish(bot, m, g, reason, why):
    cid, u = m.chat.id, m.from_user
    if not u:
        return
    try:
        await m.delete()
    except TelegramAPIError as e:
        return log.warning("can't delete in %s (bot must be admin): %s", cid, e)
    db.inc_deleted(cid)
    n = db.add_warn(cid, u.id)
    txt = f"🚫 پیام {u.mention_html()} حذف شد\nدلیل: {reason}\n"
    if g["punish"] != "none" and n >= g["warn_limit"]:
        db.reset_warns(cid, u.id)
        if g["punish"] == "warn":
            txt += "⚠️ سقف اخطار پر شد؛ مجازات خودکار غیرفعال است."
        else:
            try:
                if g["punish"] == "ban":
                    await bot.ban_chat_member(cid, u.id)
                    txt += "⛔️ کاربر مسدود شد."
                elif g["punish"] == "mute":
                    await bot.restrict_chat_member(cid, u.id, ChatPermissions(can_send_messages=False),
                                                   until_date=int(time.time()) + 86400)
                    txt += "🔇 کاربر یک روز میوت شد."
            except TelegramAPIError:
                txt += " (دسترسی ربات برای مجازات کافی نیست)"
    else:
        txt += f"⚠️ اخطار {n}/{g['warn_limit']}"
    s = await bot.send_message(cid, txt)
    t = asyncio.create_task(_later(s)); _tasks.add(t); t.add_done_callback(_tasks.discard)
    if g["notify"]:
        await report(bot, m, reason, why, buttons=False, note="\n🗑 حذف شد")


async def handle(m: Message, edited=False):
    bot, is_ch = m.bot, m.chat.type == "channel"
    g = db.group(m.chat.id, m.chat.title, "channel" if is_ch else "group")
    if not g["enabled"]:
        return
    admin = False
    if not is_ch:
        admin = bool(m.sender_chat) or await is_admin(bot, m.chat.id, m.from_user.id)
        if admin and g["admin_mode"] == "skip":
            return
    res = await judge(bot, m, g)
    if not res:
        return
    reason, why = res
    if edited:
        reason += " (بعد از ویرایش)"
    if is_ch or admin:
        mode = g["chan_mode"] if is_ch else g["admin_mode"]
        if mode == "delete":
            try:
                await m.delete(); db.inc_deleted(m.chat.id)
                await report(bot, m, reason, why, buttons=False, note="\n🗑 خودکار حذف شد")
            except TelegramAPIError:
                await report(bot, m, reason, why, note="\n⚠️ حذف نشد (دسترسی ربات؟)")
        else:
            await report(bot, m, reason, why)
        return
    await punish(bot, m, g, reason, why)


@r.message(F.from_user | F.sender_chat)
async def on_msg(m: Message): await handle(m)


@r.edited_message(F.from_user | F.sender_chat)
async def on_edit(m: Message): await handle(m, True)


@ch.channel_post()
async def on_post(m: Message): await handle(m)


@ch.edited_channel_post()
async def on_post_edit(m: Message): await handle(m, True)


async def main():
    if not config.TOKEN or not config.OWNERS:
        raise SystemExit("BOT_TOKEN / OWNER_IDS not set in .env")
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg not found: video/gif scanning will use thumbnails only")
    bot = Bot(config.TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_routers(panel.r, r, ch)

    @dp.callback_query(F.data.startswith("rd:"))
    async def owner_delete_report(cb):
        if cb.from_user.id not in config.OWNERS:
            await cb.answer("فقط مالک ربات می‌تواند این کار را انجام دهد.", show_alert=True)
            return
        try:
            _, cid, mid = (cb.data or "").split(":")
            await bot.delete_message(int(cid), int(mid))
            db.inc_deleted(int(cid))
            await cb.answer("پیام حذف شد.")
            if cb.message:
                await cb.message.edit_reply_markup(reply_markup=None)
        except Exception as exc:
            log.warning("owner delete action failed: %s", exc)
            await cb.answer("حذف پیام ممکن نشد؛ شاید قبلاً حذف شده باشد.", show_alert=True)

    @dp.callback_query(F.data.startswith("ri:"))
    async def owner_ignore_report(cb):
        if cb.from_user.id not in config.OWNERS:
            await cb.answer("فقط مالک ربات می‌تواند این کار را انجام دهد.", show_alert=True)
            return
        await cb.answer("گزارش نادیده گرفته شد.")
        if cb.message:
            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except TelegramAPIError:
                pass

    @dp.my_chat_member(F.chat.type.in_({"group", "supergroup", "channel"}))
    async def joined(e: ChatMemberUpdated):
        if e.new_chat_member.status in ("member", "administrator"):
            db.group(e.chat.id, e.chat.title, "channel" if e.chat.type == "channel" else "group")

    async def warm_local_detector():
        try:
            await asyncio.to_thread(detect.warm)
        except Exception as exc:
            log.warning("local detector could not initialize; cloud/AI fallback remains available: %s", exc)

    asyncio.create_task(warm_local_detector())
    log.info("GuardBot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
