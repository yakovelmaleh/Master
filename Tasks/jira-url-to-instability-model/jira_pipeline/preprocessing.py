import difflib
import re
from collections import defaultdict

import pandas as pd


SPRINT_DATE_PATTERN = re.compile(
    r"startDate=([^,\]]+)", re.IGNORECASE
)


def timestamp(value):
    if not value:
        return None
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed.tz_convert(None)


def adf_to_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(adf_to_text(item) for item in value).strip()
    if isinstance(value, dict):
        pieces = []
        if isinstance(value.get("text"), str):
            pieces.append(value["text"])
        if "content" in value:
            pieces.append(adf_to_text(value["content"]))
        return " ".join(piece for piece in pieces if piece).strip()
    return str(value)


def display_value(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(
            value.get("key")
            or value.get("name")
            or value.get("value")
            or value.get("displayName")
            or value.get("accountId")
            or ""
        )
    return str(value)


def sprint_start_dates(value):
    values = value if isinstance(value, list) else [value]
    dates = []
    for sprint in values:
        if isinstance(sprint, dict):
            parsed = timestamp(sprint.get("startDate"))
            if parsed is not None:
                dates.append(parsed)
        elif sprint:
            match = SPRINT_DATE_PATTERN.search(str(sprint))
            if match:
                parsed = timestamp(match.group(1))
                if parsed is not None:
                    dates.append(parsed)
    return dates


def flattened_changes(histories):
    changes = []
    for history in histories:
        created = timestamp(history.get("created"))
        for item in history.get("items", []):
            changes.append(
                {
                    "created": created,
                    "field": str(item.get("field") or ""),
                    "from_string": item.get("fromString"),
                    "to_string": item.get("toString"),
                }
            )
    return changes


def field_changes(changes, names):
    normalized = {name.casefold() for name in names}
    return [
        change
        for change in changes
        if change["field"].casefold() in normalized
        and change["created"] is not None
    ]


def first_sprint_entry(fields, sprint_field_id, changes, created):
    candidates = sprint_start_dates(fields.get(sprint_field_id))
    sprint_changes = field_changes(changes, {"Sprint"})
    candidates.extend(
        change["created"]
        for change in sprint_changes
        if change["to_string"]
    )
    valid = [date for date in candidates if date >= created]
    return min(valid) if valid else None


def word_change_count(original, current):
    original_words = str(original or "").split()
    current_words = str(current or "").split()
    return sum(
        1
        for item in difflib.ndiff(original_words, current_words)
        if item[0] != " "
    )


def state_at_sprint(current_value, changes, sprint_entry, created):
    eligible = [
        change
        for change in changes
        if change["created"] > sprint_entry
        and (change["created"] - created).total_seconds() > 3600
        and change["from_string"] is not None
    ]
    eligible.sort(key=lambda change: change["created"])
    original = eligible[0]["from_string"] if eligible else current_value
    return str(original or ""), len(eligible)


def numeric_state_at_sprint(current_value, changes, sprint_entry, created):
    original, count = state_at_sprint(
        current_value, changes, sprint_entry, created
    )
    try:
        return float(original), count
    except (TypeError, ValueError):
        return None, count


def preprocess_record(record, field_map):
    issue = record["issue"]
    fields = issue.get("fields") or {}
    created = timestamp(fields.get("created"))
    if created is None:
        return None, "invalid_created"
    changes = flattened_changes(record.get("changelog", []))
    sprint_field = field_map.get("Sprint")
    sprint_entry = (
        first_sprint_entry(fields, sprint_field, changes, created)
        if sprint_field
        else None
    )
    if sprint_entry is None:
        return None, "no_sprint_entry"

    comment_dates = [
        timestamp(comment.get("created"))
        for comment in record.get("comments", [])
    ]
    comments_before = [
        date
        for date in comment_dates
        if date is not None and date <= sprint_entry
    ]
    if not comments_before:
        return None, "no_comment_before_sprint"

    summary = adf_to_text(fields.get("summary"))
    description = adf_to_text(fields.get("description"))
    acceptance_field = field_map.get("Acceptance Criteria")
    acceptance = adf_to_text(fields.get(acceptance_field))
    story_points_field = field_map.get("Story Points")
    story_points = fields.get(story_points_field)

    summary_changes = field_changes(changes, {"summary"})
    description_changes = field_changes(changes, {"description"})
    acceptance_changes = field_changes(
        changes, {"Acceptance Criteria"}
    )
    story_point_changes = field_changes(changes, {"Story Points"})

    original_summary, summary_after = state_at_sprint(
        summary, summary_changes, sprint_entry, created
    )
    original_description, description_after = state_at_sprint(
        description, description_changes, sprint_entry, created
    )
    original_acceptance, acceptance_after = state_at_sprint(
        acceptance, acceptance_changes, sprint_entry, created
    )
    original_story_points, story_points_after = numeric_state_at_sprint(
        story_points, story_point_changes, sprint_entry, created
    )

    text_changes_after = (
        summary_after + description_after + acceptance_after
    )
    changed_words = (
        word_change_count(original_summary, summary)
        + word_change_count(original_description, description)
        + word_change_count(original_acceptance, acceptance)
    )
    text_changes_all = sum(
        1
        for change in (
            summary_changes + description_changes + acceptance_changes
        )
        if change["from_string"] is not None
        and (change["created"] - created).total_seconds() > 3600
    )
    story_point_changes_all = sum(
        1
        for change in story_point_changes
        if change["from_string"] is not None
        and (change["created"] - created).total_seconds() > 3600
    )
    creator = fields.get("creator") or fields.get("reporter") or {}
    row = {
        "issue_key": issue.get("key", ""),
        "issue_type": display_value(fields.get("issuetype")),
        "project_key": display_value(fields.get("project")),
        "created": created,
        "time_add_to_sprint": sprint_entry,
        "creator": display_value(creator),
        "priority": display_value(fields.get("priority")),
        "original_summary_sprint": original_summary,
        "original_description_sprint": original_description,
        "original_acceptance_criteria_sprint": original_acceptance,
        "original_story_points_sprint": original_story_points,
        "num_comments_before_sprint": len(comments_before),
        "num_changes_text_before_sprint": max(
            0, text_changes_all - text_changes_after
        ),
        "num_changes_story_point_before_sprint": max(
            0, story_point_changes_all - story_points_after
        ),
        "time_until_add_to_sprint": (
            sprint_entry - created
        ).total_seconds()
        / 60,
        "num_changes_summary_description_acceptance_sprint": (
            text_changes_after
        ),
        "num_different_words_all_text_sprint": changed_words,
    }
    for threshold_value in (5, 10, 15, 20):
        row[f"is_change_text_num_words_{threshold_value}"] = int(
            changed_words >= threshold_value and text_changes_after > 0
        )
    return row, "accepted"


def add_previous_creator_counts(frame):
    frame = frame.sort_values("created").copy()
    counts = defaultdict(int)
    previous = []
    for creator in frame["creator"].fillna("unknown").astype(str):
        previous.append(counts[creator])
        counts[creator] += 1
    frame["num_issues_cretor_prev"] = previous
    return frame.sort_values("time_add_to_sprint", kind="stable").reset_index(drop=True)
