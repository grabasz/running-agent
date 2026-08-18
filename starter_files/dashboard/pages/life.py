"""Zakladka Rozkminy — cele tygodnia + zadania + notatki.

**ODSTEPSTWO od SRP:** ten plik ma >200 linii bo `page_life` to naturalnie
zlozona zakladka z trzema seciami (goals + tasks + notes) i formami dodawania.
Podzial na goals.py / tasks.py / notes.py byłby przedwczesny — sekcje sa
scisle powiazane (LIFE_CATEGORIES / LIFE_ICONS wspolne, `_render_task_row`
prywatny helper). Po dojrzalej obserwacji ewolucji rozdzielimy.
"""
from __future__ import annotations
from datetime import datetime
import streamlit as st

import api  # type: ignore

from dashboard.constants import LIFE_CATEGORIES, LIFE_ICONS, NOTE_CATEGORIES, NOTE_ICONS
from dashboard.queries import q_goals_week, q_tasks_all, q_notes_recent
from dashboard.callbacks import (
    _invalidate_life_cache, _push_life_to_turso,
    _cb_goal_upsert, _cb_goal_toggle,
    _cb_task_toggle, _cb_task_delete, _cb_note_delete,
)
from dashboard.helpers import monday_iso
from dashboard.utils import get_user_id


def _render_task_row(t: dict, children_by_parent: dict, indent: int = 0):
    """Prywatny helper renderujacy jeden wiersz taska + rekurencyjnie children."""
    prio_icon = {"high": "🔥", "med": "▲", "low": "▽"}.get(t.get("priority") or "", "")
    due = f" · 📅 {t['due_date']}" if t.get("due_date") else ""
    done = t["status"] == "done"
    prefix = "&nbsp;&nbsp;&nbsp;&nbsp;" * indent + ("↳ " if indent else "")

    cols = st.columns([1, 9, 1])
    with cols[0]:
        st.checkbox(
            "done", value=done,
            key=f"task_chk_{t['id']}",
            label_visibility="collapsed",
            on_change=_cb_task_toggle,
            args=(t["id"], t["status"]),
        )
    with cols[1]:
        title_html = f"{prefix}<span style='opacity:{0.55 if done else 1}'>"
        if done:
            title_html += f"<s>{t['title']}</s>"
        else:
            title_html += f"<b>{t['title']}</b>"
        title_html += f" {prio_icon}{due}</span>"
        st.markdown(title_html, unsafe_allow_html=True)
        if t.get("description") or t.get("success_criteria"):
            with st.expander("szczegóły", expanded=False):
                if t.get("description"):
                    st.write(f"**Opis:** {t['description']}")
                if t.get("success_criteria"):
                    st.write(f"**Kryterium (SMART):** {t['success_criteria']}")
    with cols[2]:
        if st.button("🗑", key=f"task_del_{t['id']}",
                     help="Usuń task (kaskada — usuwa też podzadania)"):
            _cb_task_delete(t["id"])
            st.rerun()

    for child in children_by_parent.get(t["id"], []):
        _render_task_row(child, children_by_parent, indent + 1)


