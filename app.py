import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import streamlit as st

DATA_FILE = Path(__file__).parent / "items.json"
BACKUP_FILE = DATA_FILE.with_suffix(".json.bak")  # 깨진 파일 보관용

st.set_page_config(page_title="쇼핑리스트", page_icon="🛒", layout="centered")

# ---------- 스타일 (CSS는 이 한 곳에만) ----------
# 색상은 하드코딩하지 않고 Streamlit 테마(.streamlit/config.toml)와 상속색을 사용한다.
CSS = """
<style>
/* 좁은 가운데 정렬 레이아웃 */
[data-testid="stMainBlockContainer"] { max-width: 640px; padding-top: 2.5rem; }

/* 제목 */
h1 { font-size: 1.9rem !important; padding-bottom: .25rem; }

/* 항목 행: 모바일에서도 세로로 쌓이지 않고 한 줄 유지 */
[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .25rem !important; }
[data-testid="stColumn"] { min-width: 0 !important; }
/* 첫 칸(이름)은 남는 폭 전부, 나머지(버튼)는 터치하기 쉬운 고정 폭 */
[data-testid="stColumn"]:first-child { flex: 1 1 0 !important; }
[data-testid="stColumn"]:not(:first-child) { flex: 0 0 2.6rem !important; width: 2.6rem !important; }

/* 수정/삭제 버튼: 작고 덜 눈에 띄게 (배경·테두리 없음). 편집 폼의 제출 버튼 포함 */
[data-testid="stColumn"] .stButton button,
[data-testid="stColumn"] [data-testid="stFormSubmitButton"] button {
  min-height: 2.5rem; min-width: 2.5rem; padding: 0;
  border: none; background: transparent; opacity: .55; box-shadow: none;
}
[data-testid="stColumn"] .stButton button:hover,
[data-testid="stColumn"] [data-testid="stFormSubmitButton"] button:hover { opacity: 1; background: rgba(128,128,128,.15); }

/* 긴 이름이 넘치지 않게 줄바꿈 */
[data-testid="stCheckbox"] label p { word-break: break-word; font-size: 1.05rem; }

/* 빈 상태 */
.empty-state { text-align: center; padding: 2.5rem 1rem; opacity: .75; word-break: keep-all; }
.empty-state .icon { font-size: 3rem; line-height: 1.2; }
.empty-state .title { font-size: 1.1rem; font-weight: 600; margin-top: .5rem; }
.empty-state .desc { font-size: .95rem; margin-top: .25rem; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def escape_md(text):
    """사용자 입력이 마크다운/색상 문법으로 해석되지 않도록 이스케이프."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!~<>|$:&])", r"\\\1", text)


# ---------- 저장/불러오기 ----------
def _backup_broken_file():
    """깨진 items.json 은 덮어쓰이기 전에 .bak 으로 보관한다."""
    try:
        shutil.copy2(DATA_FILE, BACKUP_FILE)
    except OSError:
        pass


def read_file():
    """items.json 을 읽어 리스트로 반환. 파일이 없거나 읽을 수 없으면 None.

    내용이 깨진 경우(JSON 오류/리스트가 아님)에는 .bak 으로 보관하고 None 을 반환한다.
    """
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        _backup_broken_file()
        return None
    except OSError:
        return None
    if not isinstance(data, list):
        _backup_broken_file()
        return None
    return [
        {"id": str(d["id"]), "name": str(d["name"]), "done": bool(d.get("done", False))}
        for d in data
        if isinstance(d, dict) and "id" in d and "name" in d
    ]


