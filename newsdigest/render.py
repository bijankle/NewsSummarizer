"""Station five: lay out the email (HTML plus plain text) and the web page data."""

from datetime import date
from html import escape

REGION_LABELS = {"perth": "Perth", "australia": "Australia", "international": "International"}

COLOURS = {
    "ink": "#1d2329", "muted": "#5b6670", "rule": "#dfe3e7", "paper": "#ffffff",
    "tag": "#eef2f5", "accent": "#0b5cad", "update": "#b3541e", "update_bg": "#fdf3ec",
}


def long_date(d):
    return f"{d:%A} {d.day} {d:%B %Y}"


def story_to_dict(story, categories, in_email):
    return {
        "id": story.id,
        "headline": story.headline or story.items[0].title,
        "facts": story.facts,
        "key_numbers": story.key_numbers,
        "why_it_matters": story.why_it_matters,
        "category": story.category,
        "category_label": categories[story.category]["label"],
        "region": story.region,
        "importance": story.importance,
        "is_update": bool(story.previous),
        "update_summary": story.update_summary,
        "previous": {
            "date": story.previous.get("date", ""),
            "headline": story.previous.get("headline", ""),
            "facts": story.previous.get("facts", ""),
        } if story.previous else None,
        "debate": story.debate,
        "sources": story.sources[:6],
        "published": story.published.isoformat() if story.published else None,
        "processed": story.processed,
        "in_email": in_email,
    }


def _nice_date(iso):
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or "an earlier day"
    return f"{d.day} {d:%B}"


def _tags_html(s):
    c = COLOURS
    style = f"display:inline-block;background:{c['tag']};color:{c['muted']};font-size:11px;letter-spacing:.04em;padding:2px 7px;border-radius:3px;margin-right:4px;text-transform:uppercase"
    tags = [REGION_LABELS.get(s["region"], s["region"]), s["category_label"]]
    out = ""
    if s["is_update"]:
        out += f'<span style="{style};background:{c["update"]};color:#fff;font-weight:bold">Update</span>'
    return out + "".join(f'<span style="{style}">{escape(t)}</span>' for t in tags)


def _sources_html(s):
    links = ", ".join(
        f'<a href="{escape(src["url"])}" style="color:{COLOURS["accent"]}">{escape(src["name"])}</a>'
        for src in s["sources"]
    )
    n = len(s["sources"])
    label = "Source" if n == 1 else f"Reported by {n} outlets"
    return f'<p style="margin:8px 0 0;font-size:12px;color:{COLOURS["muted"]}">{label}: {links}</p>'


def _body_html(s):
    c = COLOURS
    out = ""
    if s["facts"]:
        out += f'<p style="margin:6px 0">{escape(s["facts"])}</p>'
    elif not s["processed"]:
        out += f'<p style="margin:6px 0;color:{c["muted"]};font-style:italic">Summary not available for this run. Headline only.</p>'
    if s["key_numbers"]:
        nums = "<br>".join(escape(n) for n in s["key_numbers"])
        out += f'<p style="margin:6px 0;padding:6px 10px;border-left:3px solid {c["accent"]};background:#f6f9fc;font-size:14px"><b>Key numbers</b><br>{nums}</p>'
    if s["why_it_matters"]:
        out += f'<p style="margin:6px 0"><b>Why it matters.</b> {escape(s["why_it_matters"])}</p>'
    return out


def story_html(s):
    c = COLOURS
    head = f'<div style="margin-bottom:4px">{_tags_html(s)}</div><h2 style="font-size:18px;line-height:1.3;margin:4px 0 6px;color:{c["ink"]}">{escape(s["headline"])}</h2>'
    if s["is_update"]:
        prev = s["previous"]
        new = escape(s["update_summary"] or "New details have been reported.")
        body = (
            f'<p style="margin:6px 0;padding:8px 10px;background:{c["update_bg"]};border-left:3px solid {c["update"]}"><b>What is new.</b> {new}</p>'
            f'{_body_html(s)}'
            f'<div style="margin-top:10px;padding:8px 10px;border:1px dashed {c["rule"]};font-size:13px;color:{c["muted"]}">'
            f'<b>Original story, sent on {escape(_nice_date(prev["date"]))}</b><br>{escape(prev["headline"])}. {escape(prev["facts"])}</div>'
        )
    else:
        body = _body_html(s)
    return f'<div style="padding:16px 0;border-bottom:1px solid {c["rule"]}">{head}{body}{_sources_html(s)}</div>'


