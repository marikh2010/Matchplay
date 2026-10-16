
import copy
import datetime
import threading
import time

import gspread
import streamlit as st
from gspread.utils import rowcol_to_a1

CACHE_TTL_SECONDS = 300  # how often to pick up manual edits made in the Sheet

# ---------------------------------------------------------------------------
# Schema: tab name -> columns. "id" must stay the first column of every tab.
# Extra columns found in the Sheet (or new keys in a payload) are kept/added
# automatically, so this list is a starting point, not a hard limit.
# ---------------------------------------------------------------------------
SCHEMA = {
    "sports": ["id", "name"],
    "entry_types": ["id", "sport_id", "name", "sort_order"],
    "athletes": ["id", "name", "sport_id", "gender"],
    "stages": ["id", "entry_type_id", "name", "sort_order"],
    "squash_matches": ["id", "athlete_id", "entry_type_id", "match_date", "category", "stage",
                       "match_no", "opponent_name", "max_sets"],
    "squash_match_sets": ["id", "match_id", "set_no", "player_score", "opponent_score", "rpe",
                          "duration_seconds", "avg_hr", "peak_hr", "end_hr", "hr_recovery",
                          "cardio_load", "resting_lactate", "lactate", "resting_glucose", "glucose",
                          "avg_hr_pct"],
    "rsa_tests": ["id", "athlete_id", "entry_type_id", "test_date", "stage"],
    "rsa_sets": ["id", "test_id", "set_no", "lap_1", "lap_2"],
    "yoyo_tests": ["id", "athlete_id", "entry_type_id", "test_date", "stage", "age", "level", "shuttle",
                   "peak_hr", "lactate_pretest", "lactate_peak", "lactate_0min", "lactate_2min",
                   "lactate_5min", "lactate_7min", "lactate_9min"],
    "longjump_tests": ["id", "athlete_id", "entry_type_id", "test_date"],
    "longjump_attempts": ["id", "test_id", "jump_no", "first_10m", "split_10_15", "split_15_20",
                          "total_time", "validity", "jump_length"],
    "judo_tests": ["id", "athlete_id", "entry_type_id", "test_date", "stage", "body_mass",
                   "ramp_last_watt", "ramp_duration_s", "ramp_increment", "ramp_peak_hr"],
    "judo_trials": ["id", "test_id", "trial_no", "grip_right", "grip_left", "max_rfd_right",
                    "max_rfd_left", "avg_rfd_right", "avg_rfd_left", "imtp_peak"],
}

# Unique rules (what Postgres "duplicate key" used to enforce).
UNIQUE = {
    "sports": [("name",)],
    "entry_types": [("sport_id", "name")],
    "athletes": [("sport_id", "name")],
    "stages": [("entry_type_id", "name")],
}

# Cascade deletes: parent tab -> [(child tab, foreign-key column)]
_TEST_TABS = ["squash_matches", "rsa_tests", "yoyo_tests", "longjump_tests", "judo_tests"]
CHILDREN = {
    "sports": [("entry_types", "sport_id"), ("athletes", "sport_id")],
    "entry_types": [("stages", "entry_type_id")] + [(t, "entry_type_id") for t in _TEST_TABS],
    "athletes": [(t, "athlete_id") for t in _TEST_TABS],
    "squash_matches": [("squash_match_sets", "match_id")],
    "rsa_tests": [("rsa_sets", "test_id")],
    "longjump_tests": [("longjump_attempts", "test_id")],
    "judo_tests": [("judo_trials", "test_id")],
}

_INT_COLS = {"id", "sort_order", "match_no", "max_sets", "set_no", "jump_no", "trial_no",
             "player_score", "opponent_score", "rpe", "level", "shuttle", "age", "peak_hr", "ramp_peak_hr"}
_ATHLETE_JOIN = ("id", "name", "sport_id", "gender")


def _is_int_col(col: str) -> bool:
    return col in _INT_COLS or col.endswith("_id")


