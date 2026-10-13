"""Visible Meta Business Suite controls for the dedicated Mini PC browser.

No private Meta endpoints, cookie export, or browser-session cloning are used.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from pathlib import Path

from scheduler.native_worker import IST, NativeFailure, binding, stamp

PAGE_ID = '124454514239741'
BUSINESS_ID = '327637346385766'
PLANNER = f'https://business.facebook.com/latest/content_calendar?asset_id={PAGE_ID}&business_id={BUSINESS_ID}'
COMPOSER = f'https://business.facebook.com/latest/composer/?asset_id={PAGE_ID}&business_id={BUSINESS_ID}'
CAPTION = 'Write into the dialogue box to include text with your post.'


def calendar_label(slot: dt.datetime) -> str:
    return slot.strftime('%a ') + str(slot.day)


def time_label(slot: dt.datetime) -> str:
    return str(slot.hour % 12 or 12) + slot.strftime(':%M %p')


class MetaBrowser:
    def __init__(self, context, workdir: Path):
        self.context = context
        self.workdir = workdir
        self.page = context.new_page()
        self.planner = context.new_page()
        self.image_hash = None
        self.item_binding = None

    def close(self):
        # Close worker-owned tabs only. Keep the persistent login browser alive.
        self.page.close()
        self.planner.close()

    def timezone(self, page):
        zone = page.evaluate('Intl.DateTimeFormat().resolvedOptions().timeZone')
        if zone not in {'Asia/Kolkata', 'Asia/Calcutta'}:
            raise NativeFailure('browser_timezone_must_be_IST')

    def visible(self, page, heading):
        page.get_by_role('heading', name=heading, exact=True).wait_for(state='visible', timeout=30000)
        if '/login' in page.url or '/checkpoint' in page.url:
            raise NativeFailure('meta_login_required')
        self.timezone(page)

    def selected_platforms(self):
        selector = self.page.get_by_role('combobox').filter(has_text=re.compile('Funzug|funzugdotcom'))
        if selector.count() != 1:
            raise NativeFailure('account_selector_changed')
        text = selector.inner_text()
        selected = []
        if 'Funzug' in text:
            selected.append('facebook')
        if 'funzugdotcom' in text:
            selected.append('instagram')
        # Unknown account names must never silently pass a loose substring test.
        cleaned = re.sub(r'[\s\u200b]+', ' ', text).strip()
        if cleaned not in {'Funzug', 'funzugdotcom', 'Funzug and funzugdotcom', 'Instagram Facebook Funzug and funzugdotcom'}:
            raise NativeFailure('unexpected_selected_account')
        return selected

    def select_platforms(self, platforms):
        selected = self.selected_platforms()
        if set(selected) == set(platforms):
            return
        self.page.get_by_role('combobox').filter(has_text=re.compile('Funzug|funzugdotcom')).click()
        for platform, name in [('facebook', 'Funzug'), ('instagram', 'funzugdotcom')]:
            option = self.page.get_by_role('option', name=name, exact=True)
            if option.count() != 1:
                raise NativeFailure('account_selector_changed')
            checked = option.get_attribute('aria-selected') == 'true'
            if checked != (platform in platforms):
                option.click()
        self.page.keyboard.press('Escape')
        if set(self.selected_platforms()) != set(platforms):
            raise NativeFailure('account_selection_unconfirmed')

    def spinner(self, locator, desired):
        for _ in range(65):
            current = locator.get_attribute('aria-valuenow')
            if current is None or not current.isdigit():
                raise NativeFailure('time_control_changed')
            current = int(current)
            if current == desired:
                return
            locator.press('ArrowUp' if current < desired else 'ArrowDown')
        raise NativeFailure('time_entry_unconfirmed')

    def prepare(self, packet: dict, image: bytes) -> dict:
        self.page.goto(COMPOSER, wait_until='domcontentloaded')
        self.visible(self.page, 'Create post')
        self.select_platforms(packet['platforms'])
        self.workdir.mkdir(parents=True, exist_ok=True)
        suffix = '.png' if packet['image']['mimeType'] == 'image/png' else '.jpg'
        media = self.workdir / ('reviewed' + suffix)
        media.write_bytes(image)
        media.chmod(0o600)
        try:
            with self.page.expect_file_chooser(timeout=15000) as event:
                self.page.get_by_role('button', name='Add photo/video', exact=True).click()
            event.value.set_files(str(media))
            self.page.get_by_role('button', name='Remove photo', exact=True).wait_for(timeout=45000)
            if self.page.get_by_role('button', name='Remove photo', exact=True).count() != 1:
                raise NativeFailure('unexpected_uploaded_media_count')
            # Bind the only uploaded file to the verified original bytes. No edit
            # or crop controls are used after this point.
            self.image_hash = hashlib.sha256(media.read_bytes()).hexdigest()
        finally:
            media.unlink(missing_ok=True)
        editor = self.page.get_by_role('combobox', name=CAPTION, exact=True)
        editor.click()
        self.page.keyboard.insert_text(packet['caption'])
        self.page.get_by_role('switch', name='Set date and time', exact=True).check()
        slot = stamp(packet['proposedSchedule'])
        dates = self.page.get_by_role('textbox', name='Date picker', exact=True)
        dates.first.wait_for(state='visible', timeout=15000)
        hours = self.page.get_by_role('spinbutton', name='hours', exact=True)
        minutes = self.page.get_by_role('spinbutton', name='minutes', exact=True)
        periods = self.page.get_by_role('spinbutton', name='meridiem', exact=True)
        if any(x.count() != len(packet['platforms']) for x in (dates, hours, minutes, periods)):
            raise NativeFailure('platform_time_controls_changed')
        for i in range(len(packet['platforms'])):
            dates.nth(i).press('ControlOrMeta+A')
            dates.nth(i).press_sequentially(slot.strftime('%m/%d/%Y'))
            dates.nth(i).press('Tab')
            self.spinner(hours.nth(i), slot.hour % 12 or 12)
            self.spinner(minutes.nth(i), slot.minute)
            self.spinner(periods.nth(i), int(slot.hour >= 12))
        self.item_binding = binding(packet)
        return self.prepared(packet)

    def prepared(self, packet: dict) -> dict:
        self.visible(self.page, 'Create post')
        if self.item_binding != binding(packet) or set(self.selected_platforms()) != set(packet['platforms']):
            raise NativeFailure('composer_binding_changed')
        if self.page.get_by_role('button', name='Remove photo', exact=True).count() != 1 or not self.image_hash:
            raise NativeFailure('reviewed_media_missing')
        editor = self.page.get_by_role('combobox', name=CAPTION, exact=True)
        caption = editor.evaluate("el => Array.from(el.querySelectorAll('[data-block]')).map(b=>b.textContent).join('\\n')")
        if caption != packet['caption']:
            raise NativeFailure('caption_entry_unconfirmed')
        slot = stamp(packet['proposedSchedule'])
        for i in range(len(packet['platforms'])):
            date = self.page.get_by_role('textbox', name='Date picker', exact=True).nth(i).input_value()
            try:
                parsed = dt.datetime.strptime(date, '%b %d, %Y').date()
            except ValueError:
                try:
                    parsed = dt.datetime.strptime(date, '%m/%d/%Y').date()
                except ValueError:
                    raise NativeFailure('date_entry_unconfirmed') from None
            if parsed != slot.date():
                raise NativeFailure('date_entry_unconfirmed')
            for name, expected in [('hours', slot.hour % 12 or 12), ('minutes', slot.minute), ('meridiem', int(slot.hour >= 12))]:
                if self.page.get_by_role('spinbutton', name=name, exact=True).nth(i).get_attribute('aria-valuenow') != str(expected):
                    raise NativeFailure('time_entry_unconfirmed')
        for name in ('Boost', 'Share to Facebook Story', 'Customize post for Facebook and Instagram'):
            control = self.page.get_by_role('switch', name=name, exact=True)
            if control.count() != 1 or control.is_checked():
                raise NativeFailure('unexpected_composer_option')
        schedule = self.page.get_by_role('button', name='Schedule', exact=True)
        if schedule.count() != 1 or not schedule.is_enabled():
            raise NativeFailure('schedule_button_unavailable')
        return {**binding(packet), 'caption': caption, 'image_sha256': self.image_hash, 'timezone': 'Asia/Kolkata', 'story': False, 'boost': False}

    def submit(self):
        self.page.get_by_role('button', name='Schedule', exact=True).click(timeout=15000)
        # Any timeout returns to controller reconciliation, never click again.

    def inspect(self, packet: dict) -> dict:
        self.planner.goto(PLANNER, wait_until='domcontentloaded')
        self.visible(self.planner, 'Planner')
        self.planner.get_by_role('button', name='Week', exact=True).click()
        slot = stamp(packet['proposedSchedule'])
        today = dt.datetime.now(IST)
        delta = (slot.date() - today.date()).days
        if not 0 <= delta <= 28:
            raise NativeFailure('native_slot_outside_review_window')
        self.planner.get_by_role('button', name='Today', exact=True).click()
        # Meta renders the toolbar before its calendar data. Reading immediately
        # can advance five empty weeks before the first date header exists.
        dates = self.planner.get_by_text(re.compile(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+[0-9]{1,2}$'))
        dates.first.wait_for(state='visible', timeout=45000)
        target = calendar_label(slot)
        for _ in range(5):
            header = self.planner.get_by_text(target, exact=True)
            if header.count() == 1:
                break
            previous = dates.first.inner_text()
            self.planner.get_by_role('button', name='Right', exact=True).click()
            self.planner.get_by_text(previous,exact=True).wait_for(state='hidden',timeout=15000)
            self.planner.get_by_text(re.compile(r'^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+[0-9]{1,2}$')).first.wait_for(state='visible', timeout=15000)
        else:
            raise NativeFailure('planner_date_not_visible')
        month = self.planner.get_by_role('heading', name=slot.strftime('%B'), exact=True)
        year = self.planner.get_by_role('heading', name=str(slot.year), exact=True)
        if month.count() != 1 or year.count() != 1:
            raise NativeFailure('planner_month_not_confirmed')
        header = self.planner.get_by_text(target, exact=True)
        bounds = header.evaluate('el=>{const r=el.parentElement.getBoundingClientRect();return {left:r.left,right:r.right}}')
        cards = self.planner.get_by_label(packet['caption'], exact=True)
        results = {}
        for platform in packet['platforms']:
            name = time_label(slot) + (' Facebook' if platform == 'facebook' else ' Instagram')
            candidates = cards.get_by_role('link', name=name, exact=True)
            matching = []
            for candidate in candidates.all():
                position = candidate.bounding_box()
                if position and bounds['left'] <= position['x'] + position['width'] / 2 <= bounds['right']:
                    matching.append(candidate)
            if not matching:
                continue
            if len(matching) != 1:
                raise NativeFailure('duplicate_planner_candidates')
            matching[0].click()
            self.planner.get_by_role('heading', name='Post details', exact=True).wait_for(timeout=15000)
            detail = self.planner.get_by_text(re.compile(r'^ID: [0-9]+$'))
            if detail.count() != 1:
                raise NativeFailure('planner_identifier_not_visible')
            identifier = re.fullmatch(r'ID: ([0-9]+)', detail.inner_text())
            if not identifier:
                raise NativeFailure('planner_identifier_not_visible')
            # The exact caption, platform and slot were read from the planner
            # card in the verified date column before opening this detail.
            results[platform] = {'platform': platform, 'schedule_id': identifier.group(1), 'scheduled_at': slot.isoformat(), 'content_hash': packet['contentHash'], 'planner_url': self.planner.url, 'checked_at': dt.datetime.now(IST).isoformat()}
            closes = self.planner.get_by_role('button', name='Close', exact=True)
            if closes.count() != 1:
                raise NativeFailure('planner_detail_close_changed')
            closes.click()
        return results