def debates_html(debates):
    c = COLOURS
    if not debates:
        return ""
    out = f'<h1 style="font-size:16px;letter-spacing:.06em;text-transform:uppercase;margin:28px 0 4px;color:{c["ink"]}">Debates and contested claims</h1>'
    out += f'<p style="margin:0 0 8px;font-size:13px;color:{c["muted"]}">Each side\'s position as reported, without a verdict.</p>'
    for d in debates:
        out += f'<div style="padding:12px 0;border-bottom:1px solid {c["rule"]}"><h2 style="font-size:16px;margin:0 0 6px">{escape(d["question"])}</h2>'
        out += f'<p style="margin:0 0 6px;font-size:12px;color:{c["muted"]}">From: {escape(d["headline"])}</p>'
        out += '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px">'
        for side in d["sides"]:
            evidence = f'<br><span style="color:{c["muted"]}">Evidence cited: {escape(side["evidence"])}</span>' if side.get("evidence") else ""
            out += (
                f'<tr><td style="vertical-align:top;padding:6px 10px 6px 0;width:28%;font-weight:bold">{escape(side["side"])}</td>'
                f'<td style="vertical-align:top;padding:6px 0">{escape(side["position"])}{evidence}</td></tr>'
            )
        out += "</table></div>"
    return out


def collect_debates(story_dicts):
    return [
        {"headline": s["headline"], "question": s["debate"]["question"], "sides": s["debate"]["sides"]}
        for s in story_dicts if s.get("debate") and s["debate"].get("sides")
    ]


def notice_html(notice):
    if not notice:
        return ""
    c = COLOURS
    return (f'<p style="margin:12px 0 0;padding:8px 10px;background:{c["update_bg"]};border-left:3px solid {c["update"]};'
            f'font-size:13px">{escape(notice)}</p>')


def email_html(day, stories, debates, web_url, settings_url, notice=""):
    c = COLOURS
    links = []
    if web_url:
        links.append(f'<a href="{escape(web_url)}" style="color:{c["accent"]}">View and filter online</a>')
    if settings_url:
        links.append(f'<a href="{escape(settings_url)}" style="color:{c["accent"]}">Change settings</a>')
    link_row = f'<p style="margin:4px 0 0;font-size:13px">{" &nbsp;|&nbsp; ".join(links)}</p>' if links else ""
    updates = sum(1 for s in stories if s["is_update"])
    counts = f"{len(stories)} " + ("story" if len(stories) == 1 else "stories") + (f", {updates} of them updates" if updates else "")
    body = "".join(story_html(s) for s in stories) or '<p style="padding:16px 0">No new stories matched your settings since the last digest.</p>'
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f2f4f6">
<div style="max-width:680px;margin:0 auto;padding:20px 16px;background:{c['paper']};font-family:Georgia,'Times New Roman',serif;font-size:15px;line-height:1.5;color:{c['ink']}">
<div style="font-family:Arial,Helvetica,sans-serif">
<h1 style="font-size:20px;letter-spacing:.08em;text-transform:uppercase;margin:0">News Digest</h1>
<p style="margin:2px 0 0;color:{c['muted']};font-size:13px">{escape(long_date(day))}, {counts}</p>
{link_row}
{notice_html(notice)}
</div>
{body}
{debates_html(debates)}
<p style="margin:24px 0 0;font-size:11px;color:{c['muted']};font-family:Arial,Helvetica,sans-serif">Facts are extracted automatically by AI from the linked articles. Check the sources before relying on any figure.</p>
</div></body></html>"""


def email_text(day, stories, debates, web_url, notice=""):
    lines = [f"NEWS DIGEST, {long_date(day).upper()}", ""]
    if notice:
        lines += [f"NOTE: {notice}", ""]
    if web_url:
        lines += [f"View and filter online: {web_url}", ""]
    for n, s in enumerate(stories, start=1):
        tag = "UPDATE. " if s["is_update"] else ""
        lines.append(f"{n}. {tag}{s['headline']} [{REGION_LABELS.get(s['region'], s['region'])}, {s['category_label']}]")
        if s["is_update"]:
            lines.append(f"   What is new: {s['update_summary']}")
        if s["facts"]:
            lines.append(f"   {s['facts']}")
        for num in s["key_numbers"]:
            lines.append(f"   Key number: {num}")
        if s["why_it_matters"]:
            lines.append(f"   Why it matters: {s['why_it_matters']}")
        if s["is_update"]:
            prev = s["previous"]
            lines.append(f"   Original story, sent on {_nice_date(prev['date'])}: {prev['headline']}. {prev['facts']}")
        lines.append("   Sources: " + ", ".join(f"{x['name']} {x['url']}" for x in s["sources"]))
        lines.append("")
    if debates:
        lines += ["DEBATES AND CONTESTED CLAIMS", ""]
        for d in debates:
            lines.append(d["question"])
            for side in d["sides"]:
                lines.append(f"   {side['side']}: {side['position']} Evidence cited: {side.get('evidence', '')}")
            lines.append("")
    return "\n".join(lines)