def _clean(col, v):
    """Sheet cell -> Python value (matches what Supabase used to return)."""
    if v is None or v == "":
        return None
    if col.endswith("_date"):
        if isinstance(v, (int, float)):  # a date typed by hand in the Sheet -> serial number
            return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v))).isoformat()
        return str(v)
    if _is_int_col(col):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return v
    return v


def _to_cell(v):
    """Python value -> Sheet cell."""
    if v is None:
        return ""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return v


# ---------------------------------------------------------------------------
# Connection + in-memory store
# ---------------------------------------------------------------------------

@st.cache_resource
def _spreadsheet():
    info = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(info, http_client=gspread.BackOffHTTPClient)
    key = st.secrets["GOOGLE_SHEET_ID"]
    return gc.open_by_url(key) if key.startswith("http") else gc.open_by_key(key)


class _Store:
    def __init__(self, sh):
        self.sh = sh
        self.lock = threading.RLock()
        self.tables: dict[str, list[dict]] = {}
        self.headers: dict[str, list[str]] = {}
        self.sheet_ids: dict[str, int] = {}
        self.loaded_at = 0.0
        self._ensure_tabs()

    # ----- setup -----
    def _ensure_tabs(self):
        """Create any missing tabs with their header row (first run only)."""
        existing = {ws.title: ws for ws in self.sh.worksheets()}
        for tab, cols in SCHEMA.items():
            if tab not in existing:
                ws = self.sh.add_worksheet(title=tab, rows=1000, cols=max(26, len(cols)))
                ws.update([cols], "A1", value_input_option="RAW")
                ws.freeze(rows=1)
                existing[tab] = ws
        self.sheet_ids = {t: existing[t].id for t in SCHEMA}

    # ----- reading -----
    def load(self):
        with self.lock:
            res = self.sh.values_batch_get(
                [f"'{t}'" for t in SCHEMA],
                params={"valueRenderOption": "UNFORMATTED_VALUE", "dateTimeRenderOption": "SERIAL_NUMBER"},
            )
            header_fixes = []
            for tab, vr in zip(SCHEMA, res.get("valueRanges", [])):
                values = vr.get("values", [])
                header = [str(h).strip() for h in values[0]] if values else []
                missing = [c for c in SCHEMA[tab] if c not in header]
                if missing:
                    header = header + missing
                    header_fixes.append({"range": f"'{tab}'!A1", "values": [header]})
                if header[0] != "id":
                    raise RuntimeError(f"Tab '{tab}': the first column must be 'id'. Please don't move columns in the Sheet.")
                rows = []
                for raw in values[1:]:
                    raw = list(raw) + [""] * (len(header) - len(raw))
                    rec = {c: _clean(c, v) for c, v in zip(header, raw) if c}
                    if rec.get("id") is None:
                        continue  # skip blank rows
                    rows.append(rec)
                self.headers[tab] = header
                self.tables[tab] = rows
            if header_fixes:
                self.sh.values_batch_update({"valueInputOption": "RAW", "data": header_fixes})
            self.loaded_at = time.time()

    def table(self, tab) -> list[dict]:
        with self.lock:
            if time.time() - self.loaded_at > CACHE_TTL_SECONDS or tab not in self.tables:
                self.load()
            return self.tables[tab]

    # ----- write helpers -----
    def _sheet_rows(self, tabs):
        """Read just the id column of each tab: {tab: {id: sheet_row_number}}."""
        res = self.sh.values_batch_get(
            [f"'{t}'!A:A" for t in tabs], params={"valueRenderOption": "UNFORMATTED_VALUE"}
        )
        out = {}
        for tab, vr in zip(tabs, res.get("valueRanges", [])):
            col = vr.get("values", [])
            mapping = {}
            for i, cell in enumerate(col[1:], start=2):
                v = _clean("id", cell[0] if cell else None)
                if v is not None:
                    mapping[v] = i
            out[tab] = mapping
        return out

    def _sync_check(self, sheet_rows):
        """If the Sheet was changed by hand, reload memory so we act on real data."""
        for tab, mapping in sheet_rows.items():
            if set(mapping) != {r["id"] for r in self.tables.get(tab, [])}:
                self.load()
                return

    def _ensure_columns(self, tab, keys):
        header = self.headers[tab]
        new = [k for k in keys if k not in header]
        if new:
            header.extend(new)
            self.sh.values_batch_update({"valueInputOption": "RAW",
                                         "data": [{"range": f"'{tab}'!A1", "values": [header]}]})

    def _check_unique(self, tab, record, ignore_id=None):
        for cols in UNIQUE.get(tab, []):
            key = tuple(_norm(record.get(c)) for c in cols)
            for r in self.tables[tab]:
                if r["id"] != ignore_id and tuple(_norm(r.get(c)) for c in cols) == key:
                    raise ValueError("duplicate key")

    # ----- writes -----
    def insert(self, tab, records: list[dict]) -> list[int]:
        if not records:
            return []
        with self.lock:
            self.table(tab)
            sheet_rows = self._sheet_rows([tab])
            self._sync_check(sheet_rows)
            self._ensure_columns(tab, {k for r in records for k in r})
            header = self.headers[tab]
            next_id = max(list(sheet_rows[tab]) + [r["id"] for r in self.tables[tab]] + [0]) + 1
            new_recs = []
            for rec in records:
                rec = {c: _clean(c, _to_cell(rec.get(c))) for c in header} | {"id": next_id}
                self._check_unique(tab, rec)
                for other in new_recs:
                    if any(all(_norm(other.get(c)) == _norm(rec.get(c)) for c in cols) for cols in UNIQUE.get(tab, [])):
                        raise ValueError("duplicate key")
                new_recs.append(rec)
                next_id += 1
            self.sh.values_append(
                f"'{tab}'!A1",
                params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                body={"values": [[_to_cell(r.get(c)) for c in header] for r in new_recs]},
            )
            self.tables[tab].extend(new_recs)
            return [r["id"] for r in new_recs]

    def update(self, tab, row_id: int, changes: dict):
        """Writes only the changed cells, so manual edits in other columns survive."""
        with self.lock:
            self.table(tab)
            sheet_rows = self._sheet_rows([tab])
            self._sync_check(sheet_rows)
            row = sheet_rows[tab].get(int(row_id))
            if row is None:
                return
            rec = next(r for r in self.tables[tab] if r["id"] == int(row_id))
            merged = {**rec, **{k: _clean(k, _to_cell(v)) for k, v in changes.items()}}
            self._check_unique(tab, merged, ignore_id=int(row_id))
            self._ensure_columns(tab, changes.keys())
            header = self.headers[tab]
            data = [{"range": f"'{tab}'!{rowcol_to_a1(row, header.index(k) + 1)}", "values": [[_to_cell(v)]]}
                    for k, v in changes.items()]
            self.sh.values_batch_update({"valueInputOption": "RAW", "data": data})
            rec.update({k: merged[k] for k in changes})

    def delete(self, tab, row_id: int):
        """Deletes the row and everything that belongs to it, in one API call."""
        with self.lock:
            self.table(tab)
            to_delete = self._collect(tab, {int(row_id)})
            sheet_rows = self._sheet_rows(list(to_delete))
            before = {t: {r["id"] for r in self.tables[t]} for t in to_delete}
            self._sync_check(sheet_rows)
            if before != {t: {r["id"] for r in self.tables[t]} for t in to_delete}:
                to_delete = self._collect(tab, {int(row_id)})  # memory was reloaded - recompute
                sheet_rows = self._sheet_rows(list(to_delete))
            requests = []
            for t, ids in to_delete.items():
                rows = sorted((sheet_rows[t][i] for i in ids if i in sheet_rows[t]), reverse=True)
                for r in rows:  # bottom-up so row numbers don't shift under us
                    requests.append({"deleteDimension": {"range": {
                        "sheetId": self.sheet_ids[t], "dimension": "ROWS", "startIndex": r - 1, "endIndex": r}}})
            if requests:
                self.sh.batch_update({"requests": requests})
            for t, ids in to_delete.items():
                self.tables[t] = [r for r in self.tables[t] if r["id"] not in ids]

    def _collect(self, tab, ids) -> dict[str, set]:
        out = {tab: set(ids)}
        for child, fk in CHILDREN.get(tab, []):
            child_ids = {r["id"] for r in self.table(child) if r.get(fk) in ids}
            if child_ids:
                for t, s in self._collect(child, child_ids).items():
                    out.setdefault(t, set()).update(s)
        return out


