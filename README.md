# aimyPlus Home Assistant Integration

Creates:

- `calendar.aimyplus`
- `sensor.aimyplus_amount_owing`

You only supply:

- Username
- Password
- Site slug, e.g. `horizons`

The integration builds the URL as:

`https://{site_slug}.aimyplus.com`

It logs in, fetches `/Parent/ParentDashboard`, extracts `parentId` from the page, parses `Current Amount Owing`, and uses the discovered `parentId` to fetch `/Parent/GetParentBookingList`.

## Install

Copy:

`custom_components/aimyplus`

into:

`/config/custom_components/aimyplus`

Restart Home Assistant.

Then go to:

Settings → Devices & services → Add integration → aimyPlus

## Notes

aimyPlus weekly bookings may appear as one long event if the API only returns a start/end range rather than individual appointment days.
