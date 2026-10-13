"""Parse observed Meta publication labels without inferring success from a slot."""
import datetime as dt
import re
from scheduler.native_worker import IST,NativeFailure,stamp


def publication_time(label, approved_slot, now):
    match=re.fullmatch(r'Post · Published on: ([A-Z][a-z]{2} [A-Z][a-z]{2} [0-9]{1,2}), ([0-9]{1,2}:[0-9]{2})(am|pm)',label)
    if not match:
        raise NativeFailure('publication_label_not_confirmed')
    slot=stamp(approved_slot)
    try:
        observed=dt.datetime.strptime(f'{slot.year} {match[1]} {match[2]}{match[3]}','%Y %a %b %d %I:%M%p').replace(tzinfo=IST)
    except ValueError:
        raise NativeFailure('publication_time_invalid') from None
    # strptime accepts an inconsistent weekday; verify the visible label too.
    if observed.strftime('%a %b ')+str(observed.day)!=match[1]:
        raise NativeFailure('publication_date_not_confirmed')
    if observed>now or abs(observed-slot)>dt.timedelta(minutes=15):
        raise NativeFailure('publication_time_outside_approved_slot')
    return observed.isoformat()