def _norm(v):
    return v.strip().lower() if isinstance(v, str) else v


@st.cache_resource
def _store() -> _Store:
    return _Store(_spreadsheet())


def refresh():
    """Force a re-read of the whole Sheet (e.g. after editing it by hand)."""
    _store().load()


def refresh_if_older_than(seconds: float) -> float:
    """Re-read the Sheet if the cached copy is older than `seconds`, so
    hand edits show up sooner than CACHE_TTL_SECONDS. Returns the time of
    the last load. The cache is shared, so many open pages still cause at
    most one read per `seconds`."""
    store = _store()
    with store.lock:
        if time.time() - store.loaded_at > seconds:
            store.load()
        return store.loaded_at


# ---------- small query helpers ----------

def _select(tab, where=None, order=None, desc=False):
    rows = [r for r in _store().table(tab) if not where or all(r.get(k) == v for k, v in where.items())]
    if order:
        present = [r for r in rows if r.get(order) is not None]
        missing = [r for r in rows if r.get(order) is None]
        present.sort(key=lambda r: (r[order], r["id"]), reverse=desc)
        rows = present + missing
    return copy.deepcopy(rows)


def _with_athlete(rows):
    """Equivalent of Supabase's `athletes!inner(id, name, sport_id, gender)`."""
    athletes = {a["id"]: a for a in _store().table("athletes")}
    out = []
    for r in rows:
        a = athletes.get(r.get("athlete_id"))
        if a is not None:
            r["athletes"] = {k: a.get(k) for k in _ATHLETE_JOIN}
            out.append(r)
    return out


