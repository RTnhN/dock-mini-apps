import lvgl as lv
import arequests as requests
import uasyncio as asyncio
import net
import clocktime  # Must provide epoch time in seconds
import ubinascii

NAME = "Toggl"
CAN_BE_AUTO_SWITCHED = True

scr = lv.obj()
label = None
toggl_api_token = ""
timer_cache = None
last_fetch = 0

def get_settings_json():
    return {
        "form": [{
            "type": "input",
            "default": "",
            "caption": "Toggl API Token",
            "name": "toggl_api",
            "attributes": {"placeholder": "Toggl Api"},
        }]
    }

def _load_config():
    global toggl_api_token
    cfg = _app_mgr.config()
    tok = cfg.get("toggl_api", "").strip()
    if tok:
        toggl_api_token = tok
        return True
    else:
        _app_mgr.error(
            "Toggl Token Missing",
            "Configure your Toggl API token in settings.",
            confirm="OK", cancel=False,
            cb=lambda res: asyncio.create_task(_app_mgr.exit()))
        return False

def b64_auth(token):
    raw = "{}:api_token".format(token)
    return ubinascii.b2a_base64(raw.encode()).strip().decode()

async def fetch_toggl_timer():
    global toggl_api_token
    if not toggl_api_token:
        return None
    url = "https://api.track.toggl.com/api/v9/me/time_entries/current"
    try:
        resp = await requests.request(
            "GET", url,
            headers={"Authorization": "Basic " + b64_auth(toggl_api_token)},
            timeout=10
        )
        if resp.status_code == 200:
            data = await resp.json()
            return data
    except Exception as e:
        pass
    return None

def parse_start_time(start_str):
    # Example: '2024-06-18T06:29:23+00:00'
    # We want epoch seconds (UTC)
    try:
        y = int(start_str[0:4])
        m = int(start_str[5:7])
        d = int(start_str[8:10])
        hh = int(start_str[11:13])
        mm = int(start_str[14:16])
        ss = int(start_str[17:19])
        # Ignore timezone, assume UTC
        import utime
        tm_tuple = (y, m, d, hh, mm, ss, 0, 0)
        return utime.mktime(tm_tuple)
    except Exception as e:
        return None

def elapsed_str(start_epoch, now_epoch):
    if start_epoch is None or now_epoch is None or now_epoch < start_epoch:
        return "??:??:??"
    secs = int(now_epoch - start_epoch)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h}:{m:02}:{s:02}"

def format_timer(data):
    if not data or "description" not in data or data["description"] is None:
        return "No timer running."
    desc = data.get("description") or "(No Description)"
    start_str = data.get("start", None)
    if start_str:
        now_epoch = clocktime.now()
        start_epoch = parse_start_time(start_str)
        elapsed = elapsed_str(start_epoch, now_epoch)
        return f"{desc}\nRunning: {elapsed}"
    else:
        return f"{desc}\nRunning: --:--:--"

async def update_toggl_label():
    global label, timer_cache, last_fetch
    if not net.connected():
        label.set_text("No network.")
        return
    timer = await fetch_toggl_timer()
    timer_cache = timer
    last_fetch = clocktime.now()
    txt = format_timer(timer)
    label.set_text(txt)

async def refresh_running_time():
    # Fast update of running time without extra requests
    global label, timer_cache, last_fetch
    if not timer_cache:
        return
    desc = timer_cache.get("description") or "(No Description)"
    start_str = timer_cache.get("start", None)
    if start_str:
        now_epoch = clocktime.now()
        start_epoch = parse_start_time(start_str)
        elapsed = elapsed_str(start_epoch, now_epoch)
        label.set_text(f"{desc}\nRunning: {elapsed}")
    else:
        label.set_text(f"{desc}\nRunning: --:--:--")

async def on_start():
    global label
    if not _load_config():
        return
    label = lv.label(scr)
    label.center()
    label.set_text("Loading Toggl...")
    lv.scr_load(scr)
    await update_toggl_label()

async def on_running_foreground():
    # Refresh elapsed time every call, but fetch API every 10s
    global last_fetch
    now = clocktime.now()
    # API call every 10s
    if (now - last_fetch) > 600:
        await update_toggl_label()
    else:
        await refresh_running_time()

async def on_stop():
    scr.clean()

async def on_boot(apm):
    global _app_mgr
    _app_mgr = apm