def page_life():
    st.title("🧠 Rozkminy")
    st.caption("Życie i trening w jednym miejscu — cele tygodnia, zadania, notatki.")

    user_id = get_user_id()
    week_start = monday_iso()

    # ------- Cele tygodnia -------
    st.header(f"🎯 Cele tygodnia — od pon. {week_start}")
    goals_map = q_goals_week(user_id=user_id, week_start=week_start)

    filled_cats = [c for c in LIFE_CATEGORIES if goals_map.get(c)]
    empty_cats = [c for c in LIFE_CATEGORIES if not goals_map.get(c)]

    if filled_cats:
        goal_cols = st.columns(min(3, len(filled_cats)))
        for i, cat in enumerate(filled_cats):
            with goal_cols[i % 3]:
                existing = goals_map[cat]
                status = existing["status"]
                icon = LIFE_ICONS[cat]
                input_key = f"goal_input_{week_start}_{cat}"

                st.markdown(f"**{icon} {cat.capitalize()}**")
                c_chk, c_input = st.columns([1, 8], vertical_alignment="center")
                with c_chk:
                    st.checkbox(
                        "zrobione", value=(status == "done"),
                        key=f"goal_chk_{week_start}_{cat}",
                        label_visibility="collapsed",
                        help="Zaznacz gdy zrobione",
                        on_change=_cb_goal_toggle,
                        args=(existing["id"], status),
                    )
                with c_input:
                    st.text_input(
                        "cel", value=existing["goal"],
                        key=input_key,
                        placeholder="Cel na ten tydzień…",
                        label_visibility="collapsed",
                        on_change=_cb_goal_upsert,
                        args=(week_start, cat, input_key),
                    )
    else:
        st.caption("_Brak celów na ten tydzień — dodaj pierwszy poniżej._")

    if empty_cats:
        with st.expander(f"➕ Dodaj cel dla kategorii ({len(empty_cats)} dostępnych)", expanded=not filled_cats):
            with st.form(f"add_goal_form_{week_start}", clear_on_submit=True):
                add_cat = st.selectbox(
                    "Kategoria", empty_cats,
                    format_func=lambda c: f"{LIFE_ICONS[c]} {c.capitalize()}",
                    key=f"new_goal_cat_{week_start}",
                )
                add_text = st.text_input(
                    "Cel", key=f"new_goal_text_{week_start}",
                    placeholder="Cel na ten tydzień…",
                )
                if st.form_submit_button("Zapisz cel"):
                    if not add_text.strip():
                        st.error("Wpisz treść celu.")
                    else:
                        with api.connect() as conn:
                            api.goals.upsert(conn, week_start=week_start, category=add_cat,
                                             goal=add_text.strip(), status=None)
                        _invalidate_life_cache()
                        _push_life_to_turso()
                        st.rerun()

    st.divider()

    # ------- Zadania -------
    st.header("📋 Zadania")
    all_tasks = q_tasks_all(user_id=user_id)

    show_done = st.toggle("Pokaż wykonane", value=False, key="tasks_show_done")

    by_cat: dict[str, list[dict]] = {c: [] for c in LIFE_CATEGORIES}
    for t in all_tasks:
        if t["category"] in by_cat:
            by_cat[t["category"]].append(t)

    task_tabs = st.tabs([f"{LIFE_ICONS[c]} {c.capitalize()}" for c in LIFE_CATEGORIES])

    for cat, tab in zip(LIFE_CATEGORIES, task_tabs):
        with tab:
            cat_tasks = by_cat[cat]
            visible = cat_tasks if show_done else [t for t in cat_tasks if t["status"] == "open"]
            roots = [t for t in visible if not t["parent_id"]]
            children_by_parent: dict[int, list[dict]] = {}
            for t in visible:
                if t["parent_id"]:
                    children_by_parent.setdefault(t["parent_id"], []).append(t)

            if roots:
                for t in roots:
                    _render_task_row(t, children_by_parent)
            else:
                st.info("Brak zadań w tej kategorii.")

            with st.expander(f"➕ Dodaj task ({cat})", expanded=False):
                with st.form(f"add_task_form_{cat}", clear_on_submit=True):
                    title = st.text_input("Tytuł*", key=f"nt_title_{cat}",
                                          placeholder="Krótko i konkretnie (SMART: Specific)")
                    parent_opts = {0: "— brak (root task / projekt)"}
                    for t in cat_tasks:
                        if not t["parent_id"] and t["status"] == "open":
                            parent_opts[t["id"]] = f"↳ {t['title'][:50]}"
                    parent_id = st.selectbox(
                        "Podzadanie czego?", options=list(parent_opts.keys()),
                        format_func=lambda x: parent_opts[x], key=f"nt_parent_{cat}"
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        due = st.date_input("Termin (opcjonalny)",
                                            value=None, key=f"nt_due_{cat}")
                    with c2:
                        prio = st.selectbox("Priorytet",
                                            ["", "low", "med", "high"],
                                            key=f"nt_prio_{cat}")
                    desc = st.text_area("Opis (opcjonalny)", key=f"nt_desc_{cat}")
                    crit = st.text_input(
                        "Kryterium sukcesu (SMART: Measurable)",
                        key=f"nt_crit_{cat}",
                        placeholder="Skąd wiesz że jest zrobione? np. „Umowa podpisana”"
                    )
                    if st.form_submit_button("Zapisz"):
                        if not title.strip():
                            st.error("Tytuł jest wymagany")
                        else:
                            with api.connect() as conn:
                                api.tasks.add(
                                    conn,
                                    parent_id=parent_id if parent_id else None,
                                    category=cat,
                                    title=title.strip(),
                                    description=(desc.strip() or None),
                                    success_criteria=(crit.strip() or None),
                                    due_date=(due.isoformat() if due else None),
                                    priority=(prio or None),
                                    status=None,
                                )
                            _invalidate_life_cache()
                            _push_life_to_turso()
                            st.success("Task dodany")
                            st.rerun()

    st.divider()

    # ------- Notatki -------
    st.header("💡 Notatki")

    f1, f2 = st.columns([2, 1])
    with f1:
        cat_filter = st.selectbox(
            "Kategoria", ["wszystkie"] + NOTE_CATEGORIES,
            format_func=lambda c: c if c == "wszystkie" else f"{NOTE_ICONS[c]} {c}",
            key="notes_cat_filter",
        )
    with f2:
        limit = st.number_input("Pokaż ostatnie N", min_value=5, max_value=100,
                                 value=20, step=5, key="notes_limit")

    notes = q_notes_recent(user_id=user_id, limit=int(limit))
    if cat_filter != "wszystkie":
        notes = [n for n in notes if n["category"] == cat_filter]

    if notes:
        for n in notes:
            icon = NOTE_ICONS.get(n["category"], "•")
            row = st.columns([1, 10, 1])
            with row[0]:
                st.write(f"{icon} `{n['date']}`")
            with row[1]:
                st.write(n["content"])
                if n.get("source") and n["source"] != "chat":
                    st.caption(f"źródło: {n['source']}")
            with row[2]:
                if st.button("🗑", key=f"note_del_{n['id']}",
                             help="Usuń notatkę"):
                    _cb_note_delete(n["id"])
                    st.rerun()
    else:
        st.info("Brak notatek dla wybranego filtra. Dodaj poniżej.")

    with st.expander("➕ Dodaj notatkę", expanded=False):
        with st.form("add_note_form", clear_on_submit=True):
            cat = st.selectbox("Kategoria", NOTE_CATEGORIES,
                               format_func=lambda c: f"{NOTE_ICONS[c]} {c}",
                               key="nn_cat")
            content = st.text_area("Treść*", key="nn_content",
                                    placeholder="Insight, decyzja, przypomnienie, pomysł…")
            if st.form_submit_button("Zapisz"):
                if not content.strip():
                    st.error("Treść jest wymagana")
                else:
                    with api.connect() as conn:
                        api.notes.add(
                            conn,
                            date=datetime.now().date().isoformat(),
                            category=cat,
                            content=content.strip(),
                            related_task_id=None, related_run_id=None,
                            related_session_id=None,
                            source="manual",
                        )
                    _invalidate_life_cache()
                    _push_life_to_turso()
                    st.success("Notatka dodana")
                    st.rerun()