def _children_by_parent(tab, fk, order):
    grouped = {}
    for r in _select(tab, order=order):
        grouped.setdefault(r.get(fk), []).append(r)
    return grouped


def _wrap_dup(fn, msg):
    try:
        return fn()
    except ValueError as e:
        if "duplicate key" in str(e):
            raise ValueError(msg) from e
        raise


# ---------- Sports ----------

def list_sports():
    return _select("sports", order="name")


def create_sport(name: str):
    return _wrap_dup(lambda: _store().insert("sports", [{"name": name}]), f"'{name}' already exists.")


# ---------- Entry types ----------

def list_entry_types(sport_id: int):
    return _select("entry_types", {"sport_id": sport_id}, order="sort_order")


def create_entry_type(sport_id: int, name: str, sort_order: int = 0):
    return _wrap_dup(
        lambda: _store().insert("entry_types", [{"sport_id": sport_id, "name": name, "sort_order": sort_order}]),
        f"'{name}' already exists for this sport.")


# ---------- Athletes ----------

def list_athletes(sport_id: int = None):
    return _select("athletes", {"sport_id": sport_id} if sport_id is not None else None, order="name")


def create_athlete(name: str, sport_id: int, gender: str = None):
    payload = {"name": name, "sport_id": sport_id}
    if gender:
        payload["gender"] = gender
    return _wrap_dup(lambda: _store().insert("athletes", [payload]), f"'{name}' is already added for this sport.")


def update_athlete(athlete_id: int, name: str, gender: str):
    return _wrap_dup(lambda: _store().update("athletes", athlete_id, {"name": name, "gender": gender}),
                     f"'{name}' is already used by another athlete in this sport.")


def delete_athlete(athlete_id: int):
    """Cascades to delete every match/test this athlete has across all entry types."""
    _store().delete("athletes", athlete_id)


# ---------- Stages ----------

def list_stages(entry_type_id: int):
    return _select("stages", {"entry_type_id": entry_type_id}, order="sort_order")


