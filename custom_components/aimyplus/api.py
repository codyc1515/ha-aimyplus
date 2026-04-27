import re
from datetime import datetime, timezone, timedelta
from html import unescape
from zoneinfo import ZoneInfo

from .const import BASE_DOMAIN

MS_DATE_RE = re.compile(r"/Date\((\d+)\)/")
LOCAL_TZ = ZoneInfo("Pacific/Auckland")

AMOUNT_RE = re.compile(
    r"Current\s+Amount\s+Owing:\s*<b[^>]*>\s*\$?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    re.IGNORECASE | re.DOTALL,
)
PARENT_ID_RE = re.compile(
    r"(?:parentId=|parentId:\s*|parentId&quot;:\s*&quot;|parentId['\"]?\s*[:=]\s*['\"]?)(\d+)",
    re.IGNORECASE,
)


def parse_ms_date(value):
    """Parse ASP.NET /Date(1776739500000)/ into a timezone-aware UTC datetime."""
    if not value:
        return None

    match = MS_DATE_RE.search(str(value))
    if not match:
        return None

    return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc)


def parse_localized_date(value):
    """Parse Aimy Plus LocalizedStartDate/LocalizedEndDate values like 28/04/2026."""
    if not value:
        return None

    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass

    return None


def parse_aimy_datetime(ms_value, localized_date_value=None):
    """Return an NZ-local datetime for Aimy Plus booking-list timestamps."""
    timestamp_dt = parse_ms_date(ms_value)
    if not timestamp_dt:
        return None

    local_dt = timestamp_dt.astimezone(LOCAL_TZ)
    localized_date = parse_localized_date(localized_date_value)

    if localized_date:
        return datetime.combine(localized_date, local_dt.timetz(), tzinfo=LOCAL_TZ)

    return local_dt


def parse_calendar_datetime(value):
    """Parse dates returned by /Parent/GetParentBookingCalender.

    Aimy Plus calendar values are local appointment times. If the API returns a
    naive ISO value such as 2026-04-28T14:45:00, treat it as Pacific/Auckland,
    not UTC. Treating it as UTC is what shifted 2:45pm on 28 April to 2:45am
    on 29 April in Home Assistant.
    """
    if not value:
        return None

    parsed = parse_ms_date(value)
    if parsed:
        return parsed.astimezone(LOCAL_TZ)

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=LOCAL_TZ)

    return parsed.astimezone(LOCAL_TZ)


def parse_amount_owing(html):
    if not html:
        return None

    html = unescape(html)
    match = AMOUNT_RE.search(html)
    if not match:
        return None

    return float(match.group(1).replace(",", ""))


def parse_parent_id(html):
    if not html:
        return None

    html = unescape(html)
    match = PARENT_ID_RE.search(html)
    if not match:
        return None

    return int(match.group(1))


