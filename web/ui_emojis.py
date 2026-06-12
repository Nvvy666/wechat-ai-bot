"""
Emoji Tab — 表情包管理
预览 + 标签编辑为主，列表折叠
"""
import gradio as gr
from pathlib import Path
from database import get_all_emojis, add_emoji_keyword, remove_emoji, add_log

EMOJI_DIR = Path(__file__).parent.parent / "emojis"
EMOJI_DIR.mkdir(parents=True, exist_ok=True)


def _scan():
    files = []
    for ext in ["*.gif","*.png","*.jpg","*.jpeg","*.bmp","*.webp"]:
        for f in sorted(EMOJI_DIR.glob(ext)):
            files.append(f.name)
    return files


def _table_rows():
    files = _scan()
    emojis = get_all_emojis()
    tagged = {}
    for e in emojis:
        fn = Path(e["filepath"]).name
        tagged.setdefault(fn, []).append(e)
    rows = []
    for i, fn in enumerate(files, 1):
        ts = tagged.get(fn, [])
        t = ts[0] if ts else {}
        rows.append([i, t.get("id",""), fn, t.get("keyword",""), t.get("emotion",""),
                     t.get("scenario",""), f"{t.get('usage_count',0)}"])
    if not rows:
        rows = [[0,"","(空)","","","","0"]]
    return rows


def create_emoji_tab():
    gr.Markdown("## 表情包")
    gr.Markdown(f"把 GIF/PNG 放到 `{EMOJI_DIR.absolute()}` 即可自动扫描")

    files = _scan()

    # ---- 编辑区 (主界面) ----
    with gr.Row():
        file_sel = gr.Dropdown(
            label="选择表情包文件",
            choices=files if files else ["(无)"],
            value=files[0] if files else None,
            scale=3,
        )
        preview = gr.Image(
            label="预览",
            value=str(EMOJI_DIR / files[0]) if files else None,
            width=120, height=120,
            scale=1,
        )

    with gr.Row():
        kw = gr.Textbox(label="关键词", placeholder="AI匹配用，如：哈哈", scale=1)
        em = gr.Textbox(label="情绪", placeholder="开心/难过/震惊...", scale=1)
        sc = gr.Textbox(label="场景", placeholder="打招呼/告别/安慰...", scale=1)
    nt = gr.Textbox(label="注释 (AI理解用)", placeholder="描述这个表情包的用法，例如：一只猫在摇头表示无奈")

    with gr.Row():
        save_btn = gr.Button("💾 保存标签", variant="primary", scale=2)
        del_btn = gr.Button("🗑 清除标签", variant="stop", scale=1)
        scan_btn = gr.Button("🔄 重新扫描", scale=1)

    # ---- 列表 (折叠) ----
    with gr.Accordion("📋 表情包列表", open=False):
        table = gr.Dataframe(
            headers=["#","ID","文件","关键词","情绪","场景","使用"],
            value=_table_rows(), label="全部表情包", interactive=False,
        )

    # ---- Handlers ----
    def refresh_files():
        fs = _scan()
        return (
            gr.Dropdown(choices=fs if fs else ["(无)"], value=fs[0] if fs else None),
            _table_rows(),
        )

    def on_select(fn):
        if not fn or fn == "(无)":
            return None, "", "", "", ""
        preview_path = str((EMOJI_DIR / fn).absolute()) if fn else None
        for e in get_all_emojis():
            if Path(e["filepath"]).name == fn:
                return preview_path, e["keyword"], e.get("emotion",""), e.get("scenario",""), e.get("note","")
        return preview_path, "", "", "", ""

    def on_save(fn, k, em_val, sc_val, nt_val):
        if not fn or fn == "(无)" or not k:
            raise gr.Warning("需要选择文件和填写关键词", duration=2)
        fp = str((EMOJI_DIR / fn).absolute())
        for e in get_all_emojis():
            if Path(e["filepath"]).name == fn:
                remove_emoji(e["id"])
        add_emoji_keyword(k.strip(), fp, em_val.strip(), sc_val.strip(), nt_val.strip())
        add_log("INFO", f"Emoji: {fn} -> {k}", "system")
        return _table_rows()

    def on_clear(fn):
        if not fn or fn == "(无)":
            raise gr.Warning("请选择文件", duration=2)
        for e in get_all_emojis():
            if Path(e["filepath"]).name == fn:
                remove_emoji(e["id"])
        add_log("INFO", f"Emoji cleared: {fn}", "system")
        return _table_rows()

    file_sel.change(on_select, file_sel, [preview, kw, em, sc, nt])
    save_btn.click(on_save, [file_sel, kw, em, sc, nt], table).then(
        fn=lambda: gr.Info("标签已保存", duration=2)
    )
    del_btn.click(on_clear, file_sel, table).then(
        fn=lambda: gr.Info("标签已清除", duration=2)
    )
    scan_btn.click(refresh_files, outputs=[file_sel, table]).then(
        fn=lambda: gr.Info("已重新扫描", duration=2)
    )

    return {}