def create_stage(entry_type_id: int, name: str, sort_order: int = 0):
    return _wrap_dup(
        lambda: _store().insert("stages", [{"entry_type_id": entry_type_id, "name": name, "sort_order": sort_order}]),
        f"'{name}' already exists for this entry type.")


def delete_stage(stage_id: int):
    _store().delete("stages", stage_id)


# =====================================================================
# Squash - Match Play
# =====================================================================

def next_match_no(athlete_id: int, category: str = None) -> int:
    where = {"athlete_id": athlete_id}
    if category is not None:
        where["category"] = category
    nos = [r["match_no"] for r in _select("squash_matches", where) if r.get("match_no") is not None]
    return max(nos) + 1 if nos else 1


def find_possible_duplicate_match(athlete_id, match_date, match_no, category=None, opponent_name=None, stage=None):
    base = _select("squash_matches", {"athlete_id": athlete_id, "match_date": str(match_date)})
    pick = lambda r: {"id": r["id"], "match_no": r.get("match_no"), "match_date": r.get("match_date")}
    by_number = [r for r in base if r.get("match_no") == match_no]
    if by_number:
        return pick(by_number[0])
    if opponent_name:
        by_key = [r for r in base if r.get("opponent_name") == opponent_name
                  and (not category or r.get("category") == category)
                  and (not stage or r.get("stage") == stage)]
        if by_key:
            return pick(by_key[0])
    return None


def create_match(athlete_id, entry_type_id, match_date, category, stage, match_no, opponent_name, max_sets):
    payload = {
        "athlete_id": athlete_id, "entry_type_id": entry_type_id, "match_date": str(match_date),
        "category": category, "stage": stage, "match_no": match_no,
        "opponent_name": opponent_name.strip() if opponent_name else None, "max_sets": max_sets,
    }
    return _store().insert("squash_matches", [payload])[0]


def create_match_sets(match_id: int, sets: list[dict]):
    _store().insert("squash_match_sets", [{**s, "match_id": match_id} for s in sets])


def get_matches(athlete_id: int = None, category: str = None):
    where = {}
    if athlete_id is not None:
        where["athlete_id"] = athlete_id
    if category is not None:
        where["category"] = category
    return _with_athlete(_select("squash_matches", where, order="match_date", desc=True))


def get_match_sets(match_id: int):
    return _select("squash_match_sets", {"match_id": match_id}, order="set_no")


def get_matches_with_sets(athlete_id: int = None, category: str = None):
    matches = get_matches(athlete_id=athlete_id, category=category)
    sets = _children_by_parent("squash_match_sets", "match_id", "set_no")
    for m in matches:
        m["sets"] = sets.get(m["id"], [])
    return matches


def delete_match(match_id: int):
    _store().delete("squash_matches", match_id)


def update_match(match_id: int, category, stage, opponent_name, match_no):
    _store().update("squash_matches", match_id, {
        "category": category, "stage": stage, "opponent_name": opponent_name, "match_no": match_no,
    })


def update_match_set_scores(set_id: int, player_score, opponent_score):
    _store().update("squash_match_sets", set_id, {"player_score": player_score, "opponent_score": opponent_score})


def list_known_opponents():
    rows = _store().table("squash_matches")
    return sorted({str(r["opponent_name"]).strip() for r in rows if r.get("opponent_name")})


# =====================================================================
# Squash - RSA Test
# =====================================================================

def create_rsa_test(athlete_id, entry_type_id, test_date, stage):
    payload = {"athlete_id": athlete_id, "entry_type_id": entry_type_id, "test_date": str(test_date), "stage": stage}
    return _store().insert("rsa_tests", [payload])[0]


def create_rsa_sets(test_id: int, sets: list[dict]):
    _store().insert("rsa_sets", [{**s, "test_id": test_id} for s in sets])


def get_rsa_tests(athlete_id: int = None):
    where = {"athlete_id": athlete_id} if athlete_id is not None else None
    return _with_athlete(_select("rsa_tests", where, order="test_date", desc=True))


def get_rsa_sets(test_id: int):
    return _select("rsa_sets", {"test_id": test_id}, order="set_no")


