"""Requirements document with function headings and embedded local PNG diagrams."""
from __future__ import annotations

import io
import struct
import zipfile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from reqcompleter_v2_0.protocol import TaskError


def save_document(store, result):
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal.font.size = Pt(10.5)
    normal.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    document.add_heading("软件需求说明书", 0)
    document.add_paragraph("ReqCompleter v2.1 · 分层功能与用例／活动图")
    if not result["converged"]:
        document.add_paragraph("本需求说明书为待复核稿：功能逻辑检查尚未判定收敛。")

    def paragraphs(content):
        for line in str(content).splitlines():
            if line.strip():
                document.add_paragraph(line)

    def picture(entry):
        image = store.path(entry["image"])
        data = image.read_bytes()
        width, height = struct.unpack(">II", data[16:24])
        section = document.sections[-1]
        maximum_width = section.page_width - section.left_margin - section.right_margin
        maximum_height = section.page_height - section.top_margin - section.bottom_margin - Inches(1)
        display_width = min(maximum_width, Inches(width / 96), maximum_height * width / height)
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run().add_picture(str(image), width=int(display_width))
        caption = document.add_paragraph(f"{entry['nodeId']} {entry['name']} · {'用例图' if entry['kind'] == 'use-case' else '活动图'}")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for title, field in (("1 软件概述", "software_intro"), ("2 数据实体", "data_entities"),
                         ("3 业务用例", "use_cases"), ("4 用例说明", "use_case_description")):
        document.add_heading(title, 1)
        if isinstance(result[field], list):
            for item in result[field]:
                document.add_paragraph(str(item), style="List Bullet")
        else:
            paragraphs(result[field])
    document.add_heading("5 功能需求", 1)
    document.add_heading("5.1 功能需求说明", 2)
    paragraphs(result["functional_requirements"])
    document.add_heading("5.2 分层功能与用例图", 2)
    by_node = {entry["nodeId"]: entry for entry in result["diagrams"]}
    picture(by_node["SYSTEM"])

    def functions(nodes, prefix="5.2", level=3):
        for index, node in enumerate(nodes, 1):
            numbering = f"{prefix}.{index}"
            document.add_heading(f"{numbering} {node['name']}（{node['id']}）", level)
            document.add_paragraph("参与者：" + "、".join(node["actors"]))
            paragraphs(node["description"])
            picture(by_node[node["id"]])
            functions(node["children"], numbering, level + 1)

    functions(result["functional_tree"]["functions"])
    for title, field in (("6 外部接口需求", "external_interface"), ("7 非功能需求", "nonfunctional_requirements")):
        document.add_heading(title, 1)
        paragraphs(result[field])
    content = io.BytesIO()
    document.save(content)
    with zipfile.ZipFile(content) as package:
        if package.testzip() or "word/document.xml" not in package.namelist():
            raise TaskError("DOCX_FAILED", "新版需求文档不是有效 DOCX。")
    store.write_bytes("final/requirements.docx", content.getvalue())
    return "final/requirements.docx"
