#!/usr/bin/env python3

import asyncio
import aiohttp
import json
import re
import time
import random
import string
import os
import sys
import base64
from datetime import datetime
from typing import List, Optional, Dict, Set
from dataclasses import dataclass
from collections import deque

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.tree import Tree
from rich.prompt import IntPrompt, Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.align import Align

try:
    from banner import BANNER
except ImportError:
    BANNER = "[bold purple]NOCTA GEN v3.0[/bold purple]"

console = Console()

DEFAULT_CONFIG = {
    "PROXIES_FILE": "proxies.txt",
    "CONCURRENT": 1,
    "TIMEOUT": 60,
    "USE_PROXIES": False,
    "HEADLESS": False,
    "OUTPUT_FOLDER": "output",
    "SAVE_FORMAT": "email:pass:token",
    "DISPLAY_NAME": "",
    "USE_AVATAR": False,
    "MAX_ACCOUNTS": 500,
    "RETRY_ATTEMPTS": 3,
    "DELAY_BETWEEN": 45,
    "HUMAN_MODE": True,
    "USER_AGENT_ROTATION": False,
    "REQUEST_INTERCEPTION": False
}

TOKENS_FILE = "tokens.txt"
AVATAR_FOLDER = "profilepictures"
LOG_FILE = "generation_log.txt"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.0 Edg/119.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"
]

@dataclass
class GenResult:
    email: str
    password: str
    token: Optional[str] = None
    username: str = ""
    display_name: str = ""
    proxy: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    timestamp: str = ""
    age_verified: bool = False

class ConfigManager:
    def __init__(self):
        self.cfg = {}
        self.load()
    
    def load(self):
        try:
            import config as c
            for k, v in DEFAULT_CONFIG.items():
                self.cfg[k] = getattr(c, k, v)
        except:
            self.cfg = DEFAULT_CONFIG.copy()
            self.save()
    
    def save(self):
        with open("config.py", "w") as f:
            f.write("# Nocta Gen Configuration\n\n")
            for k, v in self.cfg.items():
                if isinstance(v, str):
                    f.write(f'{k} = "{v}"\n')
                else:
                    f.write(f"{k} = {v}\n")
    
    def get(self, k: str, default=None):
        return self.cfg.get(k, default)
    
    def set(self, k: str, v):
        self.cfg[k] = v
        self.save()

class ProxyManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.proxies: List[str] = []
        self.working: Set[str] = set()
        self.dead: Set[str] = set()
        self.current_idx = 0
        self.lock = asyncio.Lock()
        self.load()
    
    def load(self):
        if not os.path.exists(self.filepath):
            return
        
        with open(self.filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    self.proxies.append(line)
        
        self.working = set(self.proxies)
    
    async def get(self) -> Optional[str]:
        async with self.lock:
            if not self.working:
                return None
            proxy_list = list(self.working)
            proxy = proxy_list[self.current_idx % len(proxy_list)]
            self.current_idx += 1
            return proxy
    
    def mark_dead(self, proxy: str):
        self.working.discard(proxy)
        self.dead.add(proxy)
    
    @property
    def status(self) -> str:
        total = len(self.proxies)
        working = len(self.working)
        dead = len(self.dead)
        return f"[green]{working}[/green]/[red]{dead}[/red]/[dim]{total}[/dim]"

class OneSecMail:
    def __init__(self):
        self.base = "https://www.1secmail.com/api/v1/"
        self.domains = ["1secmail.com", "1secmail.net", "1secmail.org"]
    
    def random_email(self) -> Dict[str, str]:
        login = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        domain = random.choice(self.domains)
        email = f"{login}@{domain}"
        
        return {
            "email": email,
            "login": login,
            "domain": domain,
            "password": self.random_password()
        }
    
    def random_password(self, length=16):
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(random.choices(chars, k=length))
    
    async def check_messages(self, login: str, domain: str, session: aiohttp.ClientSession) -> Optional[Dict]:
        try:
            url = f"{self.base}?action=getMessages&login={login}&domain={domain}"
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        for msg in data:
                            subject = msg.get("subject", "").lower()
                            from_addr = msg.get("from", "").lower()
                            if "discord" in subject or "discord" in from_addr:
                                return msg
        except:
            pass
        return None
    
    async def get_verify_link(self, login: str, domain: str, msg_id: int, session: aiohttp.ClientSession) -> Optional[str]:
        try:
            url = f"{self.base}?action=readMessage&login={login}&domain={domain}&id={msg_id}"
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    body = data.get("body", "")
                    text = data.get("textBody", "")
                    combined = body + " " + text
                    
                    patterns = [
                        r'https://click\.discord\.com/ls/click\?[^\s"<]+',
                        r'https://discord\.com/verify[^\s"<]+',
                        r'https://discord\.com/api/v9/auth/verify[^\s"<]+',
                    ]
                    
                    for p in patterns:
                        links = re.findall(p, combined, re.IGNORECASE)
                        if links:
                            clean = links[0].replace('"', '').replace("'", "").replace(">", "").replace("<", "")
                            return clean
        except:
            pass
        return None

class AvatarManager:
    def __init__(self, folder: str):
        self.folder = folder
        self.images: List[str] = []
        self.current_idx = 0
        self.lock = asyncio.Lock()
        self.load_images()
    
    def load_images(self):
        if not os.path.exists(self.folder):
            os.makedirs(self.folder)
            return
        
        for f in os.listdir(self.folder):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                self.images.append(os.path.join(self.folder, f))
    
    async def get_next(self) -> Optional[bytes]:
        async with self.lock:
            if not self.images:
                return None
            path = self.images[self.current_idx % len(self.images)]
            self.current_idx += 1
        
        try:
            with open(path, "rb") as f:
                return f.read()
        except:
            return None
    
    @property
    def count(self) -> int:
        return len(self.images)

class StatsTracker:
    def __init__(self):
        self.successful = 0
        self.failed = 0
        self.total = 0
        self.start_time = None
        self.lock = asyncio.Lock()
    
    async def increment_success(self):
        async with self.lock:
            self.successful += 1
            self.total += 1
    
    async def increment_fail(self):
        async with self.lock:
            self.failed += 1
            self.total += 1
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.successful / self.total) * 100