class AimyPlusApi:
    def __init__(self, session, site_slug: str, username: str, password: str):
        self.session = session
        self.site_slug = site_slug.strip().lower()
        self.base_url = f"https://{self.site_slug}.{BASE_DOMAIN}"
        self.username = username
        self.password = password
        self._dashboard_html = None
        self._parent_id = None

    async def login(self):
        login_url = f"{self.base_url}/Account/Login?ReturnUrl=%2F"

        async with self.session.post(
            login_url,
            data={
                "UserName": self.username,
                "Password": self.password,
                "submit": "Login",
                "RememberMe": "false",
            },
            headers={
                "Origin": self.base_url,
                "Referer": login_url,
                "User-Agent": "Mozilla/5.0",
            },
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            await resp.text()

    async def get_dashboard_html(self, force_refresh=False):
        if self._dashboard_html and not force_refresh:
            return self._dashboard_html

        await self.login()

        async with self.session.get(
            f"{self.base_url}/Parent/ParentDashboard",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": f"{self.base_url}/Account/Login?ReturnUrl=%2f",
                "User-Agent": "Mozilla/5.0",
            },
        ) as resp:
            resp.raise_for_status()
            self._dashboard_html = await resp.text()

        return self._dashboard_html

    async def get_parent_id(self):
        if self._parent_id:
            return self._parent_id

        html = await self.get_dashboard_html()
        parent_id = parse_parent_id(html)

        if not parent_id:
            raise RuntimeError("Could not find parentId on Aimy Plus dashboard")

        self._parent_id = parent_id
        return parent_id

    async def get_bookings(self):
        parent_id = await self.get_parent_id()

        async with self.session.get(
            f"{self.base_url}/Parent/GetParentBookingList",
            params={
                "parentId": str(parent_id),
                "isCurrentTerm": "false",
            },
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/Parent/ParentDashboard",
                "User-Agent": "Mozilla/5.0",
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

        if not data.get("Success"):
            raise RuntimeError("Aimy Plus returned Success=false")

        return [
            booking
            for booking in data.get("bookingList", [])
            if not booking.get("IsCancelled") and booking.get("Status") == "Confirmed"
        ]

    async def get_calendar_events(self, start_date, end_date):
        """Fetch individual booking instances from the dashboard calendar endpoint."""
        parent_id = await self.get_parent_id()

        async with self.session.post(
            f"{self.base_url}/Parent/GetParentBookingCalender",
            data={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "parentId": str(parent_id),
            },
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/Parent/ParentDashboard",
                "User-Agent": "Mozilla/5.0",
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

        if isinstance(data, dict):
            raw_events = data.get("events") or data.get("Events") or data.get("data") or data.get("Data") or []
        else:
            raw_events = data or []

        events = []
        for item in raw_events:
            event = calendar_item_to_event(item)
            if event:
                events.append(event)

        return events

    async def get_amount_owing(self):
        html = await self.get_dashboard_html(force_refresh=True)
        return parse_amount_owing(html)


def _description(*lines):
    return "\n".join(str(line) for line in lines if line and not str(line).endswith("None"))


def _booking_event_payload(booking, start, end):
    child_name = booking.get("ChildName") or "Child"
    programme = (booking.get("ProgrammeName") or "Aimy Plus").strip()
    billing_id = booking.get("BillingId") or f"{child_name}-{start.isoformat()}"

    return {
        "uid": f"{billing_id}-{start.date().isoformat()}",
        "summary": f"{programme} - {child_name}",
        "start": start,
        "end": end,
        "description": _description(
            f"Child: {booking.get('ChildName')}",
            f"Programme: {booking.get('ProgrammeName')}",
            f"Organisation: {booking.get('OrgName')}",
            f"Term: {booking.get('Term')}",
            f"Frequency: {booking.get('Frequency')}",
            f"Status: {booking.get('Status')}",
            f"Billing ID: {booking.get('BillingId')}",
        ),
        "location": booking.get("OrgName"),
    }


def booking_to_events(booking):
    """Convert booking-list rows to appointment instances.

    GetParentBookingList represents recurring bookings as one row whose
    StartDate is the first appointment start and EndDate is the last
    appointment end. That row must be expanded into weekly occurrences;
    otherwise Home Assistant renders it as one long multi-week event.
    """
    start = parse_aimy_datetime(booking.get("StartDate"), booking.get("LocalizedStartDate"))
    end = parse_aimy_datetime(booking.get("EndDate"), booking.get("LocalizedEndDate"))

    if not start:
        return []

    if not end or end <= start:
        end = start + timedelta(hours=1)

    localized_start = parse_localized_date(booking.get("LocalizedStartDate")) or start.date()
    localized_end = parse_localized_date(booking.get("LocalizedEndDate")) or end.date()

    if localized_end <= localized_start:
        return [_booking_event_payload(booking, start, end)]

    frequency = str(booking.get("Frequency") or "").strip().lower()
    if frequency != "weekly":
        return [_booking_event_payload(booking, start, end)]

    events = []
    current_date = localized_start
    while current_date <= localized_end:
        occurrence_start = datetime.combine(current_date, start.timetz(), tzinfo=LOCAL_TZ)
        occurrence_end = datetime.combine(current_date, end.timetz(), tzinfo=LOCAL_TZ)
        if occurrence_end <= occurrence_start:
            occurrence_end = occurrence_start + timedelta(hours=1)
        events.append(_booking_event_payload(booking, occurrence_start, occurrence_end))
        current_date += timedelta(days=7)

    return events


def booking_to_event(booking):
    """Backward-compatible wrapper returning the first expanded event."""
    events = booking_to_events(booking)
    return events[0] if events else None


def calendar_item_to_event(item):
    start = parse_calendar_datetime(item.get("start") or item.get("Start") or item.get("StartDate"))
    end = parse_calendar_datetime(item.get("end") or item.get("End") or item.get("EndDate"))

    if not start:
        return None

    if not end or end <= start:
        end = start + timedelta(hours=1)

    title = (
        item.get("title")
        or item.get("Title")
        or item.get("summary")
        or item.get("Summary")
        or "Aimy Plus booking"
    )
    site_name = item.get("siteName") or item.get("SiteName") or item.get("location") or item.get("Location")
    status = item.get("bookingStatus") or item.get("BookingStatus") or item.get("status") or item.get("Status")
    program_category = item.get("programCategory") or item.get("ProgramCategory")
    children = item.get("children") or item.get("Children") or []

    child_names = []
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                name = child.get("childName") or child.get("ChildName")
                if name:
                    child_names.append(name)

    return {
        "uid": str(item.get("id") or item.get("Id") or item.get("uid") or f"{title}-{start.isoformat()}"),
        "summary": str(title),
        "start": start,
        "end": end,
        "description": _description(
            f"Status: {status}" if status else None,
            f"Programme category: {program_category}" if program_category else None,
            "Children: " + ", ".join(child_names) if child_names else None,
        ),
        "location": site_name,
    }
