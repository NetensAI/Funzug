"""Visible Meta Business Suite controls for the dedicated Mini PC browser.

No private Meta endpoints, cookie export, or browser-session cloning are used.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,urljoin

from scheduler.native_worker import IST, NativeFailure, binding, stamp, verify_package, verify_ordered_package
from scheduler.publication_evidence import publication_time
from scheduler.native_media_files import stage_reviewed_media

PAGE_ID = '124454514239741'
BUSINESS_ID = '327637346385766'
PLANNER = f'https://business.facebook.com/latest/content_calendar?asset_id={PAGE_ID}&business_id={BUSINESS_ID}'
COMPOSER = f'https://business.facebook.com/latest/composer/?asset_id={PAGE_ID}&business_id={BUSINESS_ID}'
CAPTION = 'Write into the dialogue box to include text with your post.'
REEL_DATE = 'Select a future date and time to publish your reel at. Date picker'


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
        self.uploaded_thumbnail_urls = None
        self.media_hashes = None
        self.reel_upload_binding = None
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

    def open_reel_composer(self, platforms):
        """Navigate to the observed native Reel wizard without uploading media."""
        self.page.goto(PLANNER)
        self.visible(self.page, 'Planner')
        self.page.get_by_role('button', name='Create', exact=True).click()
        self.page.get_by_role('menuitem', name='Create reel', exact=True).click()
        self.visible(self.page, 'Create reel')
        self.select_platforms(platforms)
        if self.page.get_by_role('button', name='Add Video', exact=True).count() != 1:
            raise NativeFailure('reel_composer_changed')
        next_button = self.page.get_by_role('button', name='Next', exact=True)
        if next_button.count() != 1 or next_button.is_enabled():
            raise NativeFailure('reel_composer_not_empty')
        caption = self.page.get_by_role('textbox', name=CAPTION, exact=True)
        if caption.count() != 1 or caption.input_value():
            raise NativeFailure('reel_composer_not_empty')

    def upload_reviewed_reel(self, packet, assets):
        """Validate and upload one original MP4; never advance or submit it."""
        if packet.get('format') != 'reel':
            raise NativeFailure('unsupported_native_media_format')
        verified = verify_ordered_package(packet)
        if verified != assets:
            raise NativeFailure('reviewed_media_file_changed')
        self.visible(self.page, 'Create reel')
        if self.page.get_by_role('button', name='Delete', exact=True).count():
            raise NativeFailure('composer_not_empty')
        self.reel_upload_binding = None
        asset = packet['media'][0]
        with stage_reviewed_media(packet, assets, self.workdir) as (paths, hashes):
            with self.page.expect_file_chooser(timeout=15000) as event:
                self.page.get_by_role('button', name='Add Video', exact=True).click()
            event.value.set_files(str(paths[0]))
            self.page.get_by_text(paths[0].name, exact=True).wait_for(state='visible', timeout=45000)
            self.page.get_by_text(f"{asset['width']} x {asset['height']}", exact=True).wait_for(state='visible', timeout=45000)
            delete = self.page.get_by_role('button', name='Delete', exact=True)
            if delete.count() != 1:
                raise NativeFailure('unexpected_uploaded_media_count')
            self.reel_upload_binding = {**binding(packet), 'filename':paths[0].name,
                                        'sha256':hashes[0], 'width':asset['width'],
                                        'height':asset['height'], 'durationMs':asset['durationMs']}
        return dict(self.reel_upload_binding)

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

    def prepare(self, packet: dict, image: bytes | list[bytes]) -> dict:
        if packet.get('format', 'image') not in {'image', 'carousel'}:
            raise NativeFailure('unsupported_native_media_format')
        self.page.goto(COMPOSER, wait_until='domcontentloaded')
        self.visible(self.page, 'Create post')
        self.select_platforms(packet['platforms'])
        hashes = self.upload_reviewed_images(packet, image)
        self.image_hash = hashes[0] if packet.get('format', 'image') == 'image' else None
        self.media_hashes = hashes if packet.get('format') == 'carousel' else None
        editor = self.page.get_by_role('combobox', name=CAPTION, exact=True)
        editor.click()
        self.page.keyboard.insert_text(packet['caption'])
        self.page.get_by_role('switch', name='Set date and time', exact=True).check()
        self.set_post_schedule(packet)
        self.item_binding = binding(packet)
        return self.prepared(packet)

    def upload_reviewed_images(self, packet, assets):
        """Upload sequentially; this alone is not proof of visible slide order."""
        media_format = packet.get('format', 'image')
        if media_format == 'image':
            verified = verify_package(packet)
        elif media_format == 'carousel':
            verified = verify_ordered_package(packet)
        else:
            raise NativeFailure('unsupported_native_media_format')
        if verified != assets:
            raise NativeFailure('reviewed_media_file_changed')
        remove = self.page.get_by_role('button', name='Remove photo', exact=True)
        if remove.count() != 0:
            raise NativeFailure('composer_not_empty')
        self.uploaded_thumbnail_urls = None
        thumbnails = []
        with stage_reviewed_media(packet, assets, self.workdir) as (paths, hashes):
            for index, path in enumerate(paths):
                with self.page.expect_file_chooser(timeout=15000) as event:
                    self.page.get_by_role('button', name='Add photo/video', exact=True).click()
                event.value.set_files(str(path))
                remove.nth(index).wait_for(state='visible', timeout=45000)
                if remove.count() != index + 1:
                    raise NativeFailure('unexpected_uploaded_media_count')
                if media_format == 'carousel':
                    observed = self.carousel_thumbnail_urls()
                    if observed[:-1] != thumbnails or observed[-1] in thumbnails:
                        raise NativeFailure('uploaded_media_order_changed')
                    thumbnails = observed
            if media_format == 'carousel':
                self.uploaded_thumbnail_urls = tuple(thumbnails)
            return hashes

    def carousel_thumbnail_urls(self):
        """Read the observed per-slide thumbnail boundary, never broad page images."""
        urls = self.page.get_by_role('button', name='Remove photo', exact=True).evaluate_all("""elements => elements.map(el => {
            let parent = el;
            for (let depth = 0; depth < 4; depth++) parent = parent && parent.parentElement;
            if (!parent) return null;
            const images = parent.querySelectorAll('img');
            return images.length === 1 ? images[0].getAttribute('src') : null;
        })""")
        if not isinstance(urls, list) or not 1 <= len(urls) <= 10:
            raise NativeFailure('carousel_thumbnails_unconfirmed')
        for url in urls:
            if not isinstance(url, str):
                raise NativeFailure('carousel_thumbnails_unconfirmed')
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.fbcdn.net') or parsed.username or parsed.password or parsed.port not in {None,443}:
                raise NativeFailure('carousel_thumbnails_unconfirmed')
        if len(set(urls)) != len(urls):
            raise NativeFailure('carousel_thumbnails_unconfirmed')
        return urls

    def verify_carousel_upload_order(self, count):
        if not self.uploaded_thumbnail_urls or len(self.uploaded_thumbnail_urls) != count or tuple(self.carousel_thumbnail_urls()) != self.uploaded_thumbnail_urls:
            raise NativeFailure('uploaded_media_order_changed')

    def set_post_schedule(self, packet):
        """Shared image-post time controls, not the separate Reel wizard."""
        self.set_schedule_fields(packet, 'Date picker')

    def set_reel_schedule(self, packet):
        """Select the scheduling option only; never click the final submit action."""
        self.visible(self.page, 'Create reel')
        self.page.get_by_role('heading', name='Scheduling options', exact=True).wait_for(state='visible', timeout=15000)
        option = self.page.get_by_role('button', name='Schedule', exact=True).and_(self.page.locator('[aria-pressed]'))
        if option.count() != 1:
            raise NativeFailure('reel_schedule_option_ambiguous')
        if option.get_attribute('aria-pressed') != 'true':
            option.click()
        if option.get_attribute('aria-pressed') != 'true':
            raise NativeFailure('reel_schedule_option_unconfirmed')
        self.set_schedule_fields(packet, REEL_DATE)

    def set_schedule_fields(self, packet, date_name):
        self.timezone(self.page)
        if packet.get('scheduleTimezone') != 'Asia/Kolkata':
            raise NativeFailure('invalid_timezone')
        slot = stamp(packet['proposedSchedule'])
        dates = self.page.get_by_role('textbox', name=date_name, exact=True)
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
    def prepared(self, packet: dict) -> dict:
        self.visible(self.page, 'Create post')
        if self.item_binding != binding(packet) or set(self.selected_platforms()) != set(packet['platforms']):
            raise NativeFailure('composer_binding_changed')
        media_format = packet.get('format', 'image')
        if media_format == 'carousel':
            self.verify_carousel_upload_order(len(packet.get('media', [])))
            assets = verify_ordered_package(packet)
            if self.media_hashes != [hashlib.sha256(asset).hexdigest() for asset in assets]:
                raise NativeFailure('reviewed_media_missing')
            media_proof = {'format':'carousel', 'media_sha256':list(self.media_hashes)}
        elif media_format == 'image':
            if self.page.get_by_role('button', name='Remove photo', exact=True).count() != 1 or not self.image_hash:
                raise NativeFailure('reviewed_media_missing')
            media_proof = {'image_sha256':self.image_hash}
        else:
            raise NativeFailure('unsupported_native_media_format')
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
        return {**binding(packet), 'caption': caption, **media_proof, 'timezone': 'Asia/Kolkata', 'story': False, 'boost': False}

    def submit(self):
        self.page.get_by_role('button', name='Schedule', exact=True).click(timeout=15000)
        # Any timeout returns to controller reconciliation, never click again.

    def planner_cards(self, packet: dict, allow_past=False):
        self.planner.goto(PLANNER, wait_until='domcontentloaded')
        self.visible(self.planner, 'Planner')
        self.planner.get_by_role('button', name='Week', exact=True).click()
        slot = stamp(packet['proposedSchedule'])
        today = dt.datetime.now(IST)
        delta = (slot.date() - today.date()).days
        if not (-28 if allow_past else 0) <= delta <= 28:
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
            self.planner.get_by_role('button', name='Left' if delta<0 else 'Right', exact=True).click()
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
        return cards,bounds

    def inspect(self, packet: dict) -> dict:
        cards,bounds=self.planner_cards(packet)
        slot=stamp(packet['proposedSchedule'])
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

    def inspect_publication(self, packet: dict) -> dict:
        """Read published evidence only. Never interact with delivery controls."""
        handoff=packet.get('nativeHandoff',{})
        if handoff.get('state')!='scheduled':
            raise NativeFailure('publication_requires_scheduled_receipts')
        cards,bounds=self.planner_cards(packet,allow_past=True)
        links={}
        for platform in packet['platforms']:
            label='Facebook' if platform=='facebook' else 'Instagram'
            choices=cards.locator('a[href]').filter(has=self.planner.get_by_role('img',name=label,exact=True))
            matches=[]
            for link in choices.all():
                position=link.bounding_box()
                if position and bounds['left']<=position['x']+position['width']/2<=bounds['right'] and re.sub(r'\s+',' ',link.inner_text()).strip()==time_label(stamp(packet['proposedSchedule'])):
                    href=urljoin(PLANNER,link.get_attribute('href') or '')
                    parsed=urlsplit(href)
                    values=parse_qs(parsed.query).get('content_id',[])
                    if parsed.scheme=='https' and parsed.hostname=='business.facebook.com' and not parsed.username and not parsed.password and parsed.path.rstrip('/')=='/latest/insights/object_insights' and len(values)==1 and re.fullmatch(r'[0-9]+',values[0]):
                        matches.append(values[0])
            if len(matches)!=1:
                raise NativeFailure('published_planner_link_not_unique')
            links[platform]=matches[0]
        results={}
        for platform in packet['platforms']:
            scheduled_id=handoff.get('receipts',{}).get(platform,{}).get('schedule_id')
            if not isinstance(scheduled_id,str) or not re.fullmatch(r'[0-9]+',scheduled_id):
                raise NativeFailure('publication_identifier_missing')
            identifier=links[platform]
            url='https://business.facebook.com/latest/insights/object_insights/?content_id='+identifier
            self.planner.goto(url,wait_until='domcontentloaded')
            self.planner.get_by_role('heading',name=packet['caption'],exact=True).wait_for(timeout=45000)
            self.timezone(self.planner)
            observed=urlsplit(self.planner.url)
            if observed.scheme!='https' or observed.hostname!='business.facebook.com' or observed.path.rstrip('/')!='/latest/insights/object_insights' or parse_qs(observed.query).get('content_id')!=[identifier]:
                raise NativeFailure('publication_identifier_changed')
            account='Funzug' if platform=='facebook' else 'funzugdotcom'
            self.planner.get_by_text(account,exact=True).first.wait_for(state='visible',timeout=15000)
            destination='View post on Facebook' if platform=='facebook' else 'View post on Instagram'
            self.planner.get_by_text(destination,exact=True).wait_for(state='visible',timeout=15000)
            labels=self.planner.get_by_text(re.compile(r'^Post · Published on: '))
            if labels.count()!=1:
                raise NativeFailure('publication_label_not_confirmed')
            published=publication_time(labels.inner_text(),packet['proposedSchedule'],dt.datetime.now(IST))
            results[platform]={'post_id':identifier,'published_at':published,'evidence_url':url}
            if identifier!=scheduled_id:
                results[platform].update(scheduled_post_id=scheduled_id,content_hash=packet['contentHash'])
        return {'platform_results':results}