def get_rsa_tests_with_sets(athlete_id: int = None):
    tests = get_rsa_tests(athlete_id=athlete_id)
    sets = _children_by_parent("rsa_sets", "test_id", "set_no")
    for t in tests:
        t["sets"] = sets.get(t["id"], [])
    return tests


def delete_rsa_test(test_id: int):
    _store().delete("rsa_tests", test_id)


def update_rsa_test(test_id: int, stage):
    _store().update("rsa_tests", test_id, {"stage": stage})


def update_rsa_set(set_id: int, lap_1, lap_2):
    _store().update("rsa_sets", set_id, {"lap_1": lap_1, "lap_2": lap_2})


# =====================================================================
# Squash - YIRC L1
# =====================================================================

def create_yoyo_test(payload: dict):
    return _store().insert("yoyo_tests", [payload])[0]


def get_yoyo_tests(athlete_id: int = None):
    where = {"athlete_id": athlete_id} if athlete_id is not None else None
    return _with_athlete(_select("yoyo_tests", where, order="test_date", desc=True))


def delete_yoyo_test(test_id: int):
    _store().delete("yoyo_tests", test_id)


def update_yoyo_test(test_id: int, payload: dict):
    _store().update("yoyo_tests", test_id, payload)


# =====================================================================
# Long Jump - 10-5-5
# =====================================================================

def create_longjump_test(athlete_id, entry_type_id, test_date):
    payload = {"athlete_id": athlete_id, "entry_type_id": entry_type_id, "test_date": str(test_date)}
    return _store().insert("longjump_tests", [payload])[0]


def create_longjump_attempts(test_id: int, attempts: list[dict]):
    _store().insert("longjump_attempts", [{**a, "test_id": test_id} for a in attempts])


def get_longjump_tests(athlete_id: int = None):
    where = {"athlete_id": athlete_id} if athlete_id is not None else None
    return _with_athlete(_select("longjump_tests", where, order="test_date", desc=True))


def get_longjump_attempts(test_id: int):
    return _select("longjump_attempts", {"test_id": test_id}, order="jump_no")


def get_longjump_tests_with_attempts(athlete_id: int = None):
    tests = get_longjump_tests(athlete_id=athlete_id)
    attempts = _children_by_parent("longjump_attempts", "test_id", "jump_no")
    for t in tests:
        t["attempts"] = attempts.get(t["id"], [])
    return tests


def delete_longjump_test(test_id: int):
    _store().delete("longjump_tests", test_id)


def update_longjump_attempt(attempt_id: int, first_10m, split_10_15, split_15_20, validity, jump_length):
    _store().update("longjump_attempts", attempt_id, {
        "first_10m": first_10m, "split_10_15": split_10_15, "split_15_20": split_15_20,
        "validity": validity, "jump_length": jump_length,
    })


# =====================================================================
# Judo - Fitness Test (handgrip, IMTP, 1-min ramp)
# =====================================================================

def create_judo_test(payload: dict):
    return _store().insert("judo_tests", [payload])[0]


def create_judo_trials(test_id: int, trials: list[dict]):
    _store().insert("judo_trials", [{**t, "test_id": test_id} for t in trials])


def get_judo_tests(athlete_id: int = None):
    where = {"athlete_id": athlete_id} if athlete_id is not None else None
    return _with_athlete(_select("judo_tests", where, order="test_date", desc=True))


def get_judo_trials(test_id: int):
    return _select("judo_trials", {"test_id": test_id}, order="trial_no")


def get_judo_tests_with_trials(athlete_id: int = None):
    tests = get_judo_tests(athlete_id=athlete_id)
    trials = _children_by_parent("judo_trials", "test_id", "trial_no")
    for t in tests:
        t["trials"] = trials.get(t["id"], [])
    return tests


def update_judo_test(test_id: int, payload: dict):
    _store().update("judo_tests", test_id, payload)


def update_judo_trial(trial_id: int, payload: dict):
    _store().update("judo_trials", trial_id, payload)


def delete_judo_test(test_id: int):
    _store().delete("judo_tests", test_id)