def write_file(items):
    """임시 파일에 쓴 뒤 교체(원자적 쓰기). 쓰기가 불가능한 환경에서는 세션에서만 유지."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=DATA_FILE.parent, prefix="items.", suffix=".tmp", delete=False
        ) as tmp:
            tmp_path = tmp.name
            json.dump(items, tmp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except OSError:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def mutate(change):
    """파일의 최신 내용을 먼저 읽고 그 위에 변경을 적용해 저장한다.

    세션이 들고 있는 목록은 오래됐을 수 있으므로(다른 탭에서 수정), 통째로 덮어쓰지 않는다.
    파일을 읽을 수 없으면 세션의 목록을 기준으로 한다.
    """
    items = read_file()
    if items is None:
        items = st.session_state.shopping_items
    change(items)
    st.session_state.shopping_items = items
    write_file(items)


# ---------- 상태 초기화 ----------
def init_state():
    if "shopping_items" not in st.session_state:
        # 시작할 때 파일이 없거나 깨졌으면 빈 목록 (깨진 파일은 .bak 으로 보관됨)
        st.session_state.shopping_items = read_file() or []  # {"id", "name", "done"}
    if "editing" not in st.session_state:
        st.session_state.editing = None  # 편집 중인 아이템 id


# ---------- 동작 (콜백) ----------
# 모든 변경은 mutate() 를 거쳐 파일의 최신 목록 위에 적용한다.
def add_item():
    name = st.session_state.new_item.strip()
    if name:
        mutate(lambda items: items.append({"id": uuid.uuid4().hex, "name": name, "done": False}))
    st.session_state.new_item = ""


def toggle_item(item_id):
    done = st.session_state[f"chk_{item_id}"]

    def change(items):
        for it in items:
            if it["id"] == item_id:
                it["done"] = done

    mutate(change)


def delete_item(item_id):
    mutate(lambda items: items.__setitem__(slice(None), [i for i in items if i["id"] != item_id]))
    if st.session_state.editing == item_id:
        st.session_state.editing = None


def start_edit(item_id):
    st.session_state.editing = item_id


def save_edit(item_id):
    if st.session_state.editing != item_id:
        return
    name = st.session_state[f"edit_{item_id}"].strip()
    if not name:
        return  # 빈 값으로는 저장 불가, 편집 모드 유지

    def change(items):
        for it in items:
            if it["id"] == item_id:
                it["name"] = name

    mutate(change)
    st.session_state.editing = None


def cancel_edit():
    st.session_state.editing = None


def clear_checked():
    mutate(lambda items: items.__setitem__(slice(None), [i for i in items if not i["done"]]))


# ---------- 화면 ----------
def render_header(items):
    st.title("🛒 쇼핑리스트")
    if items:
        done = sum(i["done"] for i in items)
        st.caption(f"완료 **{done}** / 전체 {len(items)}")
        st.progress(done / len(items))
    st.text_input(
        "아이템 추가",
        key="new_item",
        placeholder="➕ 예: 우유, 계란, 사과 (Enter로 추가)",
        on_change=add_item,
        label_visibility="collapsed",
    )


def render_empty():
    st.markdown(
        '<div class="empty-state">'
        '<div class="icon">🧺</div>'
        '<div class="title">장바구니가 비어 있어요</div>'
        '<div class="desc">위 입력창에 사야 할 물건을 적고 Enter를 눌러 보세요</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_item(it):
    iid = it["id"]
    with st.container(border=True):
        render_item_row(it, iid)


def render_item_row(it, iid):
    if st.session_state.editing == iid:
        # 폼 안의 입력창은 포커스가 빠져도 값이 확정되지 않는다 → ✖️ 취소가 저장으로 이어지지 않음.
        # Enter 는 첫 번째 제출 버튼(💾)을 누른 것과 같다.
        with st.form(key=f"form_{iid}", border=False):
            c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="center")
            c1.text_input(
                "수정",
                value=it["name"],
                key=f"edit_{iid}",
                label_visibility="collapsed",
            )
            c2.form_submit_button("💾", on_click=save_edit, args=(iid,), help="저장")
            c3.form_submit_button("✖️", on_click=cancel_edit, help="취소")
    else:
        c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="center")
        label = escape_md(it["name"])
        c1.checkbox(
            f":gray[~~{label}~~]" if it["done"] else label,
            value=it["done"],
            key=f"chk_{iid}",
            on_change=toggle_item,
            args=(iid,),
        )
        c2.button("✏️", key=f"edit_btn_{iid}", on_click=start_edit, args=(iid,), help="수정")
        c3.button("🗑️", key=f"del_{iid}", on_click=delete_item, args=(iid,), help="삭제")


def render_list(items):
    if not items:
        render_empty()
        return
    for it in items:
        render_item(it)
    if any(i["done"] for i in items):
        st.button("✅ 체크된 항목 모두 삭제", on_click=clear_checked)


def main():
    init_state()
    inject_css()
    items = st.session_state.shopping_items
    render_header(items)
    render_list(items)


main()