class NoctaGen:
    def __init__(self):
        self.cfg = ConfigManager()
        self.proxies: Optional[ProxyManager] = None
        self.results: deque = deque(maxlen=200)
        self.mail = OneSecMail()
        self.avatars = AvatarManager(AVATAR_FOLDER)
        self.stats = StatsTracker()
        self.ensure_output()
        self.session: Optional[aiohttp.ClientSession] = None
        self.current_user_agent = random.choice(USER_AGENTS)
    
    def ensure_output(self):
        folder = self.cfg.get("OUTPUT_FOLDER", "output")
        if not os.path.exists(folder):
            os.makedirs(folder)
    
    def random_username(self, length=10):
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
    
    def generate_adult_birthday(self):
        current_year = 2026
        min_age = 18
        max_age = 45
        
        max_birth_year = current_year - min_age
        min_birth_year = current_year - max_age
        
        year = random.randint(min_birth_year, max_birth_year)
        month = random.randint(1, 12)
        
        if month in [1, 3, 5, 7, 8, 10, 12]:
            day = random.randint(1, 31)
        elif month == 2:
            is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
            day = random.randint(1, 29 if is_leap else 28)
        else:
            day = random.randint(1, 30)
        
        today = datetime.now()
        age = current_year - year
        if (today.month, today.day) < (month, day):
            age -= 1
        
        return {
            "day": str(day),
            "month": str(month),
            "year": str(year),
            "age": age
        }
    
    def log(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        color = {"info": "cyan", "success": "green", "warning": "yellow", "error": "red", "step": "magenta"}.get(level, "white")
        self.results.append((ts, level, msg))
        
        log_line = f"[{ts}] {level.upper()}: {msg}\n"
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line)
        except:
            pass
        
        console.print(f"[dim]{ts}[/dim] | [{color}]{level.upper()[:5]:^5}[/{color}] | {msg}")
    
    async def human_like_delay(self, min_ms=800, max_ms=2500):
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)
    
    async def human_like_typing(self, page, selector, text):
        for char in text:
            await page.type(selector, char, delay=random.randint(50, 150))
            await asyncio.sleep(random.uniform(0.01, 0.08))
    
    async def human_mouse_move(self, page, target_x, target_y):
        steps = random.randint(10, 25)
        
        start_x = random.randint(100, 300)
        start_y = random.randint(100, 300)
        
        for i in range(steps):
            t = i / steps
            ease = t * t * (3 - 2 * t)
            new_x = int(start_x + (target_x - start_x) * ease + random.randint(-5, 5))
            new_y = int(start_y + (target_y - start_y) * ease + random.randint(-5, 5))
            await page.mouse.move(new_x, new_y)
            await asyncio.sleep(random.uniform(0.01, 0.03))
    
    async def check_for_captcha(self, page):
        captcha_selectors = [
            "iframe[src*='captcha']",
            "iframe[src*='hcaptcha']",
            "iframe[src*='recaptcha']",
            "div[class*='captcha']",
            "[data-sitekey]",
            ".h-captcha",
            ".g-recaptcha",
            "text=I'm not a robot",
            "text=Verify you are human"
        ]
        
        for selector in captcha_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    return True
            except:
                continue
        return False
    
    async def wait_for_manual_captcha(self, page):
        self.log("warning", "CAPTCHA DETECTED - MANUAL SOLVE REQUIRED")
        console.print()
        console.print(Panel.fit(
            "[bold red]⚠ CAPTCHA CHALLENGE DETECTED ⚠[/bold red]\n\n"
            "[white]Please complete the CAPTCHA in the browser window.[/white]\n"
            "[cyan]1.[/cyan] Solve the CAPTCHA manually\n"
            "[cyan]2.[/cyan] Click 'Continue' or 'Submit' if present\n"
            "[cyan]3.[/cyan] Press [bold green]ENTER[/bold green] here when done\n\n"
            "[dim]Waiting for your input...[/dim]",
            border_style="red",
            padding=(1, 4)
        ))
        
        try:
            await asyncio.get_event_loop().run_in_executor(None, input)
        except:
            pass
        
        self.log("step", "Resuming after manual CAPTCHA solve...")
        await asyncio.sleep(2)
        
        for _ in range(10):
            if await self.check_for_captcha(page):
                self.log("warning", "CAPTCHA still present, waiting...")
                await asyncio.sleep(1)
            else:
                self.log("success", "CAPTCHA cleared!")
                return True
        
        self.log("error", "CAPTCHA still present after wait")
        return False
    
    async def generate_one(self, use_proxy: bool = False, headless: bool = False, retry_count: int = 0) -> GenResult:
        if self.cfg.get("USER_AGENT_ROTATION"):
            self.current_user_agent = random.choice(USER_AGENTS)
            self.log("info", f"Rotated User Agent")
        
        if self.stats.total > 0:
            long_delay = random.randint(30, 90)
            self.log("info", f"Rate limit prevention: waiting {long_delay}s...")
            await asyncio.sleep(long_delay)
        
        proxy = await self.proxies.get() if (use_proxy and self.proxies) else None
        
        mail_data = self.mail.random_email()
        email = mail_data["email"]
        password = mail_data["password"]
        username = self.random_username()
        login = mail_data["login"]
        domain = mail_data["domain"]
        
        cfg_display = self.cfg.get("DISPLAY_NAME", "").strip()
        display_name = cfg_display if cfg_display else username
        
        birthday = self.generate_adult_birthday()
        day = birthday["day"]
        month = birthday["month"]
        year = birthday["year"]
        
        result = GenResult(
            email=email,
            password=password,
            username=username,
            display_name=display_name,
            proxy=proxy,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            age_verified=True
        )
        
        self.log("info", f"Email: {email}")
        self.log("info", f"User: {username} | Age: {birthday['age']}")
        
        avatar_data = None
        if self.cfg.get("USE_AVATAR") and self.avatars.count > 0:
            avatar_data = await self.avatars.get_next()
        
        try:
            from playwright.async_api import async_playwright
            
            self.log("step", "Launching browser...")
            
            pargs = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-web-security",
                "--window-size=1366,768",
                "--start-maximized"
            ]
            
            browser_kwargs = {"headless": headless, "args": pargs}
            
            if proxy:
                browser_kwargs["proxy"] = {"server": f"http://{proxy}"}
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(**browser_kwargs)
                
                context_options = {
                    "locale": "en-US",
                    "timezone_id": "America/New_York",
                    "viewport": {"width": 1366, "height": 768},
                    "user_agent": self.current_user_agent if self.cfg.get("USER_AGENT_ROTATION") else USER_AGENTS[0]
                }
                
                context = await browser.new_context(**context_options)
                
                page = await context.new_page()
                token_found = None
                
                async def handle_route(route, request):
                    nonlocal token_found
                    
                    if self.cfg.get("REQUEST_INTERCEPTION"):
                        if "discord.com/api" in request.url:
                            headers = request.headers
                            headers.pop("sec-ch-ua-platform", None)
                            headers.pop("sec-ch-ua-mobile", None)
                            
                            if request.method == "POST":
                                try:
                                    response = await route.fetch(headers=headers)
                                    if response.status == 429:
                                        self.log("warning", "Rate limit detected in request")
                                        await asyncio.sleep(random.uniform(5, 10))
                                    await route.fulfill(response=response)
                                    return
                                except:
                                    pass
                    
                    if "discord.com/api/v9/auth/register" in request.url:
                        try:
                            response = await route.fetch()
                            body = await response.text()
                            data = json.loads(body)
                            if "token" in data:
                                token_found = data["token"]
                                self.log("success", "Token captured!")
                        except:
                            pass
                    await route.continue_()
                
                await page.route("**/discord.com/api/v9/auth/register", handle_route)
                
                if self.cfg.get("REQUEST_INTERCEPTION"):
                    await page.route("**/discord.com/api/**", handle_route)
                
                self.log("step", "Navigating to Discord...")
                await page.goto("https://discord.com/register", wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(2, 4))
                
                if await self.check_for_captcha(page):
                    success = await self.wait_for_manual_captcha(page)
                    if not success:
                        result.error = "CAPTCHA not solved"
                        await browser.close()
                        return result
                
                self.log("step", "Filling email...")
                try:
                    email_box = await page.locator("input[name='email']").bounding_box()
                    if email_box:
                        await self.human_mouse_move(page, int(email_box["x"] + 50), int(email_box["y"] + 15))
                except:
                    pass
                await page.click("input[name='email']", delay=random.randint(100, 300))
                await self.human_like_typing(page, "input[name='email']", email)
                await self.human_like_delay(500, 1200)
                
                self.log("step", "Filling display name...")
                try:
                    await page.click("input[name='global_name']", delay=random.randint(100, 300))
                    await self.human_like_typing(page, "input[name='global_name']", display_name)
                    await self.human_like_delay(400, 1000)
                except:
                    pass
                
                self.log("step", "Filling username...")
                await page.click("input[name='username']", delay=random.randint(100, 300))
                await self.human_like_typing(page, "input[name='username']", username)
                await self.human_like_delay(600, 1500)
                
                self.log("step", "Filling password...")
                await page.click("input[name='password']", delay=random.randint(100, 300))
                await self.human_like_typing(page, "input[name='password']", password)
                await self.human_like_delay(800, 2000)
                
                await page.click("div[class*='month']", delay=random.randint(200, 500))
                await self.human_like_delay(300, 700)
                for _ in range(random.randint(1, 3)):
                    await page.keyboard.press("ArrowDown")
                    await asyncio.sleep(0.1)
                await page.keyboard.type(month)
                await page.keyboard.press("Enter")
                await self.human_like_delay(400, 900)
                
                await page.click("div[class*='day']", delay=random.randint(200, 500))
                await self.human_like_delay(300, 700)
                await page.keyboard.type(day)
                await page.keyboard.press("Enter")
                await self.human_like_delay(400, 900)
                
                await page.click("div[class*='year']", delay=random.randint(200, 500))
                await self.human_like_delay(500, 1000)
                
                target_year = int(year)
                current_year = 2026
                scrolls_needed = current_year - target_year
                
                for _ in range(min(scrolls_needed, 50)):
                    await page.keyboard.press("ArrowDown")
                    await asyncio.sleep(random.uniform(0.05, 0.15))
                
                await page.keyboard.type(year)
                await asyncio.sleep(0.5)
                await page.keyboard.press("Enter")
                await self.human_like_delay(1000, 2500)
                
                self.log("step", "Submitting registration...")
                try:
                    submit_btn = await page.locator("button[type='submit']").bounding_box()
                    if submit_btn:
                        await self.human_mouse_move(page, int(submit_btn["x"] + 50), int(submit_btn["y"] + 15))
                except:
                    pass
                await page.click("button[type='submit']", delay=random.randint(200, 500))
                
                await asyncio.sleep(5)
                
                if await self.check_for_captcha(page):
                    success = await self.wait_for_manual_captcha(page)
                    if not success:
                        result.error = "CAPTCHA not solved after submit"
                        await browser.close()
                        return result
                
                self.log("step", "Waiting for verification email...")
                
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                msg = None
                start_time = time.time()
                
                while time.time() - start_time < 180:
                    msg = await self.mail.check_messages(login, domain, self.session)
                    if msg:
                        self.log("success", "Verification email received!")
                        break
                    await asyncio.sleep(3)
                
                if msg:
                    msg_id = msg.get("id")
                    verify_link = await self.mail.get_verify_link(login, domain, msg_id, self.session)
                    
                    if verify_link:
                        verify_page = await context.new_page()
                        await verify_page.goto(verify_link, wait_until="networkidle")
                        await asyncio.sleep(5)
                        await verify_page.close()
                
                await asyncio.sleep(3)
                
                if token_found:
                    result.token = token_found
                    result.success = True
                    self.save_token(result)
                    self.log("success", "Account created successfully!")
                    
                    if avatar_data and result.token:
                        await self.set_avatar(result.token, avatar_data)
                else:
                    result.error = "No token captured"
                    self.log("error", "Failed to capture token")
                
                await browser.close()
                
        except Exception as e:
            result.error = str(e)[:100]
            self.log("error", f"Error: {str(e)[:60]}")
            if proxy and self.proxies:
                self.proxies.mark_dead(proxy)
            
            if retry_count < self.cfg.get("RETRY_ATTEMPTS", 3):
                await asyncio.sleep(5)
                return await self.generate_one(use_proxy, headless, retry_count + 1)
        
        return result
    
    async def set_avatar(self, token: str, avatar_data: bytes):
        try:
            headers = {
                "Authorization": token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            b64_avatar = base64.b64encode(avatar_data).decode()
            data = {"avatar": f"data:image/png;base64,{b64_avatar}"}
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.patch(
                "https://discord.com/api/v10/users/@me",
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    self.log("success", "Avatar uploaded!")
        except:
            pass
    
    def save_token(self, result: GenResult):
        folder = self.cfg.get("OUTPUT_FOLDER", "output")
        path = os.path.join(folder, TOKENS_FILE)
        
        fmt = self.cfg.get("SAVE_FORMAT", "email:pass:token")
        
        if fmt == "email:pass:token":
            line = f"{result.email}:{result.password}:{result.token}\n"
        else:
            line = f"{result.token}\n"
        
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"# {result.timestamp} | {result.display_name}\n")
            f.write(line)
            f.write("-" * 50 + "\n\n")
    
    def banner(self):
        console.print(BANNER)
        console.print()
    
    def menu(self) -> Panel:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bright_magenta", width=2)
        table.add_column(style="white")
        
        table.add_row("1", "Generate Single (Manual CAPTCHA)")
        table.add_row("2", f"Generate Multiple ([cyan]up to {self.cfg.get('MAX_ACCOUNTS', 500)}[/cyan])")
        table.add_row("3", "View Results")
        table.add_row("4", "Check Proxies")
        table.add_row("5", "Settings")
        table.add_row("h", "Help")
        table.add_row("x", "[red]Exit[/red]")
        
        return Panel(table, title="[bold purple]Menu[/bold purple]", border_style="purple", padding=(1, 2))
    
    def status_panel(self) -> Panel:
        cfg = self.cfg.cfg
        parts = []
        
        if cfg.get("USE_PROXIES"):
            parts.append(f"Proxies: {self.proxies.status if self.proxies else 'OFF'}")
        
        parts.append(f"Max: {cfg.get('MAX_ACCOUNTS', 500)}")
        parts.append(f"UA Rotate: {'ON' if cfg.get('USER_AGENT_ROTATION') else 'OFF'}")
        parts.append(f"Intercept: {'ON' if cfg.get('REQUEST_INTERCEPTION') else 'OFF'}")
        
        text = " | ".join(parts) if parts else "[dim]Ready[/dim]"
        return Panel(text, border_style="purple", box=box.SIMPLE, title="[dim]Status[/dim]")
    
    def show_results(self):
        if not self.results:
            console.print("[dim]No activity[/dim]")
            return
        
        tree = Tree("[bold purple]Recent Activity[/bold purple]")
        
        for ts, lvl, msg in list(self.results)[-20:]:
            color = {"info": "cyan", "success": "green", "warning": "yellow", "error": "red", "step": "magenta"}.get(lvl, "white")
            icon = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗", "step": "→"}.get(lvl, "•")
            tree.add(f"[dim]{ts}[/dim] [{color}]{icon}[/{color}] {msg[:50]}")
        
        console.print(tree)
        
        if self.stats.total > 0:
            console.print()
            console.print(f"[bold]Stats:[/bold] [green]{self.stats.successful}[/green] | [red]{self.stats.failed}[/red] | [cyan]{self.stats.success_rate:.1f}%[/cyan]")
    
    def settings(self):
        while True:
            console.clear()
            self.banner()
            
            cfg = self.cfg.cfg
            t = Table(show_header=False, box=box.ROUNDED, border_style="purple", padding=(0, 2))
            t.add_column(style="bright_magenta", width=3)
            t.add_column(style="white", width=25)
            t.add_column(style="cyan")
            
            t.add_row("1", "Use Proxies", "[green]ON[/green]" if cfg.get("USE_PROXIES") else "[dim]OFF[/dim]")
            t.add_row("2", "Concurrent", f"[purple]{cfg.get('CONCURRENT', 1)}[/purple]")
            t.add_row("3", "Timeout", f"[purple]{cfg.get('TIMEOUT', 60)}s[/purple]")
            t.add_row("4", "Save Format", f"[cyan]{cfg.get('SAVE_FORMAT', 'email:pass:token')}[/cyan]")
            t.add_row("5", "Display Name", cfg.get("DISPLAY_NAME", "")[:25] or "[dim]Random[/dim]")
            t.add_row("6", "Use Avatar", "[green]ON[/green]" if cfg.get("USE_AVATAR") else "[dim]OFF[/dim]")
            t.add_row("7", "Headless Mode", "[yellow]ON[/yellow]" if cfg.get("HEADLESS") else "[dim]OFF[/dim]")
            t.add_row("8", "Max Accounts", f"[purple]{cfg.get('MAX_ACCOUNTS', 500)}[/purple]")
            t.add_row("9", "Human Mode", "[green]ON[/green]" if cfg.get("HUMAN_MODE") else "[dim]OFF[/dim]")
            t.add_row("10", "User Agent Rotation", "[green]ON[/green]" if cfg.get("USER_AGENT_ROTATION") else "[dim]OFF[/dim]")
            t.add_row("11", "Request Interception", "[green]ON[/green]" if cfg.get("REQUEST_INTERCEPTION") else "[dim]OFF[/dim]")
            t.add_row("", "", "")
            t.add_row("0", "Back", "")
            
            console.print(Panel(t, title="[bold purple]Settings[/bold purple]", border_style="purple"))
            
            c = console.input("[bold purple]>[/bold purple] ").strip()
            
            if c == "1":
                new_val = not cfg.get("USE_PROXIES")
                self.cfg.set("USE_PROXIES", new_val)
                if new_val and os.path.exists(self.cfg.get("PROXIES_FILE", "proxies.txt")):
                    self.proxies = ProxyManager(self.cfg.get("PROXIES_FILE", "proxies.txt"))
            elif c == "2":
                v = IntPrompt.ask("Concurrent (1-10)", default=cfg.get("CONCURRENT", 1))
                self.cfg.set("CONCURRENT", max(1, min(10, v)))
            elif c == "3":
                v = IntPrompt.ask("Timeout (30-300)", default=cfg.get("TIMEOUT", 60))
                self.cfg.set("TIMEOUT", max(30, min(300, v)))
            elif c == "4":
                f = console.input("Format (email:pass:token or token): ").strip()
                if f in ["email:pass:token", "token"]:
                    self.cfg.set("SAVE_FORMAT", f)
            elif c == "5":
                name = Prompt.ask("Display name prefix", default="")
                self.cfg.set("DISPLAY_NAME", name.strip())
            elif c == "6":
                self.cfg.set("USE_AVATAR", not cfg.get("USE_AVATAR"))
            elif c == "7":
                self.cfg.set("HEADLESS", not cfg.get("HEADLESS"))
            elif c == "8":
                v = IntPrompt.ask("Max accounts (1-500)", default=cfg.get("MAX_ACCOUNTS", 500))
                self.cfg.set("MAX_ACCOUNTS", max(1, min(500, v)))
            elif c == "9":
                self.cfg.set("HUMAN_MODE", not cfg.get("HUMAN_MODE"))
            elif c == "10":
                self.cfg.set("USER_AGENT_ROTATION", not cfg.get("USER_AGENT_ROTATION"))
            elif c == "11":
                self.cfg.set("REQUEST_INTERCEPTION", not cfg.get("REQUEST_INTERCEPTION"))
            elif c == "0":
                break
    
    def help(self):
        text = """
[bold purple]Nocta Gen v3.0[/bold purple] | Human Mode Enabled

[bright_magenta]Features:[/bright_magenta]
• Human-like mouse movements and typing patterns
• Randomized delays between actions
• Manual CAPTCHA solving prompts
• User Agent Rotation (setting 10)
• Request Interception (setting 11)

[bright_magenta]User Agent Rotation:[/bright_magenta]
Changes browser fingerprint for each account to prevent
tracking and linking multiple accounts together.

[bright_magenta]Request Interception:[/bright_magenta]
Modifies API requests to remove automation headers and
handles rate limit responses automatically.

[bright_magenta]Setup:[/bright_magenta]
pip install -r requirements.txt
playwright install chromium
        """
        console.print(Panel(text, title="[bold purple]Help[/bold purple]", border_style="purple"))
    
    async def run(self):
        if self.cfg.get("USE_PROXIES") and os.path.exists(self.cfg.get("PROXIES_FILE", "proxies.txt")):
            self.proxies = ProxyManager(self.cfg.get("PROXIES_FILE", "proxies.txt"))
        
        while True:
            console.clear()
            self.banner()
            console.print(self.menu())
            console.print(self.status_panel())
            
            choice = console.input("[bold purple]>[/bold purple] ").strip().lower()
            
            headless = self.cfg.get("HEADLESS", False)
            
            if choice == "1":
                self.log("info", "=== Starting Single Generation ===")
                result = await self.generate_one(self.cfg.get("USE_PROXIES", False), headless)
                
                if result.success:
                    await self.stats.increment_success()
                    self.log("success", "=== Success ===")
                else:
                    await self.stats.increment_fail()
                    self.log("error", f"=== Failed: {result.error} ===")
                
                console.input("[dim]Press Enter...[/dim]")
            
            elif choice == "2":
                max_allowed = self.cfg.get("MAX_ACCOUNTS", 500)
                count = IntPrompt.ask(f"How many (1-{max_allowed})", default=1)
                count = max(1, min(max_allowed, count))
                
                use_proxy = self.cfg.get("USE_PROXIES", False)
                
                for i in range(count):
                    self.log("info", f"=== Account {i+1}/{count} ===")
                    result = await self.generate_one(use_proxy, headless)
                    
                    if result.success:
                        await self.stats.increment_success()
                        self.log("success", "Account created")
                    else:
                        await self.stats.increment_fail()
                        self.log("error", f"Failed: {result.error}")
                    
                    if i < count - 1:
                        delay = random.randint(5, 15)
                        self.log("info", f"Waiting {delay}s before next...")
                        await asyncio.sleep(delay)
                
                console.input("[dim]Press Enter...[/dim]")
            
            elif choice == "3":
                self.show_results()
                console.input("[dim]Press Enter...[/dim]")
            
            elif choice == "4":
                if not self.cfg.get("USE_PROXIES"):
                    self.log("error", "Enable proxies first!")
                    console.input("[dim]Press Enter...[/dim]")
                    continue
                
                if not self.proxies:
                    if os.path.exists(self.cfg.get("PROXIES_FILE", "proxies.txt")):
                        self.proxies = ProxyManager(self.cfg.get("PROXIES_FILE", "proxies.txt"))
                    else:
                        self.log("error", "No proxies.txt found!")
                        console.input("[dim]Press Enter...[/dim]")
                        continue
                
                await self.check_proxies()
                console.input("[dim]Press Enter...[/dim]")
            
            elif choice == "5":
                self.settings()
            
            elif choice == "h":
                self.help()
                console.input("[dim]Press Enter...[/dim]")
            
            elif choice == "x":
                console.print("[purple]Goodbye[/purple]")
                if self.session:
                    await self.session.close()
                break

def main():
    gen = NoctaGen()
    try:
        asyncio.run(gen.run())
    except KeyboardInterrupt:
        console.print("\n[purple]Interrupted[/purple]")
        sys.exit(0)

if __name__ == "__main__":
    main()